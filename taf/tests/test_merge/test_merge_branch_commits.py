import json

from freezegun import freeze_time

from taf.api.merge import merge_branch_commits
from taf.api.targets import register_target_files
from taf.exceptions import MergeError
from taf.models.merge import build_policy

BRANCH_PATTERN = r"^spec/(?P<date>\d{4}-\d{2}-\d{2})(?P<idx>-\d{2})?$"
SOURCE_BRANCH = "spec/2024-01-05"
GATED_POLICY = build_policy(
    branch_pattern=BRANCH_PATTERN, gate="codified-date", no_capstone_roles=["targets"]
)
UNGATED_POLICY = build_policy(
    branch_pattern=BRANCH_PATTERN, no_capstone_roles=["targets"]
)
UNEVEN_LENGTHS_POLICY = build_policy(
    branch_pattern=BRANCH_PATTERN,
    no_capstone_roles=["targets"],
    allow_uneven_branch_lengths=True,
)


def _write_target(auth_repo, name, repo, gate_date=None, destination=None):
    target_file = auth_repo.path / "targets" / "namespace" / name
    data = {
        "branch": destination or repo.default_branch,
        "commit": repo.head_commit().value,
    }
    if gate_date is not None:
        data["codified-date"] = gate_date
    target_file.write_text(json.dumps(data))


def _sign(merge_auth_repo, keystore_delegations, pin_manager):
    register_target_files(
        path=merge_auth_repo.path,
        pin_manager=pin_manager,
        keystore=keystore_delegations,
        commit=True,
        push=False,
        auth_repo=merge_auth_repo,
        update_snapshot_and_timestamp=False,
    )


def _build_source_branch(
    merge_auth_repo,
    target1_repo,
    keystore_delegations,
    pin_manager,
    dates,
    destination=None,
):
    default_branch = merge_auth_repo.default_branch
    merge_auth_repo.checkout_branch(default_branch)
    merge_auth_repo.create_and_checkout_branch(SOURCE_BRANCH)

    target1_repo.checkout_branch(target1_repo.default_branch)
    target1_repo.create_and_checkout_branch(SOURCE_BRANCH)

    for i, gate_date in enumerate(dates):
        target1_repo.commit_empty(f"target1 commit {i}")
        _write_target(merge_auth_repo, "target1", target1_repo, gate_date, destination)
        _sign(merge_auth_repo, keystore_delegations, pin_manager)

    merge_auth_repo.checkout_branch(default_branch)


def test_merge_branch_commits_gated_by_date(
    merge_auth_repo, target1_repo, keystore_delegations, pin_manager, merge_root
):
    with freeze_time("2024-01-05"):
        _build_source_branch(
            merge_auth_repo,
            target1_repo,
            keystore_delegations,
            pin_manager,
            dates=["2024-01-05", "2024-01-10"],
        )

        default_branch = merge_auth_repo.default_branch
        default_head_before = merge_auth_repo.top_commit_of_branch(default_branch)

        merge_branch_commits(
            path=str(merge_auth_repo.path),
            pin_manager=pin_manager,
            policy=GATED_POLICY,
            library_dir=str(merge_root),
            keystore=keystore_delegations,
            deploy=False,
        )

        target1_default_commits = target1_repo.all_commits_on_branch(
            branch=target1_repo.default_branch
        )
        assert len(target1_default_commits) == 2

        default_head_after = merge_auth_repo.top_commit_of_branch(default_branch)
        assert default_head_after != default_head_before

    with freeze_time("2024-01-10"):
        merge_branch_commits(
            path=str(merge_auth_repo.path),
            pin_manager=pin_manager,
            policy=GATED_POLICY,
            library_dir=str(merge_root),
            keystore=keystore_delegations,
            deploy=False,
        )

        target1_default_commits = target1_repo.all_commits_on_branch(
            branch=target1_repo.default_branch
        )
        assert len(target1_default_commits) == 3


