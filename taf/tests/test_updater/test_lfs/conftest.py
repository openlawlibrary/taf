"""Fixtures and scenario setup for the Git LFS tests.

Git LFS keeps a small text *pointer* in the repository and the real bytes in a
separate store, moved by the ``smudge`` and ``clean`` filters git runs on
checkout and commit. Those filters are configured in git config, and a clone
inherits global and system config but not the source repository's local config,
so ``lfs_global_config`` makes them visible globally for the duration of a test.
"""

import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Callable, Iterator, List, Optional

import pytest
from loguru import logger

from taf.git import GitRepository
from taf.tests.test_updater.conftest import SetupManager, add_valid_target_commits
from taf.tests.test_updater.test_lfs.lfs_server import LFSServer
from taf.tests.test_updater.update_utils import load_target_repositories
from taf.utils import run

#: Pattern committed to ``.gitattributes`` so git routes these files to LFS.
LFS_TRACKED_PATTERN = "*.bin"
LFS_FILE_NAME = "large_file.bin"

#: An ordinary, non-LFS file, for checking the filter stays out of the way.
PLAIN_FILE_NAME = "plain_file.txt"

#: A checkout in a fresh interpreter, importing only ``taf.git`` - so the result
#: reflects what a real caller gets, rather than what this test module's own
#: imports set up.
CHECKOUT_SCRIPT = """
import os
import sys
from pathlib import Path
from taf.git import GitRepository


def peak_rss_kb():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1])
    return 0


client_path, branch, file_name = sys.argv[1:4]
# Linux carries the peak-RSS watermark across fork and exec, so a child
# otherwise reports whatever its parent had reached
if Path("/proc/self/clear_refs").exists():
    Path("/proc/self/clear_refs").write_text("5")
client = GitRepository(path=client_path)
try:
    client.checkout_branch(branch)
    print("RAISED:none")
except Exception as exc:
    print("RAISED:" + type(exc).__name__)
with open(os.path.join(client_path, file_name), "rb") as handle:
    # a prefix: enough to recognise a pointer, and reading a large file whole
    # would be the measured process's biggest allocation
    print("BYTES:" + repr(handle.read(4096)))
print("RSS:%d" % peak_rss_kb())
"""

SPAWN_COUNTER = """#!/bin/sh
echo x >> "$GIT_LFS_SPAWN_LOG"
exec "$GIT_LFS_REAL" "$@"
"""


#: Skips what needs the binary; used by every module in this package.
needs_git_lfs = pytest.mark.skipif(
    not shutil.which("git-lfs"), reason="git-lfs is not installed"
)


def assert_committed_as_lfs_pointer(repo: GitRepository, file_name: str) -> None:
    """Assert ``file_name`` is stored in ``repo``'s HEAD commit as an LFS pointer.

    A misconfigured ``.gitattributes`` would commit the payload as an ordinary
    blob, exercising no LFS at all.
    """
    head_commit = repo.head_commit()
    assert head_commit is not None, f"{repo.name} has no commits"
    blob = repo.get_file(head_commit, file_name)
    assert isinstance(blob, str), f"{file_name} could not be read from HEAD"
    assert is_lfs_pointer(blob.encode()), (
        f"{repo.name}: {file_name} was committed as a normal blob, so this test "
        "is not exercising Git LFS"
    )


def assert_lfs_content_materialized(repo_path: Path, revision: str) -> None:
    """Assert the working tree holds real LFS content, not a pointer.

    The three failure modes are separated because they have different causes: a
    missing file means the checkout never happened, a pointer means the smudge
    filter did not run, and wrong bytes mean the wrong revision.
    """
    file_path = repo_path / LFS_FILE_NAME
    assert file_path.is_file(), f"{file_path} was never checked out"

    content = file_path.read_bytes()
    expected = get_lfs_file_content(revision)

    assert not is_lfs_pointer(content), (
        f"{file_path} contains a Git LFS pointer instead of the file's content, "
        f"so the smudge filter did not run for this checkout.\n"
        f"pointer:\n{content[:200].decode(errors='replace')}"
    )
    assert content == expected, (
        f"{file_path} holds unexpected bytes: expected the {revision} payload "
        f"({len(expected)} bytes), found {len(content)} bytes starting with "
        f"{content[:40]!r}"
    )


