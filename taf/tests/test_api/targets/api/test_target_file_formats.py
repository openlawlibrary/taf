"""Reading signed target files of target repositories in the single object and list formats."""

from pathlib import Path

import pytest

import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository
from taf.models.types import Commitish
from taf.tests.test_api.util import sign_target_file
from taf.tests.test_targets_history.conftest import (
    MAIN,
    PUBLICATION,
    make_entry,
    make_history,
)
from taf.yubikey.yubikey_manager import PinManager


@pytest.fixture
def sign(
    auth_repo_when_add_repositories_json: AuthenticationRepository,
    pin_manager: PinManager,
    keystore_delegations: str,
):
    """Sign a target file of the test authentication repository, returning the new commit."""

    def _sign(target_name, content):
        return sign_target_file(
            auth_repo_when_add_repositories_json,
            pin_manager,
            keystore_delegations,
            target_name,
            content,
        )

    return _sign


@pytest.fixture
def target_names(library: Path):
    """Names of target repositories listed in the test authentication repository."""
    return [f"{library.name}/target1", f"{library.name}/target2"]


@pytest.mark.parametrize(
    "content",
    [make_entry(**{"build-date": "2026-01-15"}), make_history(3, PUBLICATION)],
    ids=["single-object", "list"],
)
def test_get_target_tip(
    auth_repo_when_add_repositories_json, sign, target_names, content
):
    commit = sign(target_names[0], content)

    auth_repo = auth_repo_when_add_repositories_json
    assert auth_repo.get_target(target_names[0], commit) == content
    assert auth_repo.get_target_tip(target_names[0], commit) == (
        content[-1] if isinstance(content, list) else content
    )


def test_get_target_tip_without_target_file(
    auth_repo_when_add_repositories_json, target_names
):
    assert auth_repo_when_add_repositories_json.get_target_tip(target_names[0]) is None


def test_targets_at_revisions_reads_current_commit_of_both_formats(
    auth_repo_when_add_repositories_json, sign, target_names
):
    single_object_name, list_name = target_names
    single_object = make_entry("single", **{"build-date": "2026-01-15"})
    first = make_entry("first", PUBLICATION, **{"branch-id": "build-1"})
    last = make_entry(
        "last", PUBLICATION, **{"branch-id": "build-1", "capstone": True, "note": "x"}
    )
    sign(single_object_name, single_object)
    first_commit = sign(list_name, [first])
    last_commit = sign(list_name, [first, last])

    targets = auth_repo_when_add_repositories_json.targets_at_revisions(
        [first_commit, last_commit]
    )

    assert targets[first_commit][list_name] == {
        "branch": PUBLICATION,
        "commit": first["commit"],
        "custom": {},
    }
    assert targets[last_commit][list_name] == {
        "branch": PUBLICATION,
        "commit": last["commit"],
        "custom": {"note": "x"},
    }
    assert targets[last_commit][single_object_name] == {
        "branch": MAIN,
        "commit": single_object["commit"],
        "custom": {"build-date": "2026-01-15"},
    }


def test_is_commit_authenticated_finds_commit_listed_before_current_commit(
    auth_repo_when_add_repositories_json, sign, target_names
):
    history = make_history(2)
    sign(target_names[0], history[:1])
    sign(target_names[0], history)

    auth_repo = auth_repo_when_add_repositories_json
    assert auth_repo.is_commit_authenticated(
        target_names[0], Commitish.from_hash(history[0]["commit"])
    )
    assert not auth_repo.is_commit_authenticated(
        target_names[0], Commitish.from_hash(make_entry("never-signed")["commit"])
    )


def test_repository_default_branch_is_branch_of_current_commit_in_list(
    auth_repo_when_add_repositories_json, sign, target_names
):
    sign(target_names[0], make_history(2) + [make_entry("current", PUBLICATION)])

    auth_repo = auth_repo_when_add_repositories_json
    repositoriesdb.clear_repositories_db()
    try:
        repositoriesdb.load_repositories(auth_repo)
        repository = repositoriesdb.get_repository(auth_repo, target_names[0])
    finally:
        repositoriesdb.clear_repositories_db()

    assert repository.default_branch == PUBLICATION