def test_merge_branch_commits_is_idempotent(
    merge_auth_repo, target1_repo, keystore_delegations, pin_manager, merge_root
):
    with freeze_time("2024-01-05"):
        _build_source_branch(
            merge_auth_repo,
            target1_repo,
            keystore_delegations,
            pin_manager,
            dates=["2024-01-05"],
        )

        merge_branch_commits(
            path=str(merge_auth_repo.path),
            pin_manager=pin_manager,
            policy=GATED_POLICY,
            library_dir=str(merge_root),
            keystore=keystore_delegations,
            deploy=False,
        )

        default_branch = merge_auth_repo.default_branch
        head_after_first_merge = merge_auth_repo.top_commit_of_branch(default_branch)

        merge_branch_commits(
            path=str(merge_auth_repo.path),
            pin_manager=pin_manager,
            policy=GATED_POLICY,
            library_dir=str(merge_root),
            keystore=keystore_delegations,
            deploy=False,
        )

        assert (
            merge_auth_repo.top_commit_of_branch(default_branch)
            == head_after_first_merge
        )


def test_merge_branch_commits_no_matching_branch_is_noop(
    merge_auth_repo, pin_manager, keystore_delegations, merge_root
):
    default_branch = merge_auth_repo.default_branch
    head_before = merge_auth_repo.top_commit_of_branch(default_branch)

    merge_branch_commits(
        path=str(merge_auth_repo.path),
        pin_manager=pin_manager,
        policy=UNGATED_POLICY,
        library_dir=str(merge_root),
        keystore=keystore_delegations,
        deploy=False,
    )

    assert merge_auth_repo.top_commit_of_branch(default_branch) == head_before


def test_merge_branch_commits_pushed_branch_filter_short_circuits(
    merge_auth_repo, target1_repo, keystore_delegations, pin_manager, merge_root
):
    with freeze_time("2024-01-05"):
        _build_source_branch(
            merge_auth_repo,
            target1_repo,
            keystore_delegations,
            pin_manager,
            dates=["2024-01-05"],
        )

        default_branch = merge_auth_repo.default_branch
        head_before = merge_auth_repo.top_commit_of_branch(default_branch)

        merge_branch_commits(
            path=str(merge_auth_repo.path),
            pin_manager=pin_manager,
            policy=GATED_POLICY,
            library_dir=str(merge_root),
            pushed_branch="unrelated-branch",
            keystore=keystore_delegations,
            deploy=False,
        )

        assert merge_auth_repo.top_commit_of_branch(default_branch) == head_before


def test_merge_branch_commits_repo_not_touched_drops_out(
    merge_auth_repo,
    target1_repo,
    target2_repo,
    keystore_delegations,
    pin_manager,
    merge_root,
):
    """A repo whose declared commit does not change (e.g. rdf that was not
    rebuilt) participates in signing but nothing moves for it."""
    default_branch = merge_auth_repo.default_branch
    merge_auth_repo.checkout_branch(default_branch)
    merge_auth_repo.create_and_checkout_branch(SOURCE_BRANCH)

    target1_repo.checkout_branch(target1_repo.default_branch)
    target1_repo.create_and_checkout_branch(SOURCE_BRANCH)
    target2_repo.checkout_branch(target2_repo.default_branch)
    target2_repo.create_and_checkout_branch(SOURCE_BRANCH)

    with freeze_time("2024-01-05"):
        target1_repo.commit_empty("target1 commit 0")
        target2_repo.commit_empty("target2 commit 0")
        _write_target(merge_auth_repo, "target1", target1_repo)
        _write_target(merge_auth_repo, "target2", target2_repo)
        _sign(merge_auth_repo, keystore_delegations, pin_manager)

        target1_repo.commit_empty("target1 commit 1")
        _write_target(merge_auth_repo, "target1", target1_repo)
        _sign(merge_auth_repo, keystore_delegations, pin_manager)

        merge_auth_repo.checkout_branch(default_branch)

        head_before = merge_auth_repo.top_commit_of_branch(default_branch)

        merge_branch_commits(
            path=str(merge_auth_repo.path),
            pin_manager=pin_manager,
            policy=UNEVEN_LENGTHS_POLICY,
            library_dir=str(merge_root),
            keystore=keystore_delegations,
            deploy=False,
        )

        assert merge_auth_repo.top_commit_of_branch(default_branch) != head_before
        assert (
            len(target1_repo.all_commits_on_branch(branch=target1_repo.default_branch))
            == 3
        )
        assert (
            len(target2_repo.all_commits_on_branch(branch=target2_repo.default_branch))
            == 2
        )


