from taf.yubikey.yubikey_manager import PinManager
import pytest
import json
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from taf.tuf.keys import load_signer_from_file

# from taf.tests import TEST_WITH_REAL_YK
from taf.utils import on_rm_error, run

TEST_DATA_PATH = Path(__file__).parent / "data"
TEST_DATA_REPOS_PATH = TEST_DATA_PATH / "repos"
TEST_DATA_ORIGIN_PATH = TEST_DATA_REPOS_PATH / "origin"
TEST_OUTPUT_PATH = TEST_DATA_PATH / "output"
KEYSTORES_PATH = TEST_DATA_PATH / "keystores"
KEYSTORE_PATH = KEYSTORES_PATH / "keystore"
WRONG_KEYSTORE_PATH = KEYSTORES_PATH / "wrong_keystore"
DELEGATED_ROLES_KEYSTORE_PATH = KEYSTORES_PATH / "delegated_roles_keystore"
CLIENT_DIR_PATH = TEST_DATA_REPOS_PATH / "client"
HANDLERS_DATA_INPUT_DIR = TEST_DATA_PATH / "handler_inputs"
TEST_INIT_DATA_PATH = Path(__file__).parent / "init_data"
REPOSITORY_DESCRIPTION_INPUT_DIR = TEST_DATA_PATH / "repository_description_inputs"
NO_YUBIKEYS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_yubikeys.json"
WITH_DELEGATIONS_NO_YUBIKEY = (
    REPOSITORY_DESCRIPTION_INPUT_DIR / "with_delegations_no_yubikeys.json"
)
REPOSITORIES_JSON_PATH = TEST_INIT_DATA_PATH / "repositories.json"
MIRRORS_JSON_PATH = TEST_INIT_DATA_PATH / "mirrors.json"

#: Branch name `git init` gives test repositories.
TESTS_DEFAULT_BRANCH = "main"


def _get_git_config(key):
    """Value git resolves for ``key`` right now, or "" when it is unset."""
    try:
        return run("git", "config", "--get", key) or ""
    except subprocess.CalledProcessError:
        return ""


@contextmanager
def deterministic_git_environment_context():
    """Isolate the git environment the tests run in. Yields the config path.

    Both variables are read by the ``git`` subprocess only; libgit2 honors
    neither, so pygit2 code paths still see the developer's real global config
    and still discover repositories above ``taf/tests``.

    ``GIT_CEILING_DIRECTORIES`` stops repository discovery at ``taf/tests``.
    Discovery walks upward and test repositories live inside the TAF checkout,
    so without it git answers about TAF's own repository whenever it is run
    against a path that is not a repository yet.

    ``GIT_CONFIG_GLOBAL`` points at a generated config and
    ``GIT_CONFIG_NOSYSTEM`` shuts out ``/etc/gitconfig``, so settings such as
    ``init.defaultBranch`` and the Git LFS filters come from here rather than
    from the machine. The developer's identity is carried over - resolved before
    the redirect, so it is what git would have used - because committing needs
    it.
    """
    identity = {key: _get_git_config(f"user.{key}") for key in ("name", "email")}

    monkeypatch = pytest.MonkeyPatch()
    config_dir = Path(tempfile.mkdtemp(prefix="taf-tests-gitconfig-"))
    config_path = config_dir / "gitconfig"

    lines = ["[init]", f"\tdefaultBranch = {TESTS_DEFAULT_BRANCH}"]
    if identity["name"] or identity["email"]:
        lines.append("[user]")
        for key, value in identity.items():
            if value:
                lines.append(f"\t{key} = {value}")
    config_path.write_text("\n".join(lines) + "\n")

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(TEST_DATA_PATH.parent))
    try:
        yield config_path
    finally:
        monkeypatch.undo()
        shutil.rmtree(config_dir, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def deterministic_git_environment():
    with deterministic_git_environment_context() as config_path:
        yield config_path


@pytest.fixture(scope="session", autouse=True)
def repo_dir(deterministic_git_environment):
    path = CLIENT_DIR_PATH
    if path.is_dir():
        shutil.rmtree(path, onerror=on_rm_error)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, onerror=on_rm_error)


@pytest.fixture(scope="session")
def keystore():
    """Create signer from some rsa test key."""
    return TEST_DATA_PATH / "keystores" / "keystore"


@pytest.fixture(scope="session")
def keystore_delegations():
    """Create signer from some rsa test key."""
    return TEST_DATA_PATH / "keystores" / "keystore_delegations"


@pytest.fixture(scope="session")
def mirrors_json_path():
    return MIRRORS_JSON_PATH


@pytest.fixture(scope="session")
def no_yubikeys_input():
    return json.loads(NO_YUBIKEYS_INPUT.read_text())


@pytest.fixture(scope="session")
def with_delegations_no_yubikeys_input():
    return json.loads(WITH_DELEGATIONS_NO_YUBIKEY.read_text())


@pytest.fixture(scope="session")
def with_delegations_no_yubikeys_path():
    return WITH_DELEGATIONS_NO_YUBIKEY


@pytest.fixture(scope="session")
def signers(keystore):
    return _load_signers_from_keystore(keystore)


@pytest.fixture(scope="session")
def signers_with_delegations(keystore_delegations):
    return _load_signers_from_keystore(keystore_delegations)


@pytest.fixture(scope="session")
def public_keys(signers):
    return {
        role_name: [signer.public_key for signer in signers]
        for role_name, signers in signers.items()
    }


@pytest.fixture(scope="session")
def public_keys_with_delegations(signers_with_delegations):
    return {
        role_name: [signer.public_key for signer in signers]
        for role_name, signers in signers_with_delegations.items()
    }


def _load_signers_from_keystore(keystore):
    def normalize_base_name(name):
        return re.sub(r"\d+$", "", name)

    signers = {}

    for file in keystore.iterdir():
        if file.is_file() and file.suffix == "":
            normalized_base_name = normalize_base_name(file.stem)

            if normalized_base_name not in signers:
                signers[normalized_base_name] = []
            signers[normalized_base_name].append(load_signer_from_file(file))
    return signers


@pytest.fixture(scope="session")
def repositories_json_template():
    return json.loads(Path(REPOSITORIES_JSON_PATH).read_text())


@pytest.fixture(autouse=True)
def repo_path(request, repo_dir):
    # Get the base directory path

    # Append the test name
    test_name = request.node.name
    full_path = repo_dir / test_name
    full_path.mkdir(parents=True)

    yield full_path
    shutil.rmtree(full_path, onerror=on_rm_error)


@pytest.fixture(scope="session", autouse=True)
def output_path():
    shutil.rmtree(TEST_OUTPUT_PATH, ignore_errors=True)
    TEST_OUTPUT_PATH.mkdir()
    yield TEST_OUTPUT_PATH
    shutil.rmtree(TEST_OUTPUT_PATH, onerror=on_rm_error)


@pytest.fixture(scope="session")
def pin_manager():
    return PinManager()


@pytest.fixture(scope="session")
def client_dir():
    return CLIENT_DIR_PATH


@pytest.fixture(scope="session")
def origin_dir():
    return TEST_DATA_ORIGIN_PATH


@pytest.fixture(scope="session")
def wrong_keystore():
    """Path of the wrong keystore"""
    return str(WRONG_KEYSTORE_PATH)
