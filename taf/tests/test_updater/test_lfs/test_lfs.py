"""Cloning and updating target repositories that keep their content in Git LFS.

Where git-lfs looks for objects decides the outcome. It uses the endpoint it
resolves for the repository: ``lfs.url``, normally from a committed
``.lfsconfig`` so it survives cloning, otherwise derived from the git remote.
TAF never clones a target repository straight from its origin - it clones into a
temporary partition as a *bare* repo, which carries no LFS objects, then
materializes the user's copy from that temporary repo
(``updater_pipeline.update_users_target_repositories`` -> ``clone_from_disk``).
The intermediate repo therefore cannot supply objects:

* with an LFS server configured, the client fetches from it and clone and update
  both work. The tests delete the origin's local objects and assert the server
  served them, so the bytes provably travel over HTTP.
* with no ``lfs.url``, git-lfs falls back to the git remote - the objectless
  temporary clone - and the update fails with ``smudge filter lfs failed``. LFS
  target repositories need a reachable LFS server; a local mirror is not enough.

``taf.lfs`` covers the other half: libgit2 does not run the external filters
declared in git config, so pygit2 checkouts need TAF's registered filter to
materialize LFS content.

These tests need the ``git-lfs`` binary and skip without it, so the suite still
runs where LFS is not installed; CI installs it (``.github/workflows/ci.yml``).
"""

import io
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pygit2
import pytest

from taf import lfs as lfs_module
from taf import lfs_process
from taf.exceptions import GitError, GitLFSError
from taf.git import GitRepository
from taf.lfs import filter_through_git_lfs
from taf.tests.conftest import run_ignoring_failure
from taf.tests.test_updater.test_lfs.conftest import (
    LFS_FILE_NAME,
    PLAIN_FILE_NAME,
    assert_lfs_content_materialized,
    build_lfs_origin,
    build_plain_origin,
    checkout_in_subprocess,
    commit_lfs_content,
    get_lfs_file_content,
    get_path_without_git_lfs,
    is_lfs_pointer,
    needs_git_lfs,
    publish_lfs_objects,
    unwritable_lfs_store,
)
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    load_target_repositories,
    update_and_check_commit_shas,
    update_invalid_repos_and_check_if_repos_exist,
)
from taf.updater.types.update import OperationType
from taf.utils import run

TARGETS_WITH_LFS = {
    "targets_config": [{"name": "target1"}, {"name": "target2"}],
}

#: git's message when the smudge filter cannot produce a tracked file's content.
LFS_SMUDGE_FAILED_PATTERN = r"smudge filter lfs failed"


@needs_git_lfs
def test_a_clean_failure_outside_a_checkout_does_not_fail_the_next_one(tmp_path):
    """A file that could not be filtered belongs to the operation that hit it.

    libgit2 runs the clean filter to answer ``something_to_commit``, which the
    updater asks of every target repository before it checks anything out. A
    failure there must not surface as the next checkout's error, since that
    checkout may well have materialized every file correctly.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)

    content = get_lfs_file_content("v2")
    tracked = client.path / LFS_FILE_NAME
    # same length, so libgit2 cannot tell it apart by size and has to clean it
    tracked.write_bytes(content.replace(b"v2", b"V2"))
    with unwritable_lfs_store(client.path):
        # git cannot answer either, with a store it cannot write to
        with pytest.raises(GitError):
            client.something_to_commit()
    tracked.write_bytes(content)

    client = GitRepository(path=client.path)
    client.checkout_branch(client.default_branch)

    assert_lfs_content_materialized(client.path, "v2")


@needs_git_lfs
def test_a_merge_that_cannot_be_filtered_leaves_no_merge_in_progress(tmp_path):
    """The failure is reported, and the repository is not left mid-merge.

    A merge is only over once it is committed and its state cleaned up. Failing
    before that leaves ``MERGE_HEAD`` behind, and every later merge in that
    repository fails.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other")

    run("git", "-C", str(client.path), "config", "lfs.url", "http://127.0.0.1:1/lfs")
    for repo_path in (client.path, origin.path):
        shutil.rmtree(repo_path / ".git" / "lfs" / "objects", ignore_errors=True)

    client = GitRepository(path=client.path)
    with pytest.raises(GitLFSError, match="could not process"):
        client.merge_branch(client.default_branch, allow_new_commit=True)

    assert not (
        client.path / ".git" / "MERGE_HEAD"
    ).exists(), "the repository is still merging"
    assert not run_ignoring_failure(
        "git", "-C", str(client.path), "status", "--porcelain"
    ), "the merge left changes staged"
    run("git", "-C", str(client.path), "commit", "--allow-empty", "-qm", "later")
    run("git", "-C", str(client.path), "merge", "-q", client.default_branch)


