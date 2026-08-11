"""Cloning and updating target repositories that keep their content in Git LFS.

TAF knows nothing about LFS; it drives git. What these tests establish is
whether the git operations TAF chooses leave real file content in the working
tree, or LFS pointer files.

Where git-lfs looks for objects decides the outcome. It uses the endpoint it
resolves for the repository: ``lfs.url``, normally from a committed
``.lfsconfig`` so it survives cloning, otherwise derived from the git remote.
TAF never clones a target repository straight from its origin - it clones into a
temporary partition as a *bare* repo, which carries no LFS objects, then
materializes the user's copy from that temporary repo
(``updater_pipeline.update_users_target_repositories`` -> ``clone_from_disk``).
The intermediate repo therefore cannot supply objects:

* with an LFS server configured, the client fetches from it and clone and update
  both work. The tests prove the bytes travel over HTTP by deleting the origin's
  local objects and asserting the server served them.
* with no ``lfs.url``, git-lfs falls back to the git remote - the objectless
  temporary clone - and the update fails with ``smudge filter lfs failed``. LFS
  target repositories need a reachable LFS server; a local mirror is not enough.

``taf.lfs`` covers the other half: libgit2 does not run the external filters
declared in git config, so pygit2 checkouts need TAF's own registered filter to
materialize LFS content. ``test_checkout_branch_materializes_lfs_content``
covers that at the ``GitRepository`` level. A plain clone or update does not
exercise it - pygit2's checkout is a no-op when already on the target branch and
the following subprocess merge does the smudging - but ``--force`` across
branches, ``taf repo reset`` and the development-mode rollback in ``updater.py``
do.

These tests need the ``git-lfs`` binary and skip without it, so the suite still
runs where LFS is not installed; CI installs it (``.github/workflows/ci.yml``).
The LFS server is a small in-process Python one (``lfs_server.py``), so there is
no service to install.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from loguru import logger

from taf import lfs
from taf.git import GitRepository
from taf.tests.test_updater.conftest import SetupManager
from taf.tests.test_updater.lfs_server import LFSServer
from taf.tests.test_updater.lfs_utils import (
    LFS_FILE_NAME,
    PLAIN_FILE_NAME,
    add_lfs_target_commits,
    assert_lfs_content_materialized,
    build_lfs_origin,
    build_plain_origin,
    git_lfs_version,
    update_lfs_target_commits,
)
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    load_target_repositories,
    update_and_check_commit_shas,
)
from taf.updater.types.update import OperationType

pytestmark = pytest.mark.skipif(
    not git_lfs_version(),
    reason="git-lfs is not installed (needs the `git lfs` subcommand on PATH)",
)

TARGETS_WITH_LFS = {
    "targets_config": [{"name": "target1"}, {"name": "target2"}],
}


@pytest.fixture(autouse=True)
def lfs_global_config(monkeypatch, tmp_path, deterministic_git_environment):
    """Make the LFS filters visible to git globally, for this test only.

    A clone inherits filter config from global or system config, never from the
    source repository's local config, so a cloned target repository keeps
    pointer files unless the filters are configured globally.

    Extends the suite's generated config (``deterministic_git_environment``)
    with what ``git lfs install`` would write, rather than running that command
    and editing the developer's real ``~/.gitconfig``.
    """
    config_path = tmp_path / "lfs_gitconfig"
    config_path.write_text(
        "\n".join(
            [
                "[include]",
                f"\tpath = {Path(deterministic_git_environment).as_posix()}",
                '[filter "lfs"]',
                "\tclean = git-lfs clean -- %f",
                "\tsmudge = git-lfs smudge -- %f",
                "\tprocess = git-lfs filter-process",
                "\trequired = true",
            ]
        )
        + "\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config_path))
    return config_path


@pytest.fixture
def lfs_log():
    """Collect what ``taf.lfs`` logs during a test.

    TAF logs through loguru, not the stdlib, so pytest's ``caplog`` sees
    nothing; add a sink for the duration of the test instead. This matters
    because pygit2 discards the exception raised inside a filter, so the log is
    the only place the real reason survives.
    """
    messages: list = []
    handler_id = logger.add(
        lambda message: messages.append(message.record["message"]),
        level="WARNING",
        filter=lambda record: record["name"] == "taf.lfs",
        format="{message}",
    )
    yield messages
    logger.remove(handler_id)


@pytest.fixture
def lfs_server(tmp_path):
    """A real Git LFS endpoint on 127.0.0.1 for the duration of one test."""
    with LFSServer(tmp_path / "lfs-storage") as server:
        yield server


def publish_lfs_objects(origin_auth_repo, lfs_server) -> None:
    """Move every target repo's LFS objects onto the server.

    Deletes the local copies, so the server becomes the only possible source and
    a materialized working tree proves an HTTP fetch happened.
    """
    for target_repo in load_target_repositories(origin_auth_repo).values():
        lfs_server.take_local_objects(target_repo.path)


@pytest.mark.parametrize("origin_auth_repo", [TARGETS_WITH_LFS], indirect=True)
def test_clone_materializes_lfs_content_from_server(
    origin_auth_repo, client_dir, lfs_server
):
    """``taf repo clone`` materializes LFS content when a server is configured."""
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        add_lfs_target_commits, {"revision": "v1", "lfs_url": lfs_server.url}
    )
    setup_manager.execute_tasks()
    publish_lfs_objects(origin_auth_repo, lfs_server)

    clone_repositories(origin_auth_repo, client_dir)

    client_target_repos = load_target_repositories(
        origin_auth_repo, library_dir=client_dir
    )
    assert client_target_repos, "no target repositories were cloned"
    for target_repo in client_target_repos.values():
        assert_lfs_content_materialized(target_repo.path, "v1")

    assert lfs_server.downloads, (
        "no object was downloaded from the LFS server, so this test did not "
        "actually exercise LFS transfer"
    )


@pytest.mark.parametrize("origin_auth_repo", [TARGETS_WITH_LFS], indirect=True)
def test_update_materializes_new_lfs_content_from_server(
    origin_auth_repo, client_dir, lfs_server
):
    """A subsequent ``taf repo update`` materializes the *new* LFS content."""
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        add_lfs_target_commits, {"revision": "v1", "lfs_url": lfs_server.url}
    )
    setup_manager.execute_tasks()
    publish_lfs_objects(origin_auth_repo, lfs_server)

    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_lfs_target_commits, {"revision": "v2"})
    setup_manager.execute_tasks()
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

    assert lfs_server.downloads, (
        "the update fetched no object from the LFS server, so the new LFS "
        "content was not transferred"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Without an lfs.url, git-lfs falls back to the git remote, which for a "
        "TAF client is the objectless bare temp clone, so the smudge filter "
        "fails and the update aborts. LFS target repositories therefore require "
        "a reachable LFS server - a local mirror alone is not enough."
    ),
)
@pytest.mark.parametrize("origin_auth_repo", [TARGETS_WITH_LFS], indirect=True)
def test_clone_lfs_without_server_configured(origin_auth_repo, client_dir):
    """No ``lfs.url`` anywhere: cloning an LFS target repository fails.

    A constraint, not a defect to fix. TAF stages every target repository
    through a bare intermediate clone, so the origin's own ``.git/lfs/objects``
    is unreachable from the client and something has to host the objects.
    """
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_lfs_target_commits, {"revision": "v1"})
    setup_manager.execute_tasks()

    clone_repositories(origin_auth_repo, client_dir)

    client_target_repos = load_target_repositories(
        origin_auth_repo, library_dir=client_dir
    )
    assert client_target_repos, "no target repositories were cloned"
    for target_repo in client_target_repos.values():
        assert_lfs_content_materialized(target_repo.path, "v1")


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

    # A fresh instance, as a subsequent TAF run would use. Reusing `client` here
    # would hit its cached pygit2 handle, whose in-memory index is stale after
    # the subprocess checkout above ("1 conflict prevents checkout").
    client = GitRepository(path=client.path)
    assert not client.something_to_commit(), "working tree should be clean"

    # the default branch does exist locally, so this takes the pygit2 path
    client.checkout_branch(default_branch)
    assert_lfs_content_materialized(client.path, "v2")


def test_checkout_reports_missing_git_lfs_instead_of_writing_a_pointer(
    tmp_path, monkeypatch, lfs_log
):
    """git-lfs absent while the repository *does* use LFS: fail, and say why.

    The dangerous outcome is a silent one - a working tree full of pointer text
    that looks like a successful checkout. pygit2 discards the exception a
    filter raises (it surfaces as ``failed to close filter stream``), so the
    filter logs the real reason itself; that log line is the contract here.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    monkeypatch.setattr(lfs, "git_lfs_executable", lambda: None)

    client = GitRepository(path=client.path)
    with pytest.raises(Exception):
        client.checkout_branch(client.default_branch)

    assert any(
        "git-lfs" in message for message in lfs_log
    ), f"nothing explained the failure; logged: {lfs_log}"


