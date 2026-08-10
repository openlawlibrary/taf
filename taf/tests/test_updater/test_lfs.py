"""Does TAF clone and update target repositories that use Git LFS?

TAF itself knows nothing about LFS - it drives git. What is under test is
whether the git operations TAF chooses leave a *usable* working tree when a
target repository keeps its content in LFS, or whether the client is left
holding pointer files.

The decisive variable is where git-lfs can find objects. It asks the endpoint it
resolves for the repository: ``lfs.url``, normally from a **committed**
``.lfsconfig`` (so it survives cloning), otherwise derived from the git remote.
That matters here because TAF never clones a target repository straight from its
origin - it clones into a temporary partition as a *bare* repo, and a bare clone
carries no LFS objects, then materializes the user's copy from that temporary
repo (``updater_pipeline.update_users_target_repositories`` -> ``clone_from_disk``).

So the intermediate repo can never supply the objects, and the outcome hinges
entirely on ``.lfsconfig``:

* with an LFS server configured, the client fetches from it and everything works
  - this is the deployed shape (GitHub/GitLab hosting the objects), and the
  tests below prove the bytes really travel over HTTP by deleting the origin's
  local objects first and asserting the server served them;
* with no ``lfs.url``, git-lfs falls back to the git remote, which is the
  objectless temporary clone, and the update fails with
  ``fatal: <file>: smudge filter lfs failed``.

A separate gap sits in ``GitRepository.checkout_branch()``, which checks out
through ``pygit2`` when the branch already exists locally. libgit2 *does* have a
filter API (and pygit2 exposes it from 1.13.3 - though TAF still pins
``pygit2==1.9.*`` on Python < 3.11, where it is absent), but it does not run the
external filters declared in git config, and TAF registers no LFS filter of its
own. So that checkout writes pointer text even when the objects are present.

The standard clone/update flows above do not hit it: pygit2's checkout is a
no-op when the repo is already on the target branch, and the subsequent
subprocess ``git merge``/``reset --hard`` does the smudging. It is reachable
when the checkout actually changes branches, which the updater normally refuses
to do (it warns instead) *unless* ``--force`` is passed - and from
``taf repo reset`` (``api/repository.py``) and the development-mode rollback in
``updater.py``. ``test_checkout_branch_materializes_lfs_content`` pins the
behavior at the ``GitRepository`` level; no test here yet drives it through the
CLI.

These tests need the ``git-lfs`` binary. They skip without it rather than
failing, so the suite still runs on a machine with no LFS installed; CI installs
it (see ``.github/workflows/ci.yml``). The LFS server is a small in-process
Python one (``lfs_server.py``) - no extra dependency to install.
"""

import subprocess
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
def lfs_global_config(monkeypatch, tmp_path):
    """Make the LFS filters visible to git *globally*, hermetically.

    A clone inherits filter config from global/system config only - never from
    the source repository's local config - so without this a cloned target
    repository would keep pointer files no matter what TAF does, and the test
    would be measuring the developer's machine setup instead of TAF.

    Rather than running ``git lfs install`` (which would edit the developer's
    real ``~/.gitconfig``), point ``GIT_CONFIG_GLOBAL`` at a throwaway file that
    ``include``s the original, and restate the resolved essentials explicitly.
    """

    def git_config_get(key):
        result = subprocess.run(
            ["git", "config", "--get", key], capture_output=True, text=True
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    # Resolve these *before* redirecting GIT_CONFIG_GLOBAL, so they are exactly
    # the values git would otherwise have used.
    carried_over = {
        key: git_config_get(key)
        for key in ("user.name", "user.email", "init.defaultBranch", "core.autocrlf")
    }

    original_path = ""
    listed = subprocess.run(
        ["git", "config", "--global", "--list", "--show-origin"],
        capture_output=True,
        text=True,
    )
    if listed.returncode == 0 and listed.stdout:
        # "file:/home/u/.gitconfig\tuser.name=..." -> the path of the real config
        first = listed.stdout.splitlines()[0]
        if first.startswith("file:"):
            original_path = first[len("file:") :].split("\t")[0]

    lines = []
    if original_path:
        # keep everything else the suite might rely on (safe.directory, ...)
        lines += ["[include]", f"\tpath = {Path(original_path).as_posix()}"]
    # The include above is best-effort; on a machine whose global config lives
    # somewhere unparsed (or nowhere) these must still be present or the tests
    # below cannot commit.
    if carried_over["user.name"] or carried_over["user.email"]:
        lines.append("[user]")
        for key in ("user.name", "user.email"):
            if carried_over[key]:
                lines.append(f"\t{key.split('.')[1]} = {carried_over[key]}")
    if carried_over["init.defaultBranch"]:
        lines += ["[init]", f"\tdefaultBranch = {carried_over['init.defaultBranch']}"]
    if carried_over["core.autocrlf"]:
        lines += ["[core]", f"\tautocrlf = {carried_over['core.autocrlf']}"]
    # what `git lfs install` writes, spelled out so we don't mutate real config
    lines += [
        '[filter "lfs"]',
        "\tclean = git-lfs clean -- %f",
        "\tsmudge = git-lfs smudge -- %f",
        "\tprocess = git-lfs filter-process",
        "\trequired = true",
    ]
    config_path = tmp_path / "lfs_gitconfig"
    config_path.write_text("\n".join(lines) + "\n")

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

    Documents a real constraint rather than a defect to fix: because TAF stages
    every target repository through a bare intermediate clone, the origin's own
    ``.git/lfs/objects`` is never reachable from the client. Somebody must host
    the objects.
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
    """Isolate the checkout path from the transfer question.

    Uses ``GitRepository`` directly - no updater - and clones from a *non-bare*
    origin, so ``git clone --local`` hardlinks ``.git/lfs/objects`` and every
    object is already present locally. Nothing needs downloading and no server
    is involved; the only question is whether the checkout runs the smudge
    filter.
    """
    origin = build_lfs_origin(tmp_path / "origin")
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)

    default_branch = client.default_branch
    # 'other' has no local branch yet, so this goes through the git subprocess
    client.checkout_branch("other", create=True)
    assert_lfs_content_materialized(client.path, "v1")

    # A fresh instance, as a subsequent TAF run would use: reusing `client` here
    # would instead trip over its cached pygit2 handle, whose in-memory index is
    # stale after the subprocess checkout above ("1 conflict prevents checkout")
    # - a separate issue that would mask the one under test.
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
    """git-lfs absent and LFS unused: everything behaves exactly as before.

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