@needs_git_lfs
def test_a_merge_whose_commit_fails_can_still_be_completed(tmp_path):
    """A commit that fails leaves the merge in progress, as git does.

    Clearing the merge state instead would let the next commit succeed as an
    ordinary one, recording no second parent: the branch would look merged while
    history says it never was. A hook that refuses the commit gets there.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other")
    hook = client.path / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)

    client = GitRepository(path=client.path)
    with pytest.raises(GitError, match="could not commit"):
        client.merge_branch(client.default_branch, allow_new_commit=True)

    hook.unlink()
    run("git", "-C", str(client.path), "commit", "--quiet", "-m", "retried")
    parents = run(
        "git", "-C", str(client.path), "rev-list", "--parents", "-1", "HEAD"
    ).split()[1:]
    merged = run("git", "-C", str(client.path), "rev-parse", client.default_branch)

    assert merged in parents, (
        "the retried commit records no second parent, so the merge was lost "
        f"while its content stayed: parents {parents}"
    )


@needs_git_lfs
def test_a_quoted_git_lfs_path_is_recognized(tmp_path, monkeypatch):
    """Windows config quotes the program when its path contains a space.

    Splitting a Windows command line keeps the quotes inside the token, and a
    program that cannot be resolved makes the filter stand aside - which would
    put pointer text in the working tree with nothing said about it.
    """
    workdir = tmp_path / "repo"
    workdir.mkdir()
    run("git", "-C", str(workdir), "init", "-q", ".")
    quoted = f'"{shutil.which("git-lfs")}" filter-process'
    run("git", "-C", str(workdir), "config", "--local", "filter.lfs.process", quoted)

    monkeypatch.setattr("os.name", "nt")

    assert lfs_module.get_lfs_filter_commands(str(workdir)) == (quoted, quoted)


@needs_git_lfs
def test_an_unfetchable_object_costs_one_fetch_attempt(tmp_path, lfs_server):
    """One attempt per object, not two.

    git-lfs exits rather than answering that one file failed, so a broken
    exchange is its answer for that file: asking again repeats the network work
    for something it has already refused.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    run("git", "-C", str(client.path), "config", "lfs.url", lfs_server.url)
    for repo_path in (client.path, origin.path):
        shutil.rmtree(repo_path / ".git" / "lfs" / "objects", ignore_errors=True)
    lfs_server.reset_counters()

    client = GitRepository(path=client.path)
    with pytest.raises(GitLFSError, match="could not process"):
        client.checkout_branch(client.default_branch)

    assert (
        len(lfs_server.requests) == 1
    ), f"the object was asked for {len(lfs_server.requests)} times"