def test_plain_repository_unaffected_when_git_lfs_missing(
    tmp_path, monkeypatch, lfs_log
):
    """git-lfs absent and LFS unused: nothing changes.

    The filter declares ``attributes = "filter=lfs"``, so libgit2 only invokes
    it for paths ``.gitattributes`` routes to LFS. A repository that uses none
    must be untouched - no error, no log noise.
    """
    monkeypatch.setattr(lfs, "git_lfs_executable", lambda: None)

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

    pygit2 documents the filter *registry* as not thread-safe; registration
    happens once at import, but the filter itself runs concurrently because the
    updater materializes target repositories through a ThreadPoolExecutor.
    """
    repos = []
    for index in range(4):
        origin = build_lfs_origin(tmp_path / f"origin{index}")
        client = GitRepository(path=tmp_path / f"client{index}")
        client.clone_from_disk(origin.path, keep_remote=True)
        client.checkout_branch("other", create=True)
        repos.append(GitRepository(path=client.path))

    errors = []

    def checkout(repo):
        try:
            repo.checkout_branch(repo.default_branch)
        except Exception as error:  # noqa: BLE001 - reported below
            errors.append(f"{repo.path.name}: {error}")

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(checkout, repos))

    assert not errors, f"concurrent checkouts failed: {errors}"
    for repo in repos:
        assert_lfs_content_materialized(repo.path, "v2")


@pytest.mark.parametrize("origin_auth_repo", [TARGETS_WITH_LFS], indirect=True)
def test_cloned_lfs_file_is_tracked_by_lfs_at_all(origin_auth_repo, client_dir):
    """Guard the tests themselves: the file must really be LFS-tracked upstream.

    If ``.gitattributes`` or the filters were misconfigured, the payload would
    be committed as an ordinary blob and the assertions above would pass while
    testing nothing about LFS.
    """
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_lfs_target_commits, {"revision": "v1"})
    setup_manager.execute_tasks()

    origin_target_repos = load_target_repositories(origin_auth_repo)
    for target_repo in origin_target_repos.values():
        blob = target_repo._git(f"cat-file -p HEAD:{LFS_FILE_NAME}")
        assert "git-lfs.github.com/spec" in blob, (
            f"{target_repo.name}: {LFS_FILE_NAME} was committed as a normal blob, "
            "so this suite is not exercising Git LFS at all"
        )
