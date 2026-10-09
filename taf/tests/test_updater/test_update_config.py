import pytest

from taf.log import taf_logger
from taf.updater.types.update import OperationType
from taf.updater.updater import UpdateConfig


@pytest.mark.parametrize(
    "only_validate, expect_warning", [(False, True), (True, False)]
)
def test_update_config_exclude_filter(tmp_path, only_validate, expect_warning):
    warnings = []
    handler_id = taf_logger.add(warnings.append, level="WARNING", format="{message}")
    try:
        config = UpdateConfig(
            operation=OperationType.UPDATE,
            path=tmp_path,
            exclude_filter="repo.get('archived')",
            only_validate=only_validate,
        )
    finally:
        taf_logger.remove(handler_id)

    if expect_warning:
        assert config.exclude_filter is None
        assert any("exclude_filter is ignored" in w for w in warnings)
    else:
        assert config.exclude_filter == "repo.get('archived')"
        assert not warnings