def test_merge_branch_commits_uneven_lengths_raises_by_default(
    merge_auth_repo,
    target1_repo,
    target2_repo,
    keystore_delegations,
    pin_manager,
    merge_root,
):
    """Without allow_uneven_branch_lengths, a repo whose commit count on the
    source branch differs from the others is an error, not a silent drop-out -
    the ordinary force-push signal that allow_uneven_branch_lengths is meant to
    bypass only for a deliberately uneven case (e.g. rdf's rebuild commit)."""
    default_branch = merge_auth_repo.default_branch
    merge_auth_repo.checkout_branch(default_branch)
    merge_auth_repo.create_and_checkout_branch(SOURCE_BRANCH)

    target1_repo.checkout_branch(target1_repo.default_branch)
    target1_repo.create_and_checkout_branch(SOURCE_BRANCH)
    target2_repo.checkout_branch(target2_repo.default_branch)
    target2_repo.create_and_checkout_branch(SOURCE_BRANCH)

    with freeze_time("2024-01-05"):
        target1_repo.commit_empty("target1 commit 0")
        target2_repo.commit_empty("target2 commit 0")
        _write_target(merge_auth_repo, "target1", target1_repo)
        _write_target(merge_auth_repo, "target2", target2_repo)
        _sign(merge_auth_repo, keystore_delegations, pin_manager)

        target1_repo.commit_empty("target1 commit 1")
        _write_target(merge_auth_repo, "target1", target1_repo)
        _sign(merge_auth_repo, keystore_delegations, pin_manager)

        merge_auth_repo.checkout_branch(default_branch)
        head_before = merge_auth_repo.top_commit_of_branch(default_branch)

        try:
            merge_branch_commits(
                path=str(merge_auth_repo.path),
                pin_manager=pin_manager,
                policy=UNGATED_POLICY,
                library_dir=str(merge_root),
                keystore=keystore_delegations,
                deploy=False,
            )
            assert False, "expected MergeError"
        except MergeError:
            pass

        assert merge_auth_repo.top_commit_of_branch(default_branch) == head_before


def test_merge_branch_commits_force_pushed_commit_raises(
    merge_auth_repo, target1_repo, keystore_delegations, pin_manager, merge_root
):
    with freeze_time("2024-01-05"):
        _build_source_branch(
            merge_auth_repo,
            target1_repo,
            keystore_delegations,
            pin_manager,
            dates=["2024-01-05"],
        )

        target1_repo.checkout_branch(SOURCE_BRANCH)
        target1_repo.reset_num_of_commits(1, hard=True)
        target1_repo.checkout_branch(target1_repo.default_branch)

        try:
            merge_branch_commits(
                path=str(merge_auth_repo.path),
                pin_manager=pin_manager,
                policy=UNGATED_POLICY,
                library_dir=str(merge_root),
                keystore=keystore_delegations,
                deploy=False,
            )
            assert False, "expected MergeError"
        except MergeError:
            pass


def test_merge_branch_commits_merges_commit_already_on_destination(
    merge_auth_repo, target1_repo, keystore_delegations, pin_manager, merge_root
):
    """Update-branch shape: the target repo's commit is already on its
    destination branch by the time the auth branch is built, so nothing
    moves for it, but the auth commit is still merged."""
    default_branch = merge_auth_repo.default_branch

    target1_repo.checkout_branch(target1_repo.default_branch)
    target1_repo.commit_empty("target1 commit 0")

    merge_auth_repo.checkout_branch(default_branch)
    merge_auth_repo.create_and_checkout_branch(SOURCE_BRANCH)
    _write_target(merge_auth_repo, "target1", target1_repo)
    _sign(merge_auth_repo, keystore_delegations, pin_manager)
    merge_auth_repo.checkout_branch(default_branch)

    head_before = merge_auth_repo.top_commit_of_branch(default_branch)

    merge_branch_commits(
        path=str(merge_auth_repo.path),
        pin_manager=pin_manager,
        policy=UNGATED_POLICY,
        library_dir=str(merge_root),
        keystore=keystore_delegations,
        deploy=False,
    )

    assert merge_auth_repo.top_commit_of_branch(default_branch) != head_before
    assert (
        len(target1_repo.all_commits_on_branch(branch=target1_repo.default_branch)) == 2
    )
