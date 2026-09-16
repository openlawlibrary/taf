"""The update pipeline's check that target files listing commits were only appended to."""

from types import SimpleNamespace

from taf.exceptions import TargetsHistoryRewrittenError
from taf.targets_history import serialize_target_file
from taf.tests.test_targets_history.conftest import make_history
from taf.tests.test_updater.test_target_validator.conftest import (
    MAIN,
    REPO1,
    REPO2,
    law,
    make_commits,
    make_pipeline,
)
from taf.updater.lifecycle_handlers import Event
from taf.updater.updater_pipeline import UpdateStatus

HISTORY = make_history(3)
PARENT_COMMIT = make_commits("parent", 1)[0]


def _pipeline_with_target_files(target_files, parent_commit=PARENT_COMMIT):
    """
    A pipeline validating one authentication commit per entry of `target_files`, whose
    authentication repository has, for each target repository, the given target file
    content at each of those commits and the `None` key's content at the parent commit.
    """
    main = make_commits(MAIN, 1)
    count = max(len(versions) for versions in target_files.values()) - 1
    steps = law(*({REPO1: (MAIN, main[0])} for _ in range(count)))
    pipeline = make_pipeline(steps, {})
    commits = [parent_commit] + [step.auth_commit for step in steps]
    contents = {
        (repo_name, commit): content
        for repo_name, versions in target_files.items()
        for commit, content in zip(commits, versions)
    }
    reads = []

    def safely_get_target_file(target_name, commit):
        reads.append((target_name, commit))
        content = contents.get((target_name, commit))
        return None if content is None else serialize_target_file(content)

    pipeline.state.users_auth_repo = SimpleNamespace(
        get_parent_commit=lambda _commit: parent_commit,
        safely_get_target_file=safely_get_target_file,
    )
    return pipeline, steps, reads


def test_check_target_files_appended_succeeds():
    pipeline, _, _ = _pipeline_with_target_files(
        {REPO1: [HISTORY[:1], HISTORY[:2], HISTORY], REPO2: [None, None, HISTORY[:1]]}
    )

    assert pipeline.check_target_files_appended() == UpdateStatus.SUCCESS
    assert pipeline.state.errors == []


def test_check_target_files_appended_fails_on_rewritten_target_file():
    pipeline, steps, _ = _pipeline_with_target_files(
        {REPO1: [HISTORY[:1], HISTORY[:2], [HISTORY[1], HISTORY[0]]]}
    )

    status = pipeline.check_target_files_appended()

    assert status == UpdateStatus.FAILED
    assert pipeline.state.event == Event.FAILED
    error = pipeline.state.errors[0]
    assert isinstance(error, TargetsHistoryRewrittenError)
    assert error.target_name == REPO1
    assert error.auth_commit == steps[1].auth_commit


def test_check_target_files_appended_compares_first_commit_with_its_parent():
    pipeline, steps, _ = _pipeline_with_target_files(
        {REPO1: [HISTORY[:1], HISTORY, HISTORY]}
    )

    assert pipeline.check_target_files_appended() == UpdateStatus.FAILED
    assert pipeline.state.errors[0].auth_commit == steps[0].auth_commit


def test_check_target_files_appended_from_first_commit_of_authentication_repository():
    pipeline, _, reads = _pipeline_with_target_files(
        {REPO1: [None, HISTORY[:1], HISTORY[:2]]}, parent_commit=None
    )

    assert pipeline.check_target_files_appended() == UpdateStatus.SUCCESS
    assert all(commit is not None for _, commit in reads)


def test_check_target_files_appended_reads_only_repositories_being_updated():
    pipeline, _, reads = _pipeline_with_target_files(
        {REPO1: [HISTORY[:1], HISTORY[:2]], REPO2: [None, HISTORY[:1]]}
    )
    del pipeline.state.temp_target_repositories[REPO2]

    assert pipeline.check_target_files_appended() == UpdateStatus.SUCCESS
    assert {target_name for target_name, _ in reads} == {REPO1}


def test_check_target_files_appended_without_auth_commits():
    pipeline, _, reads = _pipeline_with_target_files({REPO1: [HISTORY[:1], HISTORY]})
    pipeline.state.all_targets_auth_commits = []

    assert pipeline.check_target_files_appended() == UpdateStatus.SUCCESS
    assert reads == []