@needs_git_lfs
def test_an_unfetchable_object_is_tolerated_when_lfs_is_not_required(tmp_path, lfs_log):
    """``filter.lfs.required=false`` asks git not to fail; do the same.

    git accepts a failed filter in that configuration, so the checkout
    completes and the pointer is left in place.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)
    run(
        "git",
        "-C",
        str(client.path),
        "config",
        "--local",
        "filter.lfs.required",
        "false",
    )

    run("git", "-C", str(client.path), "config", "lfs.url", "http://127.0.0.1:1/lfs")
    for repo_path in (client.path, origin.path):
        shutil.rmtree(repo_path / ".git" / "lfs" / "objects", ignore_errors=True)

    client = GitRepository(path=client.path)
    client.checkout_branch(client.default_branch)

    content = (client.path / LFS_FILE_NAME).read_bytes()
    assert content, "the file was truncated by the failed checkout"
    assert is_lfs_pointer(content)
    assert any(
        "1 file(s)" in message for message in lfs_log
    ), f"the checkout did not say how many files it could not process: {lfs_log}"


@needs_git_lfs
def test_an_unreachable_server_is_reported_once_per_operation(tmp_path, lfs_log):
    """One line for the checkout, not one per file.

    Every file fails when the server is unreachable, and an archive holds a
    hundred thousand of them; the count belongs in the error that ends the
    operation.
    """
    origin = build_lfs_origin(tmp_path / "origin", extra_files=2)
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    run("git", "-C", str(client.path), "config", "lfs.url", "http://127.0.0.1:1/lfs")
    for repo_path in (client.path, origin.path):
        shutil.rmtree(repo_path / ".git" / "lfs" / "objects", ignore_errors=True)

    client = GitRepository(path=client.path)
    with pytest.raises(GitLFSError, match="3 file"):
        client.checkout_branch(client.default_branch)

    assert (
        len(lfs_log) == 1
    ), f"expected one report for three failed files, got {len(lfs_log)}: {lfs_log}"


@needs_git_lfs
def test_checkout_branch_materializes_lfs_content(tmp_path):
    """A checkout that changes branches materializes LFS content.

    Clones from a non-bare origin, so ``git clone --local`` hardlinks
    ``.git/lfs/objects`` and every object is already present: no server is
    involved and nothing needs downloading, leaving only the question of whether
    the checkout runs the smudge filter.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)

    default_branch = client.default_branch
    # 'other' has no local branch yet, so this goes through the git subprocess
    client.checkout_branch("other", create=True)
    assert_lfs_content_materialized(client.path, "v1")

    # a fresh instance, whose pygit2 handle sees the index the subprocess
    # checkout above wrote
    client = GitRepository(path=client.path)
    assert not client.something_to_commit(), "working tree should be clean"

    # the default branch does exist locally, so this takes the pygit2 path
    client.checkout_branch(default_branch)
    assert_lfs_content_materialized(client.path, "v2")


@needs_git_lfs
def test_checkout_paths_reports_its_own_failures(tmp_path):
    """Every checkout path reports its failures, and leaves none behind.

    A failure left in place would be raised by the next unrelated checkout,
    which would then report an error for files it materialized correctly.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    run("git", "-C", str(client.path), "config", "lfs.url", "http://127.0.0.1:1/lfs")
    for repo_path in (client.path, origin.path):
        shutil.rmtree(repo_path / ".git" / "lfs" / "objects", ignore_errors=True)

    failing = GitRepository(path=client.path)
    other_revision = failing.top_commit_of_branch(failing.default_branch)
    with pytest.raises(GitLFSError, match="Git LFS"):
        failing.checkout_paths(other_revision, LFS_FILE_NAME)

    assert not lfs_process.SESSION.failures, (
        "a failure was left behind for the next operation to raise: "
        f"{lfs_process.SESSION.failures}"
    )


@needs_git_lfs
def test_checkout_without_git_lfs_never_truncates_the_file(tmp_path):
    """git-lfs absent: the filter stands aside and the file survives.

    Without the binary there is nothing to filter with, so libgit2 either
    refuses the checkout - it cannot reconcile smudged working-tree bytes with a
    pointer blob - or writes the pointer. Both leave the file readable.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    result = checkout_in_subprocess(
        GitRepository(path=client.path),
        client.default_branch,
        LFS_FILE_NAME,
        get_path_without_git_lfs(tmp_path / "no-git-lfs"),
    )

    assert "RAISED:" in result.stdout, f"the checkout never ran: {result.stderr}"
    content = (client.path / LFS_FILE_NAME).read_bytes()
    assert content, "the working-tree file was truncated by the failed checkout"
    assert content == get_lfs_file_content("v1") or is_lfs_pointer(content), (
        "expected the file left untouched or replaced by its pointer, found "
        f"{len(content)} bytes starting with {content[:40]!r}"
    )


