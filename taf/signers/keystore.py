"""Keystore files: their names and private key URIs, loading their signers,
and generating the keys of new roles."""

import glob
import re
from os import getcwd
from pathlib import Path
from typing import List, Optional, Tuple, Union

import click
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from securesystemslib.signer import CryptoSigner, Signer, SSlibKey

from taf.auth_repo import AuthenticationRepository
from taf.exceptions import KeystoreError, SchemeNotSpecifiedError
from taf.log import taf_logger
from taf.models.types import Role
from taf.signers.base import InputNeeded, KeyStorage, load_signer
from taf.tuf.keys import _from_crypto, _get_legacy_keyid, generate_and_write_keypair
from taf.utils import write_private_file


class KeystoreStorage(KeyStorage):
    """The role's keystore files, e.g. targets1 and targets2.
    Generates the keystore files of a new role that can't be loaded, if the
    user wants that."""

    name = "keystore"
    priority = 0
    input_needed = InputNeeded.NONE

    def __init__(
        self,
        taf_repo: AuthenticationRepository,
        keystore_path: Optional[Path],
        skip_prompt: Optional[bool] = False,
    ):
        self.taf_repo = taf_repo
        self.keystore_path = keystore_path
        self.skip_prompt = skip_prompt

    def load_signers(
        self, role: str, keys: List[SSlibKey], threshold_reached: bool
    ) -> List[Signer]:
        if self.keystore_path is None:
            return []
        signers: List[Signer] = []
        key_names = sorted(get_keystore_keys_of_role(str(self.keystore_path), role))
        for key_name in key_names:
            loaded_keyids = [signer.public_key.keyid for signer in signers]
            missing_keys = [key for key in keys if key.keyid not in loaded_keyids]
            if not missing_keys:
                break
            signer = _load_signer_from_keystore(
                self.keystore_path, key_name, missing_keys
            )
            if signer is not None:
                signers.append(signer)
        return signers

    def setup_keys(self, role: Role) -> Tuple[List[Signer], List[SSlibKey]]:
        if self.keystore_path is None:
            taf_logger.error("No keystore provided and no default keystore found")
            raise KeyError("No keystore provided and no default keystore found")
        signers = []
        for key_num in range(role.number):
            key_name = get_key_name(role.name, key_num, role.number)
            signer, key_id = _setup_keystore_key(
                self.keystore_path,
                role.name,
                key_name,
                role.scheme,
                role.length,
                skip_prompt=self.skip_prompt,
            )
            signers.append(signer)
            self.taf_repo.add_key_name(key_name, key_id)
        return signers, []


def check_keystore_path_usable_in_uri(path: Union[str, Path]) -> None:
    """Raise KeystoreError if a keystore file's path can't be used in a URI.
    A URI ends at '#' or '?', so it would point to another file."""
    path = Path(path).expanduser().resolve()
    if "#" in str(path) or "?" in str(path):
        raise KeystoreError(f"Keystore path {path} can't contain '#' or '?'")


def create_signer_from_keystore_file(
    keystore: Union[str, Path], key_name: str, scheme: Optional[str] = None
) -> Signer:
    """Create the signer of a keystore file whose key is not in metadata yet"""
    path = Path(keystore, key_name).expanduser().resolve()
    private_key = load_pem_private_key(path.read_bytes(), None)
    public_key = _from_crypto(private_key.public_key(), scheme)
    return Signer.from_priv_key_uri(get_keystore_uri(keystore, key_name), public_key)


def default_keystore_path() -> str:
    keystore_path = str(Path(getcwd(), "keystore"))
    return keystore_path


def get_key_name(role_name: str, key_num: int, num_of_keys: int) -> str:
    """
    Return a keystore key's name based on the role's name and total number of signing keys,
    as well as the specified counter. If number of signing keys is one, return the role's name.
    If the number of signing keys is greater that one, return role's name + counter (root1, root2...)
    """
    if num_of_keys == 1:
        return role_name
    else:
        return role_name + str(key_num + 1)


