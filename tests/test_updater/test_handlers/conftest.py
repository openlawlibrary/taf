from taf.tests.conftest import TEST_DATA_PATH


from tuf.ngclient._internal import trusted_metadata_set
from pytest import fixture


HANDLERS_DATA_INPUT_DIR = TEST_DATA_PATH / "handler_inputs"
TYPES_DIR = TEST_DATA_PATH / "types"
UPDATE_TYPES_DIR = TYPES_DIR / "update"
UPDATE_TYPES_VALID_INPUT_DIR = UPDATE_TYPES_DIR / "valid"
UPDATE_TYPES_INVALID_INPUT_DIR = UPDATE_TYPES_DIR / "invalid"
REPO_HANDLERS_DATA_VALID_INPUT_IDR = HANDLERS_DATA_INPUT_DIR / "valid" / "repo"
UPDATE_HANDLERS_DATA_VALID_INPUT_IDR = HANDLERS_DATA_INPUT_DIR / "valid" / "update"
REPO_HANDLERS_DATA_INVALID_INPUT_IDR = HANDLERS_DATA_INPUT_DIR / "invalid" / "repo"
UPDATE_HANDLERS_DATA_INVALID_INPUT_IDR = HANDLERS_DATA_INPUT_DIR / "invalid" / "update"

original_tuf_trusted_metadata_set = trusted_metadata_set.TrustedMetadataSet


@fixture
def types_update_valid_inputs():
    """Paths to the type update's input json files"""
    return [input_path for input_path in UPDATE_TYPES_VALID_INPUT_DIR.glob("*.json")]


@fixture
def types_update_invalid_inputs():
    """Paths to the type update's input json files"""
    return [input_path for input_path in UPDATE_TYPES_INVALID_INPUT_DIR.glob("*.json")]


@fixture
def repo_handlers_valid_inputs():
    """Paths to the repo handler's input json files"""
    return [
        input_path for input_path in REPO_HANDLERS_DATA_VALID_INPUT_IDR.glob("*.json")
    ]


@fixture
def update_handlers_valid_inputs():
    """Paths to the update handler's input json files"""
    return [
        input_path for input_path in UPDATE_HANDLERS_DATA_VALID_INPUT_IDR.glob("*.json")
    ]


@fixture
def repo_handlers_invalid_inputs():
    """Paths to the repo handler's input json files"""
    return [
        input_path for input_path in REPO_HANDLERS_DATA_INVALID_INPUT_IDR.glob("*.json")
    ]


@fixture
def update_handlers_invalid_inputs():
    """Paths to the update handler's input json files"""
    return [
        input_path
        for input_path in UPDATE_HANDLERS_DATA_INVALID_INPUT_IDR.glob("*.json")
    ]
