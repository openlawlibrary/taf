from collections import defaultdict
from logging import INFO
from typing import Dict, List, Optional, Tuple
import click
from pathlib import Path
from logdecorator import log_on_start
from taf.auth_repo import AuthenticationRepository
from taf.log import taf_logger
from taf.models.types import Role, RolesIterator
from taf.models.models import TAFKey
from taf.models.types import DelegatedRole, MainRoles, UserKeyData
from taf.repository_tool import Repository
from taf.yubikey import get_key_serial_by_id
from tuf.repository_tool import generate_and_write_unencrypted_rsa_keypair
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import (
    KeystoreError,
    SigningError,
    YubikeyError,
)
from taf.keystore import (
    key_cmd_prompt,
    read_private_key_from_keystore,
    read_public_key_from_keystore,
)
from taf import YubikeyMissingLibrary
from tuf.sig import generate_rsa_signature
from securesystemslib import keys

try:
    import taf.yubikey as yk
    from taf.yubikey import export_yk_certificate
except ImportError:
    taf_logger.warning(
        "WARNING: yubikey-manager dependency not installed. You will not be able to use YubiKeys."
    )
    yk = YubikeyMissingLibrary()


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


def get_metadata_key_info(certs_dir: str, key_id: str) -> TAFKey:
    """
    Read and return information about the specified key read from a certificate
    file whose name matches that key's id.
    """
    cert_path = Path(certs_dir, key_id + ".cert")
    if cert_path.exists():
        cert_pem = cert_path.read_bytes()
        return TAFKey(key_id, **_extract_x509(cert_pem))

    return TAFKey(key_id)


def _extract_x509(cert_pem: bytes) -> Dict:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend

    cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

    def _get_attr(oid):
        attrs = cert.subject.get_attributes_for_oid(oid)
        return attrs[0].value if len(attrs) > 0 else ""

    return {
        "name": _get_attr(x509.OID_COMMON_NAME),
        "organization": _get_attr(x509.OID_ORGANIZATION_NAME),
        "country": _get_attr(x509.OID_COUNTRY_NAME),
        "state": _get_attr(x509.OID_STATE_OR_PROVINCE_NAME),
        "locality": _get_attr(x509.OID_LOCALITY_NAME),
        "valid_from": cert.not_valid_before.strftime("%Y-%m-%d"),
        "valid_to": cert.not_valid_after.strftime("%Y-%m-%d"),
    }


def load_sorted_keys_of_new_roles(
    auth_repo: AuthenticationRepository,
    roles: MainRoles | DelegatedRole,
    yubikeys_data: dict[str, UserKeyData],
    keystore: str,
    yubikeys: dict[str, dict] = None,
    existing_roles: list[str] = None,
):
    """
    Load signing keys of roles - first those stored on YubiKeys to avoid entering pins
    if there is something wrong with keystore files, then from keystore files.
    Recursively load keys of all delegated roles of target roles.

    Arguments:
        auth_repo: Authentication repository's instance
        roles: MainRoles object (including root, targets, snapshot and timestamp) or a particular delegated role
        yubikeys_data: Contains a mapping of a YubiKey's name to additional details. There names
            are used to link roles to YubiKeys that are used to sign the corresponding metadata.
            If additional details contain the public key, a user will not have to insert that YubiKey
            (provided that it's not necessary given the threshold of signing keys)
        keystore: keystore path
        yubikeys:(optional): A dictionary containing previously loaded YubiKeys used to save already entered pins
        existing_roles (optional): A list of roles whose keys were already loaded

    Side Effects:
        Populates loaded YubiKeys database located in `yubikey.py`

    Returns:
        Signing and verification keys of roles
    """

    def _sort_roles(roles):
        keystore_roles = []
        yubikey_roles = []
        for role in RolesIterator(roles):
            if role.is_yubikey:
                yubikey_roles.append(role)
            else:
                keystore_roles.append(role)
        return keystore_roles, yubikey_roles

    if yubikeys is None:
        yubikeys = defaultdict(dict)
    # load and/or generate all keys first
    if existing_roles is None:
        existing_roles = []
    try:
        keystore_roles, yubikey_roles = _sort_roles(roles)
        signing_keys = {}
        verification_keys = {}

        for role in keystore_roles:
            if role.name in existing_roles:
                continue
            keystore_keys, _ = setup_roles_keys(role, auth_repo.path, keystore=keystore)
            for public_key, private_key in keystore_keys:
                signing_keys.setdefault(role.name, []).append(private_key)
                verification_keys.setdefault(role.name, []).append(public_key)

        for role in yubikey_roles:
            if role.name in existing_roles:
                continue
            _, yubikey_keys = setup_roles_keys(
                role,
                certs_dir=auth_repo.certs_dir,
                yubikeys=yubikeys,
                users_yubikeys_details=yubikeys_data,
            )
            verification_keys[role.name] = yubikey_keys
        return signing_keys, verification_keys
    except KeystoreError as e:
        print(f"Creation of repository failed: {e}")
        return