def build_lfs_origin(
    path: Path,
    other_branch: str = "other",
    payload_size: Optional[int] = None,
    extra_files: int = 0,
) -> GitRepository:
    """A standalone origin whose tracked files are stored in Git LFS.

    ``payload_size`` pads the tracked file, and ``extra_files`` adds siblings -
    both for measuring what a checkout costs.
    """

    def write(repo: GitRepository, revision: str) -> None:
        write_lfs_file(repo, revision, payload_size=payload_size)
        for index in range(extra_files):
            (repo.path / f"extra{index}.bin").write_bytes(
                get_lfs_file_content(f"{revision}-{index}")
            )

    repo = build_origin(path, write, other_branch)
    assert_committed_as_lfs_pointer(repo, LFS_FILE_NAME)
    return repo


def build_origin(
    path: Path,
    write_file: Callable[[GitRepository, str], None],
    other_branch: str = "other",
) -> GitRepository:
    """Create a standalone origin with two revisions on separate branches.

    The default branch ends at the ``v2`` payload and ``other_branch`` pins
    ``v1``, so a checkout between them has to rewrite the tracked file.
    """
    path.mkdir(parents=True, exist_ok=True)
    repo = GitRepository(path=path)
    repo.init_repo()
    write_file(repo, "v1")
    repo.commit("Add tracked file (v1)")
    repo.create_branch(other_branch)
    write_file(repo, "v2")
    repo.commit("Update tracked file (v2)")
    return repo


def build_plain_origin(path: Path, other_branch: str = "other") -> GitRepository:
    """A standalone origin with no LFS involved."""
    return build_origin(path, write_plain_file, other_branch)


def checkout_in_subprocess(
    client: GitRepository,
    branch: str,
    file_name: str,
    path_env: Optional[str] = None,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    """Check ``branch`` out in a fresh interpreter.

    Fresh because peak memory is a process high-water mark and the process count
    needs an environment the parent does not share.
    """
    environment = dict(env or os.environ)
    if path_env is not None:
        environment["PATH"] = path_env
    return subprocess.run(
        [sys.executable, "-c", CHECKOUT_SCRIPT, str(client.path), branch, file_name],
        capture_output=True,
        text=True,
        env=environment,
    )


def commit_lfs_content(origin_auth_repo, revision: str, lfs_url: Optional[str] = None):
    """Commit LFS-tracked content to every target repository and sign."""
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        add_valid_target_commits,
        {
            "mutate": partial(write_lfs_file, revision=revision, lfs_url=lfs_url),
            "commit_message": f"Update LFS-tracked file ({revision})",
        },
    )
    setup_manager.execute_tasks()

    target_repos = load_target_repositories(origin_auth_repo)
    assert target_repos, "no target repositories to commit LFS content to"
    for target_repo in target_repos.values():
        assert_committed_as_lfs_pointer(target_repo, LFS_FILE_NAME)


def get_counting_git_lfs_env(directory: Path, real_git_lfs: str, log: Path) -> dict:
    """Environment whose ``git-lfs`` records every execution in ``log``."""
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / "git-lfs"
    shim.write_text(SPAWN_COUNTER)
    shim.chmod(0o755)
    log.write_text("")
    return {
        **os.environ,
        "PATH": f"{directory}{os.pathsep}{os.environ['PATH']}",
        "GIT_LFS_REAL": real_git_lfs,
        "GIT_LFS_SPAWN_LOG": str(log),
    }


def enable_lfs(repo: GitRepository, lfs_url: Optional[str] = None) -> None:
    """Install the LFS filters into ``repo`` and track the LFS pattern there.

    When ``lfs_url`` is given, write a ``.lfsconfig`` pinning the LFS endpoint.
    ``.lfsconfig`` is committed, so it travels with the repository through
    clones and lets a client resolve objects from the LFS server rather than
    from whichever git remote it was cloned from.
    """
    run("git", "-C", str(repo.path), "lfs", "install", "--local")
    run("git", "-C", str(repo.path), "lfs", "track", LFS_TRACKED_PATTERN)
    if lfs_url is not None:
        (repo.path / ".lfsconfig").write_text(f"[lfs]\n\turl = {lfs_url}\n")


