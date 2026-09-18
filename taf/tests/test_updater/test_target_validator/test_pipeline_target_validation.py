"""
The update pipeline's use of TargetValidator: building law steps and last validated
pointers from the loaded targets data, and recording the result in the update state.
"""

from taf.exceptions import TargetCommitMismatchError
from taf.tests.test_updater.test_target_validator.conftest import (
    AUTH_COMMIT_DATE,
    AUTH_REPO_NAME,
    MAIN,
    PUBLICATION,
    REPO1,
    REPO2,
    UnauthenticatedPolicy,
    law,
    make_commits,
    make_pipeline,
    targets_data_by_auth_commits,
)
from taf.updater.lifecycle_handlers import Event
from taf.updater.target_validator import LawStep, TargetPointer
from taf.updater.updater_pipeline import UpdateStatus


def test_get_law_steps_declares_targets_of_each_auth_commit():
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 2)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 1)
    steps = law(
        {REPO1: (MAIN, repo1_main[0]), REPO2: (MAIN, repo2_main[0])},
        {REPO1: (MAIN, repo1_main[1]), REPO2: (MAIN, repo2_main[0])},
    )

    assert make_pipeline(steps, {})._get_law_steps() == steps


def test_get_law_steps_omits_repositories_without_target_at_auth_commit():
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 2)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 1)
    steps = law(
        {REPO1: (MAIN, repo1_main[0])},
        {REPO1: (MAIN, repo1_main[1]), REPO2: (MAIN, repo2_main[0])},
    )

    law_steps = make_pipeline(steps, {})._get_law_steps()

    assert [set(step.targets) for step in law_steps] == [{REPO1}, {REPO1, REPO2}]


def test_get_law_steps_ignores_repositories_not_being_updated():
    """E.g. repositories excluded from the update."""
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 1)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 1)
    steps = law({REPO1: (MAIN, repo1_main[0]), REPO2: (MAIN, repo2_main[0])})

    law_steps = make_pipeline(steps, {}, repo_names=[REPO1])._get_law_steps()

    assert law_steps == [
        LawStep(  # type: ignore[call-arg]
            auth_commit=steps[0].auth_commit,
            targets={REPO1: TargetPointer(MAIN, repo1_main[0])},  # type: ignore[call-arg]
        )
    ]


def test_get_law_steps_uses_default_branch_if_target_has_no_branch():
    publication = make_commits(PUBLICATION, 1)
    steps = law({REPO1: (PUBLICATION, publication[0])})
    targets_data = targets_data_by_auth_commits(steps)
    del targets_data[REPO1][steps[0].auth_commit]["branch"]

    law_steps = make_pipeline(steps, {}, targets_data=targets_data)._get_law_steps()

    assert law_steps[0].targets[REPO1] == TargetPointer(MAIN, publication[0])  # type: ignore[call-arg]


def test_get_law_steps_without_auth_commits():
    assert make_pipeline([], {})._get_law_steps() == []


def test_get_last_validated_target_pointers_from_last_validated_commit():
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 2)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 2)
    steps = law(
        {REPO1: (MAIN, repo1_main[0]), REPO2: (MAIN, repo2_main[0])},
        {REPO1: (MAIN, repo1_main[1]), REPO2: (MAIN, repo2_main[1])},
    )

    pointers = make_pipeline(
        steps, {}, last_validated_commit=steps[0].auth_commit
    )._get_last_validated_target_pointers()

    assert pointers == {
        REPO1: TargetPointer(MAIN, repo1_main[0]),  # type: ignore[call-arg]
        REPO2: TargetPointer(MAIN, repo2_main[0]),  # type: ignore[call-arg]
    }