@needs_git_lfs
def test_clean_failure_keeps_an_uncommitted_edit(tmp_path):
    """A failing clean must not cost the user their uncommitted work.

    Raising from the filter would leave the file holding whatever had been
    forwarded, so the raw bytes are passed through instead: they differ from the
    pointer blob, and the checkout is refused.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    precious = b"UNCOMMITTED EDIT " * 200
    (client.path / LFS_FILE_NAME).write_bytes(precious)

    with unwritable_lfs_store(client.path):
        client = GitRepository(path=client.path)
        with pytest.raises(pygit2.GitError, match="conflict prevents checkout"):
            client.checkout_branch(client.default_branch)

        assert (
            client.path / LFS_FILE_NAME
        ).read_bytes() == precious, (
            "the uncommitted edit was overwritten by the checkout"
        )


@needs_git_lfs
@pytest.mark.parametrize("origin_auth_repo", [TARGETS_WITH_LFS], indirect=True)
def test_clone_lfs_without_server_fails_with_smudge_error(origin_auth_repo, client_dir):
    """No ``lfs.url`` anywhere: cloning an LFS target repository fails.

    TAF stages every target repository through a bare intermediate clone, so
    the origin's own ``.git/lfs/objects`` is unreachable from the client and
    something has to host the objects.
    """
    commit_lfs_content(origin_auth_repo, "v1")

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        LFS_SMUDGE_FAILED_PATTERN,
        True,
    )


@needs_git_lfs
@pytest.mark.parametrize("origin_auth_repo", [TARGETS_WITH_LFS], indirect=True)
def test_clone_materializes_lfs_content_from_server(
    origin_auth_repo, client_dir, lfs_server
):
    """``taf repo clone`` materializes LFS content when a server is configured."""
    commit_lfs_content(origin_auth_repo, "v1", lfs_url=lfs_server.url)
    publish_lfs_objects(origin_auth_repo, lfs_server)

    clone_repositories(origin_auth_repo, client_dir)

    client_target_repos = load_target_repositories(
        origin_auth_repo, library_dir=client_dir
    )
    assert client_target_repos, "no target repositories were cloned"
    for target_repo in client_target_repos.values():
        assert_lfs_content_materialized(target_repo.path, "v1")

    assert lfs_server.downloads, "no object was downloaded from the LFS server"


@needs_git_lfs
def test_concurrent_checkouts_through_the_filter(tmp_path):
    """The filter is registered once and used from several threads at once.

    pygit2 documents the filter registry as not thread-safe; registration
    happens once at import, but the filter itself runs concurrently because the
    updater materializes target repositories through a ThreadPoolExecutor.
    """
    repos = []
    for index in range(8):
        origin = build_lfs_origin(tmp_path / f"origin{index}")
        client = GitRepository(path=tmp_path / f"client{index}")
        client.clone_from_disk(origin.path, keep_remote=True)
        client.checkout_branch("other", create=True)
        repos.append(GitRepository(path=client.path))

    errors = []
    # release every thread into the filter at once, so the streams overlap
    # instead of finishing one after another
    barrier = threading.Barrier(len(repos), timeout=60)

    def checkout(repo):
        barrier.wait()
        try:
            repo.checkout_branch(repo.default_branch)
        except Exception as error:
            errors.append(f"{repo.path.name}: {error}")

    with ThreadPoolExecutor(max_workers=len(repos)) as executor:
        list(executor.map(checkout, repos))

    assert not errors, f"concurrent checkouts failed: {errors}"
    for repo in repos:
        assert_lfs_content_materialized(repo.path, "v2")


@needs_git_lfs
def test_config_changes_take_effect_immediately(tmp_path):
    """The answer follows the repository's config, with nothing cached.

    git resolves its config from a set of files this code cannot enumerate -
    ``include.path``, linked worktrees, `GIT_CONFIG_SYSTEM`, XDG paths - so a
    cached answer can outlive the configuration that produced it.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    workdir = str(client.path)

    assert all(lfs_module.get_lfs_filter_commands(workdir)), "LFS should be on"

    for key in ("filter.lfs.process", "filter.lfs.smudge", "filter.lfs.clean"):
        run("git", "-C", workdir, "config", "--local", key, "some-other-program")

    assert lfs_module.get_lfs_filter_commands(workdir) == (
        "",
        "",
    ), "a change to the repository's config was not picked up"


