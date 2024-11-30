# import pytest
# from taf.tools.yubikey.yubikey_utils import (
#     Root1YubiKey,
#     Root2YubiKey,
#     Root3YubiKey,
#     TargetYubiKey,
# )
# from taf.tests.conftest import TEST_DATA_PATH

# KEYSTORES_PATH = TEST_DATA_PATH / "keystores"
# KEYSTORE_PATH = KEYSTORES_PATH / "keystore"
# WRONG_KEYSTORE_PATH = KEYSTORES_PATH / "wrong_keystore"
# DELEGATED_ROLES_KEYSTORE_PATH = KEYSTORES_PATH / "delegated_roles_keystore"
# HANDLERS_DATA_INPUT_DIR = TEST_DATA_PATH / "handler_inputs"


# @pytest.fixture
# def delegated_roles_keystore():
#     """Path of the keystore with keys of delegated roles"""
#     return str(DELEGATED_ROLES_KEYSTORE_PATH)


# @pytest.fixture
# def targets_yk(pytestconfig):
#     """Targets YubiKey."""
#     return TargetYubiKey(KEYSTORE_PATH, pytestconfig.option.signature_scheme)


# @pytest.fixture
# def root1_yk(pytestconfig):
#     """Root1 YubiKey."""
#     return Root1YubiKey(KEYSTORE_PATH, pytestconfig.option.signature_scheme)


# @pytest.fixture
# def root2_yk(pytestconfig):
#     """Root2 YubiKey."""
#     return Root2YubiKey(KEYSTORE_PATH, pytestconfig.option.signature_scheme)


# @pytest.fixture
# def root3_yk(pytestconfig):
#     """Root3 YubiKey."""
#     return Root3YubiKey(KEYSTORE_PATH, pytestconfig.option.signature_scheme)


# @pytest.fixture
# def snapshot_key(pytestconfig):
#     """Snapshot key."""
#     return _load_key(KEYSTORE_PATH, "snapshot", pytestconfig.option.signature_scheme)


# @pytest.fixture
# def timestamp_key(pytestconfig):
#     """Timestamp key."""
#     return _load_key(KEYSTORE_PATH, "timestamp", pytestconfig.option.signature_scheme)


# @pytest.fixture
# def targets_key(pytestconfig):
#     """Targets key."""
#     return _load_key(KEYSTORE_PATH, "targets", pytestconfig.option.signature_scheme)


# @pytest.fixture
# def delegated_role11_key(pytestconfig):
#     return _load_key(
#         DELEGATED_ROLES_KEYSTORE_PATH,
#         "delegated_role11",
#         pytestconfig.option.signature_scheme,
#     )


# @pytest.fixture
# def delegated_role12_key(pytestconfig):
#     return _load_key(
#         DELEGATED_ROLES_KEYSTORE_PATH,
#         "delegated_role12",
#         pytestconfig.option.signature_scheme,
#     )


# @pytest.fixture
# def delegated_role13_key(pytestconfig):
#     return _load_key(
#         DELEGATED_ROLES_KEYSTORE_PATH,
#         "delegated_role13",
#         pytestconfig.option.signature_scheme,
#     )


# @pytest.fixture
# def delegated_role2_key(pytestconfig):
#     return _load_key(
#         DELEGATED_ROLES_KEYSTORE_PATH,
#         "delegated_role2",
#         pytestconfig.option.signature_scheme,
#     )


# @pytest.fixture
# def inner_delegated_role_key(pytestconfig):
#     return _load_key(
#         DELEGATED_ROLES_KEYSTORE_PATH,
#         "inner_delegated_role",
#         pytestconfig.option.signature_scheme,
#     )