def test_get_last_validated_target_pointers_prefers_repository_last_validated_commit():
    """After an update that excluded some repositories, each can be validated up to a different commit."""
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 2)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 2)
    steps = law(
        {REPO1: (MAIN, repo1_main[0]), REPO2: (MAIN, repo2_main[0])},
        {REPO1: (MAIN, repo1_main[1]), REPO2: (MAIN, repo2_main[1])},
    )

    pointers = make_pipeline(
        steps,
        {},
        last_validated_commit=steps[1].auth_commit,
        last_validated_data={REPO2: steps[0].auth_commit.value},
    )._get_last_validated_target_pointers()

    assert pointers == {
        REPO1: TargetPointer(MAIN, repo1_main[1]),  # type: ignore[call-arg]
        REPO2: TargetPointer(MAIN, repo2_main[0]),  # type: ignore[call-arg]
    }


def test_get_last_validated_target_pointers_omits_repositories_never_validated():
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 1)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 1)
    steps = law(
        {REPO1: (MAIN, repo1_main[0])},
        {REPO1: (MAIN, repo1_main[0]), REPO2: (MAIN, repo2_main[0])},
    )

    assert make_pipeline(steps, {})._get_last_validated_target_pointers() == {}
    assert make_pipeline(
        steps, {}, last_validated_commit=steps[0].auth_commit
    )._get_last_validated_target_pointers() == {
        REPO1: TargetPointer(MAIN, repo1_main[0])  # type: ignore[call-arg]
    }


def test_get_last_validated_target_pointers_uses_default_branch_if_target_has_no_branch():
    publication = make_commits(PUBLICATION, 1)
    steps = law({REPO1: (PUBLICATION, publication[0])})
    targets_data = targets_data_by_auth_commits(steps)
    del targets_data[REPO1][steps[0].auth_commit]["branch"]

    pointers = make_pipeline(
        steps,
        {},
        targets_data=targets_data,
        last_validated_commit=steps[0].auth_commit,
    )._get_last_validated_target_pointers()

    assert pointers == {REPO1: TargetPointer(MAIN, publication[0])}  # type: ignore[call-arg]


def test_validate_target_repositories_records_validated_state():
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 2)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 1)
    steps = law(
        {REPO1: (MAIN, repo1_main[0])},
        {REPO1: (MAIN, repo1_main[1]), REPO2: (MAIN, repo2_main[0])},
    )
    pipeline = make_pipeline(
        steps, {REPO1: {MAIN: repo1_main}, REPO2: {MAIN: repo2_main}}
    )

    status = pipeline.validate_target_repositories()

    state = pipeline.state
    assert status == UpdateStatus.SUCCESS
    assert state.errors == []
    assert state.validated_auth_commits == [step.auth_commit for step in steps]
    assert state.validated_commits_per_target_repos_branches == {
        REPO1: {MAIN: repo1_main},
        REPO2: {MAIN: repo2_main},
    }
    assert state.last_validated_data_per_repositories == {
        REPO1: {"commit": repo1_main[1], "branch": MAIN},
        REPO2: {"commit": repo2_main[0], "branch": MAIN},
    }


def test_validate_target_repositories_continues_from_last_validated_commit():
    main = make_commits(MAIN, 3)
    steps = law(
        {REPO1: (MAIN, main[0])}, {REPO1: (MAIN, main[1])}, {REPO1: (MAIN, main[2])}
    )
    pipeline = make_pipeline(
        steps[1:],
        {REPO1: {MAIN: main}},
        repo_names=[REPO1],
        targets_data=targets_data_by_auth_commits(steps),
        last_validated_commit=steps[0].auth_commit,
    )

    status = pipeline.validate_target_repositories()

    assert status == UpdateStatus.SUCCESS
    assert pipeline.state.validated_commits_per_target_repos_branches == {
        REPO1: {MAIN: main[1:]}
    }