@needs_git_lfs
def test_empty_content_is_not_a_pointer():
    """A truncated file must not read as a pointer left in place.

    git-lfs accepts empty input, so the check cannot be left to it.
    """
    run("git", "lfs", "pointer", "--check", "--stdin", input=b"", raw=True)

    assert not is_lfs_pointer(b"")


@needs_git_lfs
def test_filter_agrees_with_git_when_lfs_is_not_configured(tmp_path, lfs_log):
    """No ``filter.lfs`` config: leave the blob alone, as git does.

    Filtering where git would not makes pygit2 report a clean working tree that
    git reports as modified, and git's own checkouts then refuse to run.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    # drop every definition of the filter, leaving only the .gitattributes entry
    for scope in ("--local", "--global"):
        run_ignoring_failure(
            "git",
            "-C",
            str(client.path),
            "config",
            scope,
            "--remove-section",
            "filter.lfs",
        )

    assert not run_ignoring_failure(
        "git", "-C", str(client.path), "config", "--get", "filter.lfs.process"
    ), "filter.lfs is still configured, so this test proves nothing"

    client = GitRepository(path=client.path)
    porcelain = run("git", "-C", str(client.path), "status", "--porcelain") or ""

    assert bool(client.something_to_commit()) == bool(porcelain.strip()), (
        "TAF and git disagree about whether the working tree is modified, so "
        "the filter ran where git would not have"
    )
    assert not lfs_log, f"the filter should not have run at all, logged: {lfs_log}"


@needs_git_lfs
def test_filter_is_registered_by_importing_taf_git(tmp_path):
    """A caller that imports only ``taf.git`` gets LFS-aware checkouts.

    Runs in a fresh interpreter, so only what ``taf.git`` itself imports can
    register the filter.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    result = checkout_in_subprocess(
        GitRepository(path=client.path),
        client.default_branch,
        LFS_FILE_NAME,
        os.environ["PATH"],
    )

    assert "RAISED:none" in result.stdout, result.stderr
    assert repr(get_lfs_file_content("v2")) in result.stdout, (
        "importing taf.git did not register the LFS filter, so the checkout "
        f"produced pointer text:\n{result.stdout}"
    )


