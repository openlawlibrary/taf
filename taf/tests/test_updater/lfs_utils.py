"""Helpers for exercising TAF against target repositories that use Git LFS.

Git LFS replaces the tracked file's content in git with a small text *pointer*
(``version https://git-lfs.github.com/spec/v1\\noid sha256:...\\nsize ...``) and
keeps the real bytes in a separate object store, transferred by the ``smudge``/
``clean`` filters that git runs on checkout/commit.

Two consequences drive everything here:

* Only ``git`` (the subprocess) runs those filters. libgit2/``pygit2`` does not
  implement them, so anything checked out through ``pygit2`` lands in the
  working tree as the pointer text.
* The filters are configured in git *config*, and a clone inherits only
  global/system config - not the source repository's local config. So enabling
  LFS per-repository is not enough for a clone to materialize content;
  ``git lfs install`` must be visible globally. ``lfs_global_config`` below
  arranges that hermetically, without touching the developer's real config.

No LFS server is required: git-lfs speaks a ``file://`` endpoint for
filesystem remotes and reads objects straight out of the origin's
``.git/lfs/objects``, which is exactly the shape of TAF's test origins.
"""

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from taf.tests.conftest import KEYSTORE_PATH, TEST_DATA_ORIGIN_PATH
from taf.tests.test_updater.conftest import sign_target_repositories
from taf.yubikey.yubikey_manager import PinManager

LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"

#: Pattern committed to ``.gitattributes`` so git routes these files to LFS.
LFS_TRACKED_PATTERN = "*.bin"
LFS_FILE_NAME = "large_file.bin"


def git_lfs_version() -> str:
    """Return the installed ``git lfs`` version, or "" when unavailable.

    Checks the subcommand rather than just the binary: a ``git-lfs`` on PATH
    that git cannot dispatch to is useless here.
    """
    if shutil.which("git-lfs") is None:
        return ""
    try:
        result = subprocess.run(
            ["git", "lfs", "version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def is_lfs_pointer(content: bytes) -> bool:
    """True if ``content`` is an unsmudged LFS pointer instead of real data."""
    return content.startswith(LFS_POINTER_PREFIX)


def lfs_file_content(revision: str) -> bytes:
    """Deterministic, recognizable payload for the LFS-tracked file.

    Padded well past a pointer file's length so a pointer can never be mistaken
    for content by a length check, and distinct per revision so a stale
    checkout is distinguishable from a missing smudge.
    """
    return f"LFS-CONTENT-{revision}-".encode() + revision.encode() * 512


def enable_lfs(repo: GitRepository, lfs_url: Optional[str] = None) -> None:
    """Install the LFS filters into ``repo`` and track ``*.bin`` there.

    When ``lfs_url`` is given, write a ``.lfsconfig`` pinning the LFS endpoint.
    ``.lfsconfig`` is *committed*, so it travels with the repository through
    clones - which is what lets a client resolve objects from the real LFS
    server instead of from whichever git remote it happens to have been cloned
    from. This is how hosted LFS repositories are normally set up, and TAF
    depends on it (see ``test_lfs.py``).
    """
    _run_git(repo.path, ["lfs", "install", "--local"])
    _run_git(repo.path, ["lfs", "track", LFS_TRACKED_PATTERN])
    if lfs_url is not None:
        (repo.path / ".lfsconfig").write_text(f"[lfs]\n\turl = {lfs_url}\n")


def _run_git(cwd: Path, args: List[str]) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def add_lfs_target_commits(
    auth_repo: AuthenticationRepository,
    pin_manager: PinManager,
    target_repos: list,
    revision: str = "v1",
    lfs_url: Optional[str] = None,
) -> None:
    """Commit an LFS-tracked file to every target repo, then re-sign.

    A ``SetupManager`` task: ``auth_repo``, ``pin_manager`` and ``target_repos``
    are injected from the signature. Mirrors ``add_valid_target_commits`` in
    ``test_updater/conftest.py``, but the payload goes through LFS.
    """
    for target_repo in target_repos:
        enable_lfs(target_repo, lfs_url=lfs_url)
        (target_repo.path / LFS_FILE_NAME).write_bytes(lfs_file_content(revision))
        target_repo.commit(f"Add LFS-tracked file ({revision})")
    sign_target_repositories(
        TEST_DATA_ORIGIN_PATH, auth_repo.name, KEYSTORE_PATH, pin_manager
    )


def update_lfs_target_commits(
    auth_repo: AuthenticationRepository,
    pin_manager: PinManager,
    target_repos: list,
    revision: str = "v2",
) -> None:
    """Rewrite the LFS-tracked file in every target repo, then re-sign.

    Assumes ``add_lfs_target_commits`` already ran, so LFS is configured and
    ``.gitattributes`` is committed.
    """
    for target_repo in target_repos:
        (target_repo.path / LFS_FILE_NAME).write_bytes(lfs_file_content(revision))
        target_repo.commit(f"Update LFS-tracked file ({revision})")
    sign_target_repositories(
        TEST_DATA_ORIGIN_PATH, auth_repo.name, KEYSTORE_PATH, pin_manager
    )


def build_lfs_origin(path: Path, other_branch: str = "other") -> GitRepository:
    """Create a standalone LFS origin with two revisions on separate branches.

    The default branch ends at the ``v2`` payload; ``other_branch`` pins ``v1``.
    That shape lets a test check out across revisions - the only way to observe
    whether a given checkout implementation runs the smudge filter.
    """
    # GitRepository.init_repo() only mkdirs when the directory already exists,
    # so create it here
    path.mkdir(parents=True, exist_ok=True)
    repo = GitRepository(path=path)
    repo.init_repo()
    enable_lfs(repo)
    (path / LFS_FILE_NAME).write_bytes(lfs_file_content("v1"))
    repo.commit("Add LFS-tracked file (v1)")
    repo.create_branch(other_branch)
    (path / LFS_FILE_NAME).write_bytes(lfs_file_content("v2"))
    repo.commit("Update LFS-tracked file (v2)")
    return repo


def assert_lfs_content_materialized(repo_path: Path, revision: str) -> None:
    """Assert the working tree holds real LFS content, not a pointer.

    Distinguishes the three failure modes deliberately, because they have
    different causes: a missing file (checkout never happened), a pointer
    (smudge filter did not run - e.g. a ``pygit2`` checkout), and stale or
    wrong bytes (checked out at the wrong revision).
    """
    file_path = repo_path / LFS_FILE_NAME
    assert file_path.is_file(), f"{file_path} was never checked out"

    content = file_path.read_bytes()
    expected = lfs_file_content(revision)

    assert not is_lfs_pointer(content), (
        f"{file_path} contains an unsmudged Git LFS pointer instead of the "
        f"file's content. The LFS smudge filter did not run for this checkout "
        f"(pygit2/libgit2 does not implement git's filters).\n"
        f"pointer:\n{content[:200].decode(errors='replace')}"
    )
    assert content == expected, (
        f"{file_path} holds unexpected bytes: expected the {revision} payload "
        f"({len(expected)} bytes), found {len(content)} bytes starting with "
        f"{content[:40]!r}"
    )
