"""Tests around the clone/access error path in ``taf.git``.

Two things are covered here:

* the committed fix that stopped the access error from rendering as
  ``"Cannot None <repo> ..."`` and gave the "repository could not be found"
  fallback an actionable message (these pass); and
* the two defects the clone investigation surfaced but did not yet fix - a
  command line containing a path with spaces is mangled by ``run()``'s
  whitespace split, and the real underlying git error is swallowed (logged at
  debug) instead of being surfaced on the raised exception. Those are encoded
  as ``xfail(strict=True)`` regression tests so they stay red until fixed and
  flip to a hard failure (prompting removal of the marker) once they are.
"""

from pathlib import Path

import pytest

import taf.git as git_module
from taf.exceptions import CloneRepoException, GitAccessDeniedException, GitError
from taf.git import GitRepository


def _repo(tmp_path, urls):
    """A GitRepository instance that only needs .name/.urls/.log_prefix for the
    error-formatting code under test (no on-disk repo required)."""
    return GitRepository(path=Path(tmp_path) / "law-private", urls=urls)


# --------------------------------------------------------------------------- #
# Committed fix: the access error names the operation and carries guidance.
# --------------------------------------------------------------------------- #


def test_clone_repo_exception_defaults_to_clone_operation(tmp_path):
    # Defence in depth: even constructed directly, CloneRepoException must name
    # "clone" rather than rendering the operation as None.
    exc = CloneRepoException(_repo(tmp_path, ["https://example.com/x"]))
    message = str(exc)
    assert "Cannot clone" in message
    assert "Cannot None" not in message


def test_raise_git_access_error_for_clone_names_clone_not_none(tmp_path, monkeypatch):
    # This is the exact regression from the field report: a private repo that an
    # unauthenticated probe cannot see falls through to the final branch. Before
    # the fix that branch raised with operation=None -> "Cannot None ...".
    monkeypatch.setattr(git_module, "is_host_known", lambda host: True)
    monkeypatch.setattr(git_module, "repository_exists", lambda url: False)

    repo = _repo(tmp_path, ["https://github.com/openlawlibrary/law-private"])
    with pytest.raises(CloneRepoException) as exc_info:
        repo.raise_git_access_error(CloneRepoException, operation="clone")

    message = str(exc_info.value)
    first_line = message.splitlines()[0]
    assert "Cannot clone" in first_line
    assert "None" not in first_line
    # the fallback is no longer a bare error - it carries actionable guidance
    assert "could not be found" in message


def test_raise_git_access_error_default_operation_is_not_none(tmp_path, monkeypatch):
    # A caller that forgets to pass an operation must never produce "Cannot None".
    monkeypatch.setattr(git_module, "is_host_known", lambda host: True)
    monkeypatch.setattr(git_module, "repository_exists", lambda url: False)

    repo = _repo(tmp_path, ["https://github.com/openlawlibrary/law-private"])
    with pytest.raises(GitAccessDeniedException) as exc_info:
        repo.raise_git_access_error()

    first_line = str(exc_info.value).splitlines()[0]
    assert "None" not in first_line


# --------------------------------------------------------------------------- #
# Open defect 1: `run()` splits the command on whitespace, so a repository path
# containing a space (e.g. a Windows home dir "C:\\Users\\Given Surname\\...")
# breaks the `git -C <path>` argument and every clone attempt fails.
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason=(
        "run() does command[0].split(), shattering `git -C <path with spaces>`; "
        "clone into a spaced path fails. Fix by passing argv as a list / quoting."
    ),
)
def test_clone_into_path_with_spaces(origin_repo: GitRepository, tmp_path):
    dest = Path(tmp_path) / "Given Surname" / "clone"
    dest.mkdir(parents=True)
    repo = GitRepository(path=dest)
    # assign after construction to bypass URL validation - the local origin
    # path is a valid clone source but not a URL (mirrors the other clone tests)
    repo.urls = [str(origin_repo.path)]
    repo.clone()
    assert repo.is_git_repository


@pytest.mark.xfail(
    strict=True,
    reason="run() splits `git -C <path with spaces> ...` on whitespace",
)
def test_git_subprocess_handles_spaced_repo_path(tmp_path):
    # A local git operation that actually shells out (via _git -> run) must
    # tolerate a repository path with spaces. The repo is initialised through
    # run()'s list form (which is not split), so only the _git string command
    # under test is exercised against the spaced path.
    from taf.utils import run

    dest = Path(tmp_path) / "Given Surname" / "repo"
    dest.mkdir(parents=True)
    run("git", "-C", str(dest), "init")
    repo = GitRepository(path=dest)
    out = repo._git("rev-parse --is-inside-work-tree", reraise_error=True)
    assert out.strip() == "true"


# --------------------------------------------------------------------------- #
# Open defect 2: the real per-URL git error (which explains *why* the clone
# failed) is only logged at debug and dropped; the surfaced CloneRepoException
# replaces it with a generic guess.
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason=(
        "clone() catches the per-URL GitError and logs it at debug only; the "
        "underlying git message never reaches the raised CloneRepoException."
    ),
)
def test_clone_surfaces_underlying_git_error(clone_repository: GitRepository, monkeypatch):
    clone_repository.urls = ["https://example.com/x.git"]
    sentinel = r"fatal: cannot change to 'C:\Users\Given': No such file or directory"

    def fake_git(*args, **kwargs):
        raise GitError(clone_repository, message=sentinel)

    monkeypatch.setattr(clone_repository, "_git", fake_git)
    # keep raise_git_access_error off the network and on the final fallback
    monkeypatch.setattr(git_module, "is_host_known", lambda host: True)
    monkeypatch.setattr(git_module, "repository_exists", lambda url: False)

    with pytest.raises(CloneRepoException) as exc_info:
        clone_repository.clone()

    assert sentinel in str(exc_info.value)
