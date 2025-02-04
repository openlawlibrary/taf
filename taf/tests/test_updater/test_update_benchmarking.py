import pytest
from taf.tests.test_updater.test_clone.test_clone_valid import (
    test_clone_valid_happy_path,
)


@pytest.mark.skip(reason="benchmarking disabled for time being")
@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "is_test_repo": True,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_benchmark_clone_valid_happy_path(origin_auth_repo, client_dir, benchmark):
    benchmark(test_clone_valid_happy_path, origin_auth_repo, client_dir)