def get_peak_rss_of_checkout(result: subprocess.CompletedProcess) -> int:
    """The peak RSS in KB that ``checkout_in_subprocess`` reported."""
    for line in result.stdout.splitlines():
        if line.startswith("RSS:"):
            return int(line.split(":", 1)[1])
    raise AssertionError(f"no RSS in {result.stdout} {result.stderr[-500:]}")


def is_lfs_pointer(content: bytes) -> bool:
    """True when git-lfs itself recognizes ``content`` as a pointer file.

    Empty content is not one, and has to be rejected here: ``git lfs pointer
    --check`` exits 0 for it.
    """
    if not content:
        return False
    try:
        run("git", "lfs", "pointer", "--check", "--stdin", input=content, raw=True)
        return True
    except subprocess.CalledProcessError:
        return False


def get_lfs_file_content(revision: str) -> bytes:
    """Deterministic, recognizable payload for the LFS-tracked file.

    Padded well past a pointer file's length, and distinct per revision so a
    stale checkout is distinguishable from a missing smudge.
    """
    return f"LFS-CONTENT-{revision}-".encode() + revision.encode() * 512


@pytest.fixture(autouse=True)
def lfs_global_config(monkeypatch, tmp_path, deterministic_git_environment):
    """Make the LFS filters visible to git globally, for this test only.

    Extends the suite's generated config with what ``git lfs install`` writes,
    rather than running that command and editing the developer's real
    ``~/.gitconfig``.
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

    TAF logs through loguru, so pytest's ``caplog`` sees nothing. An exception
    raised inside a filter reaches libgit2 stripped of its reason, which makes
    the log the only place that reason survives.
    """
    messages: List[str] = []
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


def get_path_without_git_lfs(shim_dir: Path) -> str:
    """``PATH`` with ``git-lfs`` unreachable and ``git`` still installed.

    A package manager puts the two in one directory, so ``git`` is linked into
    ``shim_dir`` to survive its removal: an uninstalled Git LFS leaves git in
    place, and reading the repository config needs it.
    """
    git = shutil.which("git")
    shim_dir.mkdir(parents=True, exist_ok=True)
    if git is not None:
        link = shim_dir / Path(git).name
        if not link.exists():
            try:
                link.symlink_to(git)
            except OSError:
                shutil.copy2(git, link)
    entries = [str(shim_dir)] + [
        entry
        for entry in os.environ["PATH"].split(os.pathsep)
        if entry and shutil.which("git-lfs", path=entry) is None
    ]
    candidate = os.pathsep.join(entries)
    assert (
        shutil.which("git-lfs", path=candidate) is None
    ), "git-lfs is still reachable, so this PATH does not simulate its absence"
    assert (
        shutil.which("git", path=candidate) is not None
    ), "git went missing along with git-lfs, so this PATH describes no real machine"
    return candidate


def publish_lfs_objects(origin_auth_repo, lfs_server) -> None:
    """Move every target repository's LFS objects onto the server.

    Deletes the local copies, so the server is the only possible source and a
    materialized working tree proves an HTTP fetch happened.
    """
    for target_repo in load_target_repositories(origin_auth_repo).values():
        lfs_server.take_local_objects(target_repo.path)


@contextmanager
def unwritable_lfs_store(repo_path: Path) -> Iterator[None]:
    """Make git-lfs unable to store objects in ``repo_path``, then restore it.

    A regular file where ``.git/lfs`` belongs is what a full disk or a read-only
    mount looks like to ``git lfs clean``, which exits 2.
    """
    store = repo_path / ".git" / "lfs"
    shutil.rmtree(store, ignore_errors=True)
    store.write_text("not a directory")
    try:
        yield
    finally:
        store.unlink()
        store.mkdir()


def write_lfs_file(
    target_repo: GitRepository,
    revision: str,
    lfs_url: Optional[str] = None,
    payload_size: Optional[int] = None,
) -> None:
    """Enable LFS in ``target_repo`` and write the tracked file for ``revision``."""
    enable_lfs(target_repo, lfs_url=lfs_url)
    content = get_lfs_file_content(revision)
    if payload_size is not None:
        content = (content * (payload_size // len(content) + 1))[:payload_size]
    (target_repo.path / LFS_FILE_NAME).write_bytes(content)


def write_plain_file(target_repo: GitRepository, revision: str) -> None:
    """Write an ordinary, non-LFS file for ``revision``."""
    (target_repo.path / PLAIN_FILE_NAME).write_text(f"plain {revision}")