def get_keystore_keys_of_role(keystore: str, role: str) -> List[str]:
    keystores_glob = f"{keystore}/{role}*"
    # Use glob to find matching files
    keystores = glob.glob(keystores_glob)
    pattern = r"^{}(?:\d+)?$".format(re.escape(role))

    # Iterate over the matching files
    return [
        Path(keystore_path).name
        for keystore_path in keystores
        if re.match(pattern, Path(keystore_path).name)
    ]


def get_keystore_uri(keystore: Union[str, Path], key_name: str) -> str:
    path = Path(keystore, key_name).expanduser().resolve()
    check_keystore_path_usable_in_uri(path)
    return f"{CryptoSigner.SCHEME}:{path.as_posix()}"


def load_signer_from_keystore_uri(
    keystore: Union[str, Path], key_name: str, public_keys: List[SSlibKey]
) -> Optional[Signer]:
    """Build a signer for a keystore file from its URI, for the first of
    public_keys that the file holds. Return None if none match."""
    uri = get_keystore_uri(keystore, key_name)
    try:
        return load_signer(uri, public_keys)
    except Exception as e:
        raise KeystoreError(f"Could not open keystore file {uri}: {e}") from e


def load_signer_from_private_keystore(
    keystore: Union[str, Path], key_name: str, scheme: Optional[str] = None
) -> Signer:
    """Load a keystore key that is not in metadata yet, through its URI"""
    key_path = Path(keystore, key_name).expanduser().resolve()
    if not key_path.is_file():
        raise KeystoreError(f"{str(key_path)} does not exist")
    try:
        return create_signer_from_keystore_file(keystore, key_name, scheme)
    except SchemeNotSpecifiedError:
        raise
    except Exception as e:
        raise KeystoreError(f"Could not open keystore file {key_path}: {e}") from e


def _load_signer_from_keystore(
    keystore_path, key_name, public_keys: List[SSlibKey]
) -> Optional[Signer]:
    if keystore_path is None:
        return None
    if (keystore_path / key_name).is_file():
        check_keystore_path_usable_in_uri(keystore_path / key_name)
        try:
            return load_signer_from_keystore_uri(keystore_path, key_name, public_keys)
        except KeystoreError as e:
            taf_logger.warning(str(e))

    return None


def _setup_keystore_key(
    keystore: Optional[Union[Path, str]],
    role_name: str,
    key_name: str,
    scheme: Optional[str],
    length: Optional[int],
    skip_prompt: Optional[bool],
) -> Tuple[Signer, str]:
    generate_new_keys = keystore is None
    signer = None

    if keystore is not None:
        check_keystore_path_usable_in_uri(Path(keystore, key_name))
        keystore_path = str(Path(keystore).expanduser().resolve())
        while signer is None:
            try:
                signer = load_signer_from_private_keystore(
                    keystore_path, key_name, scheme
                )
            except KeystoreError as e:
                print(e)

            if signer is None:
                generate_new_keys = skip_prompt is True or click.confirm(
                    "Generate new keys?"
                )
                if not generate_new_keys:
                    if click.confirm("Reuse existing key?"):
                        reused_key_name = input(
                            "Enter name of an existing keystore file: "
                        )
                        write_private_file(
                            Path(keystore, key_name),
                            Path(keystore, reused_key_name).read_bytes(),
                        )
                        Path(keystore, key_name + ".pub").write_bytes(
                            Path(keystore, reused_key_name + ".pub").read_bytes()
                        )
                    else:
                        raise KeystoreError(f"Could not load {key_name}")
                else:
                    break
    if generate_new_keys:
        if keystore is None:
            raise KeystoreError(
                f"Cannot generate {key_name}: no keystore to write it to"
            )
        generate_and_write_keypair(Path(keystore, key_name), scheme, length)
        signer = load_signer_from_private_keystore(keystore, key_name, scheme)

    if signer is not None:
        return signer, _get_legacy_keyid(signer.public_key)
    raise KeystoreError(f"Could not load signer {key_name}")