@needs_git_lfs
def test_filter_stands_aside_for_a_non_lfs_filter_command(
    tmp_path, monkeypatch, deterministic_git_environment
):
    """``filter.lfs.*`` pointing at another program is not ours to run.

    Running git-lfs for it would put bytes in the working tree that git never
    wrote.
    """
    other_config = tmp_path / "other_gitconfig"
    other_config.write_text(
        "\n".join(
            [
                "[include]",
                f"\tpath = {Path(deterministic_git_environment).as_posix()}",
                '[filter "lfs"]',
                "\tsmudge = sed s/x/y/g",
                "\tclean = sed s/y/x/g",
            ]
        )
        + "\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(other_config))

    smudge, clean = lfs_module.get_lfs_filter_commands(str(tmp_path))
    assert (smudge, clean) == (
        "",
        "",
    ), f"git-lfs would have run for another program's filter: {(smudge, clean)}"


def test_filtering_reports_a_missing_binary(monkeypatch, tmp_path):
    """The message a user gets when git-lfs is needed but absent."""
    monkeypatch.setenv("PATH", get_path_without_git_lfs(tmp_path / "no-git-lfs"))
    lfs_module.get_git_lfs_executable.cache_clear()
    try:
        with pytest.raises(GitLFSError, match="Git LFS is not installed"):
            filter_through_git_lfs(
                "smudge", "some/file.bin", io.BytesIO(b"pointer"), str(tmp_path)
            )
    finally:
        lfs_module.get_git_lfs_executable.cache_clear()


@needs_git_lfs
def test_get_lfs_filter_commands_tolerates_an_awkward_path(tmp_path):
    """A path containing ``{`` must not raise out of the config lookup.

    An exception escaping ``check()`` leaves libgit2's destination file
    truncated, so the lookup must not go through anything that treats a path as
    a format string.
    """
    awkward = tmp_path / "client{x"
    awkward.mkdir()

    smudge, clean = lfs_module.get_lfs_filter_commands(str(awkward))
    assert isinstance(smudge, str) and isinstance(clean, str)


@needs_git_lfs
def test_legacy_filter_configuration_is_recognized(
    tmp_path, monkeypatch, deterministic_git_environment
):
    """``filter.lfs.smudge``/``clean`` without ``filter.lfs.process``.

    git honors that older form fully, so a checkout must materialize content
    rather than leave a pointer.
    """
    legacy_config = tmp_path / "legacy_gitconfig"
    legacy_config.write_text(
        "\n".join(
            [
                "[include]",
                f"\tpath = {Path(deterministic_git_environment).as_posix()}",
                '[filter "lfs"]',
                "\tsmudge = git-lfs smudge -- %f",
                "\tclean = git-lfs clean -- %f",
                "\trequired = true",
            ]
        )
        + "\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(legacy_config))

    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    smudge, clean = lfs_module.get_lfs_filter_commands(str(client.path))
    assert smudge and clean, "the older per-direction config was not recognized"

    client = GitRepository(path=client.path)
    client.checkout_branch(client.default_branch)
    assert_lfs_content_materialized(client.path, "v2")


def test_missing_git_lfs_is_reported_once_per_repository(
    tmp_path, monkeypatch, lfs_log
):
    """One line per repository, not one per file.

    An archive can hold a hundred thousand LFS files, and git itself says
    nothing at all in this situation.
    """
    workdir = tmp_path / "repo"
    workdir.mkdir()
    run("git", "-C", str(workdir), "init", "-q", ".")
    run(
        "git",
        "-C",
        str(workdir),
        "config",
        "--local",
        "filter.lfs.process",
        "git-lfs filter-process",
    )
    monkeypatch.setenv("PATH", get_path_without_git_lfs(tmp_path / "no-git-lfs"))
    lfs_module.get_git_lfs_executable.cache_clear()
    lfs_module._reported_missing_binary.discard(str(workdir))
    try:
        for _ in range(5):
            lfs_module.warn_once_if_git_lfs_is_missing(str(workdir))
    finally:
        lfs_module.get_git_lfs_executable.cache_clear()
        lfs_module._reported_missing_binary.discard(str(workdir))

    assert len(lfs_log) == 1, f"expected one warning, got {len(lfs_log)}: {lfs_log}"
    assert "Git LFS is not installed" in lfs_log[0]


@needs_git_lfs
def test_repository_without_lfs_is_untouched(tmp_path, lfs_log):
    """A repository that uses no LFS is unaffected by the filter.

    The filter declares ``attributes = "filter=lfs"``, so libgit2 only invokes
    it for paths ``.gitattributes`` routes to LFS. A repository that uses none
    must be untouched - no error, no log noise.
    """
    origin = build_plain_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)

    client.checkout_branch("other", create=True)
    assert (client.path / PLAIN_FILE_NAME).read_text() == "plain v1"

    client = GitRepository(path=client.path)
    client.checkout_branch(client.default_branch)
    assert (client.path / PLAIN_FILE_NAME).read_text() == "plain v2"

    assert not lfs_log, f"the LFS filter should have stayed silent, logged: {lfs_log}"


@needs_git_lfs
def test_skip_smudge_is_honored(tmp_path):
    """``git lfs install --skip-smudge`` asks for pointers; do not override it.

    It disables the smudge direction only, so clean must still run or pygit2
    writes raw content into the object database where a pointer belongs.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)
    run("git", "-C", str(client.path), "lfs", "install", "--local", "--skip-smudge")

    smudge, clean = lfs_module.get_lfs_filter_commands(str(client.path) + "/")
    assert not smudge, "smudge should be disabled by --skip-smudge"
    assert clean, "clean must stay enabled, or pointers stop being written"

    client = GitRepository(path=client.path)
    client.checkout_branch(client.default_branch)

    content = (client.path / LFS_FILE_NAME).read_bytes()
    assert is_lfs_pointer(content), (
        "the user asked for pointers, but the checkout fetched content: "
        f"{len(content)} bytes"
    )


@needs_git_lfs
def test_the_filter_configuration_is_read_once_per_operation(tmp_path):
    """Reading it per file is the launch-per-file cost the session removes.

    Bounded to the operation, so a change between operations is still seen -
    which matters because ``.lfsconfig`` is committed and moves with a checkout.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    workdir = str(client.path)

    with lfs_process.session():
        before = lfs_module.get_lfs_filter_commands(workdir)
        run(
            "git",
            "-C",
            workdir,
            "config",
            "--local",
            "filter.lfs.process",
            "some-other-program",
        )
        assert (
            lfs_module.get_lfs_filter_commands(workdir) == before
        ), "the lookup was repeated inside one operation"

    assert lfs_module.get_lfs_filter_commands(workdir) == (
        "",
        "",
    ), "the answer outlived the operation that cached it"


@needs_git_lfs
def test_unfetchable_lfs_object_leaves_the_pointer_not_an_empty_file(tmp_path, lfs_log):
    """An object git-lfs cannot get fails the checkout, leaving a pointer.

    git aborts a checkout when a required filter fails. A filter cannot, since
    the exception it raises reaches libgit2 stripped of its reason and leaves the
    destination truncated, so the failure is raised by the caller once the
    checkout is over - and the file is left as a readable pointer rather than
    empty or missing.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)
    size_before = (client.path / LFS_FILE_NAME).stat().st_size

    # the client can otherwise reach the origin's store over git-lfs' file://
    # endpoint, so both copies of the object have to go
    run("git", "-C", str(client.path), "config", "lfs.url", "http://127.0.0.1:1/lfs")
    for repo_path in (client.path, origin.path):
        shutil.rmtree(repo_path / ".git" / "lfs" / "objects", ignore_errors=True)

    client = GitRepository(path=client.path)
    with pytest.raises(GitLFSError, match="could not process"):
        client.checkout_branch(client.default_branch)

    content = (client.path / LFS_FILE_NAME).read_bytes()
    assert content, f"the file was truncated (was {size_before} bytes)"
    assert is_lfs_pointer(content), (
        f"expected the pointer to be left in place, found {len(content)} bytes "
        f"starting with {content[:40]!r}"
    )
    assert any(
        "Could not get the Git LFS content" in message for message in lfs_log
    ), f"the failure was not reported, logged: {lfs_log}"


@needs_git_lfs
@pytest.mark.parametrize("origin_auth_repo", [TARGETS_WITH_LFS], indirect=True)
def test_update_materializes_new_lfs_content_from_server(
    origin_auth_repo, client_dir, lfs_server
):
    """A subsequent ``taf repo update`` materializes the new LFS content."""
    commit_lfs_content(origin_auth_repo, "v1", lfs_url=lfs_server.url)
    publish_lfs_objects(origin_auth_repo, lfs_server)

    clone_repositories(origin_auth_repo, client_dir)

    commit_lfs_content(origin_auth_repo, "v2", lfs_url=lfs_server.url)
    publish_lfs_objects(origin_auth_repo, lfs_server)
    lfs_server.reset_counters()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
    )

    client_target_repos = load_target_repositories(
        origin_auth_repo, library_dir=client_dir
    )
    assert client_target_repos, "no target repositories are present after the update"
    for target_repo in client_target_repos.values():
        assert_lfs_content_materialized(target_repo.path, "v2")

    assert lfs_server.downloads, "the update fetched no object from the LFS server"