@log_on_start(INFO, "Loading signing keys of '{role:s}'", logger=taf_logger)
def load_signing_keys(
    taf_repo: Repository,
    role: str,
    keystore: Optional[str] = None,
    loaded_yubikeys: Optional[Dict] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    prompt_for_keys: Optional[bool] = False,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Load role's signing keys. Make sure that at least the threshold of keys was
    loaded, but allow loading more keys (so that a metadata file can be signed
    by all of the role's keys if the user wants that)
    """
    threshold = taf_repo.get_role_threshold(role)
    signing_keys_num = len(taf_repo.get_role_keys(role))
    all_loaded = False
    num_of_signatures = 0
    keys = []
    yubikeys = []

    # first try to sign using yubikey
    # if that is not possible, try to load key from a keystore file
    # if the keystore file is not found, ask the user if they want to sign
    # using yubikey and to insert it if that is the case

    if keystore is not None:
        keystore = Path(keystore).expanduser().resolve()
    else:
        print("Keystore location not provided")

    def _load_from_keystore(key_name):
        if keystore is None:
            return None
        if (keystore / key_name).is_file():
            try:
                key = read_private_key_from_keystore(
                    keystore, key_name, num_of_signatures, scheme
                )
                # load only valid keys
                if taf_repo.is_valid_metadata_key(role, key, scheme=scheme):
                    return key
            except KeystoreError:
                pass
        return None

    def _load_and_append_yubikeys(key_name, role, retry_on_failure):
        public_key, _ = yk.yubikey_prompt(
            key_name,
            role,
            taf_repo,
            loaded_yubikeys=loaded_yubikeys,
            retry_on_failure=retry_on_failure,
        )

        if public_key is not None:
            yubikeys.append(public_key)
            print(f"Successfully loaded {key_name} from inserted YubiKey")

        return public_key is not None

    while not all_loaded and num_of_signatures < signing_keys_num:
        if signing_keys_num == 1:
            key_name = role
        else:
            key_name = f"{role}{num_of_signatures + 1}"
        if num_of_signatures >= threshold:
            all_loaded = not (
                click.confirm(
                    f"Threshold of {role} keys reached. Do you want to load more {role} keys?"
                )
            )
        if not all_loaded:
            key = _load_from_keystore(key_name)
            if key is not None:
                keys.append(key)
                num_of_signatures += 1
                continue

            if _load_and_append_yubikeys(key_name, role, False):
                num_of_signatures += 1
                continue

            if click.confirm(f"Sign {role} using YubiKey(s)?"):
                _load_and_append_yubikeys(key_name, role, True)
                num_of_signatures += 1
                continue

            if prompt_for_keys and click.confirm(f"Manually enter {role} key?"):
                key = key_cmd_prompt(key_name, role, taf_repo, keys, scheme)
                keys.append(key)
                num_of_signatures += 1
            else:
                raise SigningError(f"Cannot load keys of role {role}")

    return keys, yubikeys


def setup_roles_keys(
    role: Role,
    certs_dir: Optional[str] = None,
    keystore: Optional[str] = None,
    yubikeys: Optional[Dict] = None,
    users_yubikeys_details: Optional[Dict[str, UserKeyData]] = None,
):
    yubikey_keys = []
    keystore_keys = []

    yubikey_ids = role.yubikeys

    is_yubikey = bool(yubikey_ids)

    if is_yubikey:
        loaded_keys_num = 0
        yk_with_public_key = {}
        for key_id in yubikey_ids:
            public_key = users_yubikeys_details[key_id].public
            if public_key:
                scheme = users_yubikeys_details[key_id].scheme
                public_key = keys.import_rsakey_from_public_pem(public_key, scheme)
                # check if signing key already loaded too
                if not get_key_serial_by_id(key_id):
                    yk_with_public_key[key_id] = public_key
                else:
                    loaded_keys_num += 1
            else:
                key_scheme = users_yubikeys_details[key_id].scheme or role.scheme
                public_key = _setup_yubikey(
                    yubikeys, role.name, key_id, key_scheme, certs_dir
                )
                loaded_keys_num += 1
            yubikey_keys.append(public_key)
        if loaded_keys_num < role.threshold:
            print(f"Threshold of role {role.name} is {role.threshold}")
            while loaded_keys_num < role.threshold:
                loaded_keys = []
                for key_id, public_key in yk_with_public_key.items():
                    if _load_and_verify_yubikey(
                        yubikeys, role.name, key_id, public_key
                    ):
                        loaded_keys_num += 1
                        loaded_keys.append(key_id)
                    if loaded_keys_num == role.threshold:
                        break
                if loaded_keys_num < role.threshold:
                    if not click.confirm(
                        f"Threshold of sining keys of role {role.name} not reached. Continue?"
                    ):
                        raise SigningError("Not enough signing keys")
                    for key_id in loaded_keys:
                        yk_with_public_key.pop(key_id)
    else:
        for key_num in range(role.number):
            key_name = get_key_name(role.name, key_num, role.number)
            public_key, private_key = _setup_keystore_key(
                keystore, role.name, key_name, key_num, role.scheme, role.length, None
            )
            keystore_keys.append((public_key, private_key))
    return keystore_keys, yubikey_keys


def _setup_keystore_key(
    keystore: str,
    role_name: str,
    key_name: str,
    key_num: int,
    scheme: str,
    length: int,
    password: str,
) -> Tuple[Dict, Dict]:
    # if keystore exists, load the keys
    generate_new_keys = keystore is None
    public_key = private_key = None

    def _invalid_key_message(key_name, keystore, is_public):
        extension = ".pub" if is_public else ""
        key_path = Path(keystore, f"{key_name}{extension}")
        if key_path.is_file():
            if is_public:
                print(f"Could not load public key {key_path}")
            else:
                print(f"Could not load private key {key_path}")
        else:
            print(f"{key_path} is not a file!")

    if keystore is not None:
        keystore = Path(keystore).expanduser().resolve()
        while public_key is None and private_key is None:
            try:
                public_key = read_public_key_from_keystore(keystore, key_name, scheme)
            except KeystoreError:
                _invalid_key_message(key_name, keystore, True)
            try:
                private_key = read_private_key_from_keystore(
                    keystore,
                    key_name,
                    key_num=key_num,
                    scheme=scheme,
                    password=password,
                )
            except KeystoreError:
                _invalid_key_message(key_name, keystore, False)

            if public_key is None or private_key is None:
                generate_new_keys = click.confirm("Generate new keys?")
                if not generate_new_keys:
                    if click.confirm("Reuse existing key?"):
                        reused_key_name = input(
                            "Enter name of an existing keystore file: "
                        )
                        # copy existing private and public keys to the new files
                        Path(keystore, key_name).write_bytes(
                            Path(keystore, reused_key_name).read_bytes()
                        )
                        Path(keystore, key_name + ".pub").write_bytes(
                            Path(keystore, reused_key_name + ".pub").read_bytes()
                        )
                    else:
                        raise KeystoreError(f"Could not load {key_name}")
                else:
                    break
    if generate_new_keys:
        if keystore is not None and click.confirm("Write keys to keystore files?"):
            if password is None:
                password = input(
                    "Enter keystore password and press ENTER (can be left empty)"
                )
            generate_and_write_unencrypted_rsa_keypair(
                filepath=str(Path(keystore) / key_name), bits=length
            )
            public_key = read_public_key_from_keystore(keystore, key_name, scheme)
            private_key = read_private_key_from_keystore(
                keystore, key_name, key_num=key_num, scheme=scheme, password=password
            )
        else:
            key = generate_rsa_signature(bits=length, scheme=scheme)
            print(f"{role_name} key:\n\n{key['keyval']['private']}\n\n")
            public_key = private_key = key

    return public_key, private_key


def _setup_yubikey(
    yubikeys: Dict, role_name: str, key_name: str, scheme: str, certs_dir: str
) -> Dict:
    while True:
        print(f"Registering keys for {key_name}")
        use_existing = click.confirm("Do you want to reuse already set up Yubikey?")
        if not use_existing:
            if not click.confirm(
                "WARNING - this will delete everything from the inserted key. Proceed?"
            ):
                if click.confirm("Cancel?"):
                    raise YubikeyError("Yubikey setup canceled")
                continue
        key, serial_num = yk.yubikey_prompt(
            key_name,
            role_name,
            taf_repo=None,
            registering_new_key=True,
            creating_new_key=not use_existing,
            loaded_yubikeys=yubikeys,
            pin_confirm=True,
            pin_repeat=True,
        )

        if not use_existing:
            key = yk.setup_new_yubikey(serial_num, scheme)

        export_yk_certificate(certs_dir, key)
        return key


def _load_and_verify_yubikey(
    yubikeys: Dict, role_name: str, key_name: str, public_key
) -> Dict:
    if not click.confirm(f"Sign using {key_name} Yubikey?"):
        return False
    while True:
        yk_public_key, _ = yk.yubikey_prompt(
            key_name,
            role_name,
            taf_repo=None,
            registering_new_key=True,
            creating_new_key=False,
            loaded_yubikeys=yubikeys,
            pin_confirm=True,
            pin_repeat=True,
        )

        if yk_public_key["keyid"] != public_key["keyid"]:
            print("Public key of the inserted key is not equal to the specified one.")
            if not click.confirm("Try again?"):
                return False
        return True
