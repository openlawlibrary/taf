
from taf.tuf.keys import load_public_key_from_file, load_signer_from_file
from taf.tests.conftest import DELEGATED_ROLES_KEYSTORE_PATH, KEYSTORE_PATH, origin_repos_group

from pytest import fixture




def _load_key(keystore_path, key_name, scheme):
    """Load private and public keys of the given name"""
    key = load_public_key_from_file(
        keystore_path / f"{key_name}.pub"
    )
    priv_key = load_signer_from_file(
        keystore_path / key_name
    )
    key["keyval"]["private"] = priv_key["keyval"]["private"]
    return key



# @fixture(scope="session", autouse=True)
# def repository_test_repositories():
#     test_dir = "test-repository"
#     with origin_repos_group(test_dir) as origins:
#         yield origins

# @fixture
# def snapshot_key():
#     """Snapshot key."""
#     return _load_key(KEYSTORE_PATH, "snapshot", "rsa-pkcs1v15-sha256")


# @fixture
# def timestamp_key():
#     """Timestamp key."""
#     return _load_key(KEYSTORE_PATH, "timestamp", "rsa-pkcs1v15-sha256")


# @fixture
# def targets_key():
#     """Targets key."""
#     return _load_key(KEYSTORE_PATH, "targets", "rsa-pkcs1v15-sha256")


# @fixture
# def delegated_role11_key():
#     return _load_key(
#         DELEGATED_ROLES_KEYSTORE_PATH,
#         "delegated_role11",
#         "rsa-pkcs1v15-sha256",
#     )


# @fixture
# def delegated_role12_key():
#     return _load_key(
#         DELEGATED_ROLES_KEYSTORE_PATH,
#         "delegated_role12",
#         "rsa-pkcs1v15-sha256",
#     )


# @fixture
# def delegated_role13_key():
#     return _load_key(
#         DELEGATED_ROLES_KEYSTORE_PATH,
#         "delegated_role13",
#         "rsa-pkcs1v15-sha256",
#     )


# @fixture
# def delegated_role2_key():
#     return _load_key(
#         DELEGATED_ROLES_KEYSTORE_PATH,
#         "delegated_role2",
#         "rsa-pkcs1v15-sha256",
#     )


# @fixture
# def inner_delegated_role_key():
#     return _load_key(
#         DELEGATED_ROLES_KEYSTORE_PATH,
#         "inner_delegated_role",
#         "rsa-pkcs1v15-sha256",
#     )
