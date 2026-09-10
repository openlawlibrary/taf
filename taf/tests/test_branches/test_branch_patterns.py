import pytest

from taf.branches import BranchPattern, select_branches

SPECULATIVE_PATTERN = BranchPattern(
    r"^publication\/(?P<pub_date>\d{4}-\d{2}(-\d{2})?(-\d{2})?)"
    r"\.(?P<spec_date>\d{4}-\d{2}-\d{2}(-\d{2})?)$"
)
PUBLICATION_PATTERN = BranchPattern(
    r"^publication\/(?P<pub_date>(\d{4}-\d{2}(-\d{2})?))(-\d{2})?$"
)
RDF_SPECULATIVE_PATTERN = BranchPattern(
    r"^rdf\/publication\/(?P<pub_date>\d{4}-\d{2}(-\d{2})?(-\d{2})?)"
    r"\.(?P<spec_date>\d{4}-\d{2}-\d{2}(-\d{2})?)$"
)
UPDATE_PATTERN = BranchPattern(
    r"^update\/(?P<role>(\w+))\.(?P<date>(\d{4}-\d{2}-\d{2}))(?P<idx>(-\d{2}))?$"
)


@pytest.mark.parametrize(
    "branch_name, expected",
    [
        ("publication/2019-10-01.2019-10-15", True),
        ("publication/2019-10-01-01.2019-10-15-01", True),
        ("publication/2019-10-11-02.2019-10-15-02", True),
        ("publication/2019-10.2019-10-15-01", True),
        ("rdf/publication/2019-10-01.2019-10-15", False),
        ("2019-12-01", False),
        ("publication/2019-10.2019-10-15-111", False),
        ("publication/2019-10.2019-10-15-aa", False),
        ("some random name", False),
    ],
)
def test_speculative_pattern_matches(branch_name, expected):
    assert SPECULATIVE_PATTERN.matches(branch_name) == expected


@pytest.mark.parametrize(
    "branch_name, expected",
    [
        ("rdf/publication/2019-10-01.2019-10-15", True),
        ("rdf/publication/2019-10-01-01.2019-10-15-01", True),
        ("rdf/publication/2019-10.2019-10-15-01", True),
        ("publication/2019-10-01.2019-10-15", False),
        ("rdf/publication/2019-10.2019-10-15-111", False),
        ("rdf/2019-12-01", False),
    ],
)
def test_rdf_speculative_pattern_matches(branch_name, expected):
    assert RDF_SPECULATIVE_PATTERN.matches(branch_name) == expected


@pytest.mark.parametrize(
    "branch_name, expected",
    [
        ("publication/2019-10", True),
        ("publication/2020-01", True),
        ("publication/2020-01-01", True),
        ("publication/2019-10-10-01", True),
        ("publication/2019-101", False),
        ("2019-10", False),
    ],
)
def test_publication_pattern_matches(branch_name, expected):
    assert PUBLICATION_PATTERN.matches(branch_name) == expected


def test_speculative_sort_key_orders_by_named_groups():
    branches = [
        "publication/2019-11-02.2019-12-01-01",
        "publication/2019-11-02.2019-12-01",
        "publication/2019-11-01.2019-11-04",
        "publication/2019-11.2019-11-04",
    ]
    ordered = sorted(branches, key=SPECULATIVE_PATTERN.sort_key, reverse=True)
    assert ordered == [
        "publication/2019-11-02.2019-12-01-01",
        "publication/2019-11-02.2019-12-01",
        "publication/2019-11-01.2019-11-04",
        "publication/2019-11.2019-11-04",
    ]


def test_group_returns_named_group_value():
    assert UPDATE_PATTERN.group("update/docs.2019-10-10-01", "role") == "docs"
    assert UPDATE_PATTERN.group("update/docs.2019-10-10-01", "date") == "2019-10-10"
    assert UPDATE_PATTERN.group("update/docs.2019-10-10-01", "idx") == "-01"
    assert UPDATE_PATTERN.group("not-a-branch", "role") is None


def test_has_group():
    assert UPDATE_PATTERN.has_group("role")
    assert not UPDATE_PATTERN.has_group("nonexistent")


def test_select_branches_returns_empty_list_when_none_match(repository):
    assert select_branches(repository, SPECULATIVE_PATTERN) == []


def test_select_branches_ungrouped(repository):
    initial_commit = repository.head_commit()

    branch1 = "publication/2019-01-01.2019-01-01"
    repository.create_branch(branch1)
    assert select_branches(repository, SPECULATIVE_PATTERN) == [branch1]

    repository.checkout_branch(branch1)
    assert select_branches(repository, SPECULATIVE_PATTERN) == [branch1]

    repository.checkout_branch(repository.default_branch)
    repository.commit_empty("Commit 1")

    branch2 = "publication/2019-01-01.2019-01-02"
    repository.create_branch(branch2)
    assert select_branches(repository, SPECULATIVE_PATTERN) == [branch2]

    repository.commit_empty("Commit 2")

    # branches off an older commit, even with a name that sorts later, do not win
    branch3 = "publication/2019-01-01.2019-03-03"
    repository.create_branch(branch3, initial_commit)
    assert select_branches(repository, SPECULATIVE_PATTERN) == [branch2]

    branch4 = "publication/2019-01-01.2019-01-04"
    repository.create_branch(branch4)
    assert select_branches(repository, SPECULATIVE_PATTERN) == [branch4]


def test_select_branches_ungrouped_uses_remotes(repository, clone_repository):
    branch = "publication/2019-01-01.2019-01-01"
    repository.create_branch(branch)

    clone_repository.clone_from_disk(repository.path, keep_remote=True)

    assert select_branches(clone_repository, SPECULATIVE_PATTERN) == [branch]
    assert (
        select_branches(clone_repository, SPECULATIVE_PATTERN, include_remotes=False)
        == []
    )


def test_select_branches_grouped_picks_newest_per_group(repository):
    repository.create_branch("update/docs.2019-10-10")
    repository.create_branch("update/docs.2019-10-10-01")
    repository.create_branch("update/assets.2019-10-11")
    repository.create_branch("unrelated")

    branches = select_branches(repository, UPDATE_PATTERN, group_by="role")

    assert branches == ["update/docs.2019-10-10-01", "update/assets.2019-10-11"]