def test_validate_target_repositories_state_defaults_to_empty_for_unvalidated_repositories():
    """Later steps look up every target repository in these, validated or not."""
    main = make_commits(MAIN, 1)
    pipeline = make_pipeline(law({REPO1: (MAIN, main[0])}), {REPO1: {MAIN: main}})

    pipeline.validate_target_repositories()

    assert pipeline.state.validated_commits_per_target_repos_branches[REPO2] == {}
    assert pipeline.state.last_validated_data_per_repositories[REPO2] == {}


def test_validate_target_repositories_replaces_state_from_previous_validation():
    main = make_commits(MAIN, 1)
    stale = make_commits("stale", 1)[0]
    pipeline = make_pipeline(law({REPO1: (MAIN, main[0])}), {REPO1: {MAIN: main}})
    pipeline.state.validated_auth_commits = [stale]
    pipeline.state.validated_commits_per_target_repos_branches = {
        REPO2: {MAIN: [stale]}
    }
    pipeline.state.last_validated_data_per_repositories = {
        REPO2: {"commit": stale, "branch": MAIN}
    }

    pipeline.validate_target_repositories()

    assert stale not in pipeline.state.validated_auth_commits
    assert REPO2 not in pipeline.state.validated_commits_per_target_repos_branches
    assert REPO2 not in pipeline.state.last_validated_data_per_repositories


def test_validate_target_repositories_partial_keeps_validated_progress():
    main = make_commits(MAIN, 4)
    steps = law(
        {REPO1: (MAIN, main[0])}, {REPO1: (MAIN, main[1])}, {REPO1: (MAIN, main[3])}
    )
    pipeline = make_pipeline(steps, {REPO1: {MAIN: main}}, repo_names=[REPO1])

    status = pipeline.validate_target_repositories()

    state = pipeline.state
    assert status == UpdateStatus.PARTIAL
    assert state.event == Event.PARTIAL
    assert len(state.errors) == 1
    assert isinstance(state.errors[0], TargetCommitMismatchError)
    assert state.validated_auth_commits == [steps[0].auth_commit, steps[1].auth_commit]
    assert state.validated_commits_per_target_repos_branches == {
        REPO1: {MAIN: main[:2]}
    }
    assert state.last_validated_data_per_repositories == {
        REPO1: {"commit": main[1], "branch": MAIN}
    }


def test_validate_target_repositories_fails_on_first_auth_commit():
    main = make_commits(MAIN, 2)
    steps = law({REPO1: (MAIN, main[1])})
    pipeline = make_pipeline(steps, {REPO1: {MAIN: main}}, repo_names=[REPO1])

    status = pipeline.validate_target_repositories()

    assert status == UpdateStatus.FAILED
    assert pipeline.state.event == Event.FAILED
    assert pipeline.state.validated_auth_commits == []


def test_validate_target_repositories_error_names_auth_repo_and_commit_date():
    main = make_commits(MAIN, 2)
    steps = law({REPO1: (MAIN, main[1])})
    pipeline = make_pipeline(steps, {REPO1: {MAIN: main}}, repo_names=[REPO1])

    pipeline.validate_target_repositories()

    error = pipeline.state.errors[0]
    assert error.auth_repo_name == AUTH_REPO_NAME
    assert error.commit_date == AUTH_COMMIT_DATE


def test_validate_target_repositories_resolves_unauthenticated_commits_per_repository_and_auth_commit():
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 3)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 2)
    steps = law(
        {REPO1: (MAIN, repo1_main[0]), REPO2: (MAIN, repo2_main[0])},
        {REPO1: (MAIN, repo1_main[2]), REPO2: (MAIN, repo2_main[1])},
    )
    policy = UnauthenticatedPolicy([(REPO1, steps[1].auth_commit)])
    pipeline = make_pipeline(
        steps,
        {REPO1: {MAIN: repo1_main}, REPO2: {MAIN: repo2_main}},
        is_unauthenticated_allowed=policy,
    )

    status = pipeline.validate_target_repositories()

    assert status == UpdateStatus.SUCCESS
    assert policy.calls == [(REPO1, steps[1].auth_commit)]
