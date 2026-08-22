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

import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor

import pygit2
import pytest

from taf.exceptions import GitLFSError
from taf.git import GitRepository
from taf import lfs as lfs_module
from taf.lfs import run_git_lfs
from taf.tests.test_updater.test_lfs.conftest import (
    LFS_FILE_NAME,
    PLAIN_FILE_NAME,
    assert_lfs_content_materialized,
    build_lfs_origin,
    build_plain_origin,
    checkout_in_subprocess,
    commit_lfs_content,
    get_git_lfs_version,
    is_lfs_pointer,
    lfs_file_content,
    path_without_git_lfs,
    publish_lfs_objects,
)
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    load_target_repositories,
    update_and_check_commit_shas,
    update_invalid_repos_and_check_if_repos_exist,
)
from taf.updater.types.update import OperationType

pytestmark = pytest.mark.skipif(
    not get_git_lfs_version(),
    reason="git-lfs is not installed (needs the `git lfs` subcommand on PATH)",
)

TARGETS_WITH_LFS = {
    "targets_config": [{"name": "target1"}, {"name": "target2"}],
}

#: git's message when the smudge filter cannot produce a tracked file's content.
LFS_SMUDGE_FAILED_PATTERN = r"smudge filter lfs failed"


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


@pytest.mark.parametrize("origin_auth_repo", [TARGETS_WITH_LFS], indirect=True)
def test_clone_lfs_without_server_fails_with_smudge_error(origin_auth_repo, client_dir):
    """No ``lfs.url`` anywhere: cloning an LFS target repository fails.

    A constraint, not a defect to fix. TAF stages every target repository
    through a bare intermediate clone, so the origin's own ``.git/lfs/objects``
    is unreachable from the client and something has to host the objects.
    """
    commit_lfs_content(origin_auth_repo, "v1")

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        LFS_SMUDGE_FAILED_PATTERN,
        True,
    )


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


def test_filter_is_registered_by_importing_taf_git(tmp_path):
    """A caller that imports only ``taf.git`` gets LFS-aware checkouts.

    Runs in a fresh interpreter: this module imports ``taf.lfs`` directly, which
    would register the filter regardless of whether the production wiring does.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    result = checkout_in_subprocess(
        GitRepository(path=client.path),
        "main",
        LFS_FILE_NAME,
        os.environ["PATH"],
    )

    assert "RAISED:none" in result.stdout, result.stderr
    assert repr(lfs_file_content("v2")) in result.stdout, (
        "importing taf.git did not register the LFS filter, so the checkout "
        f"produced pointer text:\n{result.stdout}"
    )


def test_checkout_without_git_lfs_never_truncates_the_file(tmp_path):
    """git-lfs absent: refuse or write the pointer, but never destroy content.

    A filter that raises leaves libgit2's destination file truncated to zero
    bytes, so no filter is registered when git-lfs is missing. libgit2 then
    either refuses the checkout - it cannot reconcile smudged working-tree bytes
    with a pointer blob - or writes the pointer, which is what git does without
    Git LFS installed. Both leave the file readable.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    checkout_in_subprocess(
        GitRepository(path=client.path),
        "main",
        LFS_FILE_NAME,
        path_without_git_lfs(),
    )

    content = (client.path / LFS_FILE_NAME).read_bytes()
    assert content, "the working-tree file was truncated by the failed checkout"
    assert content == lfs_file_content("v1") or is_lfs_pointer(content), (
        "expected the file left untouched or replaced by its pointer, found "
        f"{len(content)} bytes starting with {content[:40]!r}"
    )


def test_run_git_lfs_reports_a_missing_binary(monkeypatch):
    """The message a user gets when git-lfs is needed but absent."""
    monkeypatch.setattr(lfs_module, "get_git_lfs_executable", lambda: None)

    with pytest.raises(GitLFSError, match="Git LFS is not installed"):
        run_git_lfs("smudge", "some/file.bin", b"pointer", None)


def test_checkout_reports_an_unfetchable_lfs_object(tmp_path, lfs_log):
    """git-lfs present but the object is nowhere: fail loudly, and say why."""
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    # the client can otherwise reach the origin's store over git-lfs' file://
    # endpoint, so both copies of the object have to go
    for repo_path in (client.path, origin.path):
        shutil.rmtree(repo_path / ".git" / "lfs" / "objects", ignore_errors=True)

    client = GitRepository(path=client.path)
    with pytest.raises(pygit2.GitError):
        client.checkout_branch(client.default_branch)

    assert any(
        "Git LFS could not process" in message for message in lfs_log
    ), f"nothing explained the failure; logged: {lfs_log}"


def test_plain_repository_unaffected_when_git_lfs_missing(tmp_path, lfs_log):
    """git-lfs absent and LFS unused: nothing changes.

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
    barrier = threading.Barrier(len(repos))

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
