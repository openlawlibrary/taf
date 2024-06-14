import pytest
from taf.tests.test_updater.update_utils import update_and_check_commit_shas
from taf.updater.types.update import OperationType

@pytest.mark.parametrize("origin_auth_repo", [
    {"setup_type": "all_files_initially", "targets_config": [{"name": "target1"}, {"name": "target2"}]},
    {"setup_type": "no_info_json", "targets_config": [{"name": "target1"}, {"name": "target2"}]},
    {"setup_type": "mirrors_added_later", "targets_config": [{"name": "target1"}, {"name": "target2"}]},
    {"setup_type": "repositories_and_mirrors_added_later", "targets_config": [{"name": "target1"}, {"name": "target2"}]},
    {"setup_type": "no_target_repositories", "targets_config": [{"name": "target1"}, {"name": "target2"}]},

], indirect=True)
def test_clone_expect_valid(origin_auth_repo, client_dir):

    update_and_check_commit_shas(
        OperationType.CLONE,
        None,
        origin_auth_repo,
        client_dir,
    )
