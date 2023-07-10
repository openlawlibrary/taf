import click

from pathlib import Path
from taf.yubikey import export_yk_certificate
from tuf.repository_tool import generate_and_write_unencrypted_rsa_keypair
from taf.constants import DEFAULT_ROLE_SETUP_PARAMS, DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import KeystoreError
from taf.keystore import (
    key_cmd_prompt,
    read_private_key_from_keystore,
    read_public_key_from_keystore,
)
from taf import YubikeyMissingLibrary
from tuf.sig import generate_rsa_signature

try:
    import taf.yubikey as yk
except ImportError:
    yk = YubikeyMissingLibrary()


def get_key_name(role_name, key_num, num_of_keys):
    if num_of_keys == 1:
        return role_name
    else:
        return role_name + str(key_num + 1)


def load_sorted_keys_of_roles(
    auth_repo, roles_infos, repository, keystore, yubikeys, existing_roles=None
):
    def _sort_roles(key_info, repository):
        # load keys not stored on YubiKeys first, to avoid entering pins
        # if there is something wrong with keystore files
        keystore_roles = []
        yubikey_roles = []
        for role_name, role_key_info in key_info.items():
            if not role_key_info.get("yubikey", False):
                keystore_roles.append((role_name, role_key_info))
            else:
                yubikey_roles.append((role_name, role_key_info))
            if "delegations" in role_key_info:
                delegated_keystore_role, delegated_yubikey_roles = _sort_roles(
                    role_key_info["delegations"]["roles"], repository
                )
                keystore_roles.extend(delegated_keystore_role)
                yubikey_roles.extend(delegated_yubikey_roles)
        return keystore_roles, yubikey_roles

    # load and/or generate all keys first
    if existing_roles is None:
        existing_roles = []
    try:
        keystore_roles, yubikey_roles = _sort_roles(roles_infos, repository)
        signing_keys = {}
        verification_keys = {}
        for role_name, key_info in keystore_roles:
            if role_name in existing_roles:
                continue
            keystore_keys, _ = setup_roles_keys(
                role_name, key_info, repository, keystore=keystore
            )
            for public_key, private_key in keystore_keys:
                signing_keys.setdefault(role_name, []).append(private_key)
                verification_keys.setdefault(role_name, []).append(public_key)

        for role_name, key_info in yubikey_roles:
            if role_name in existing_roles:
                continue
            _, yubikey_keys = setup_roles_keys(
                role_name,
                key_info,
                certs_dir=auth_repo.certs_dir,
                yubikeys=yubikeys,
            )
            verification_keys[role_name] = yubikey_keys
        return signing_keys, verification_keys
    except KeystoreError as e:
        print(f"Creation of repository failed: {e}")
        return


def load_sorted_keys_of_new_roles(
    auth_repo, roles_infos, keystore, yubikeys, existing_roles=None
):
    def _sort_roles(key_info, repository):
        # load keys not stored on YubiKeys first, to avoid entering pins
        # if there is somethig wrong with keystore files
        keystore_roles = []
        yubikey_roles = []
        for role_name, role_key_info in key_info.items():
            if not role_key_info.get("yubikey", False):
                keystore_roles.append((role_name, role_key_info))
            else:
                yubikey_roles.append((role_name, role_key_info))
            if "delegations" in role_key_info:
                delegated_keystore_role, delegated_yubikey_roles = _sort_roles(
                    role_key_info["delegations"]["roles"], repository
                )
                keystore_roles.extend(delegated_keystore_role)
                yubikey_roles.extend(delegated_yubikey_roles)
        return keystore_roles, yubikey_roles

    # load and/or generate all keys first
    if existing_roles is None:
        existing_roles = []
    try:
        keystore_roles, yubikey_roles = _sort_roles(roles_infos, auth_repo)
        signing_keys = {}
        verification_keys = {}
        for role_name, key_info in keystore_roles:
            if role_name in existing_roles:
                continue
            keystore_keys, _ = setup_roles_keys(
                role_name, key_info, auth_repo.path, keystore=keystore
            )
            for public_key, private_key in keystore_keys:
                signing_keys.setdefault(role_name, []).append(private_key)
                verification_keys.setdefault(role_name, []).append(public_key)

        for role_name, key_info in yubikey_roles:
            if role_name in existing_roles:
                continue
            _, yubikey_keys = setup_roles_keys(
                role_name,
                key_info,
                certs_dir=auth_repo.certs_dir,
                yubikeys=yubikeys,
            )
            verification_keys[role_name] = yubikey_keys
        return signing_keys, verification_keys
    except KeystoreError as e:
        print(f"Creation of repository failed: {e}")
        return


def load_signing_keys(
    taf_repo,
    role,
    keystore=None,
    loaded_yubikeys=None,
    scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
):
    """
    Load role's signing keys. Make sure that at least the threshold of keys was
    loaded, but allow loading more keys (so that a metadata file can be signed
    by all of the role's keys if the user wants that)
    """
    print(f"Loading signing keys of role {role}")
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

    keystore = Path(keystore)

    def _load_from_keystore(key_name):
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
            if _load_and_append_yubikeys(key_name, role, False):
                num_of_signatures += 1
                continue

            print("Attempting to load from keystore")
            key = _load_from_keystore(key_name)
            if key is not None:
                keys.append(key)
                num_of_signatures += 1
                continue

            if click.confirm(f"Sign {role} using YubiKey(s)?"):
                _load_and_append_yubikeys(key_name, role, True)
                num_of_signatures += 1
                continue

            key = key_cmd_prompt(key_name, role, taf_repo, keys, scheme)
            keys.append(key)
            num_of_signatures += 1

    return keys, yubikeys


def setup_roles_keys(role_name, key_info, certs_dir=None, keystore=None, yubikeys=None):
    yubikey_keys = []
    keystore_keys = []

    num_of_keys = key_info.get("number", DEFAULT_ROLE_SETUP_PARAMS["number"])
    is_yubikey = key_info.get("yubikey", DEFAULT_ROLE_SETUP_PARAMS["yubikey"])
    scheme = key_info.get("scheme", DEFAULT_ROLE_SETUP_PARAMS["scheme"])
    length = key_info.get("length", DEFAULT_ROLE_SETUP_PARAMS["length"])
    passwords = key_info.get("passwords", DEFAULT_ROLE_SETUP_PARAMS["passwords"])

    for key_num in range(num_of_keys):
        key_name = get_key_name(role_name, key_num, num_of_keys)
        if is_yubikey:
            public_key = _setup_yubikey(
                yubikeys, role_name, key_name, scheme, certs_dir
            )
            yubikey_keys.append(public_key)
        else:
            password = None
            if passwords is not None and len(passwords) > key_num:
                password = passwords[key_num]
            public_key, private_key = _setup_keystore_key(
                keystore, role_name, key_name, key_num, scheme, length, password
            )
            keystore_keys.append((public_key, private_key))
    return keystore_keys, yubikey_keys


def _setup_keystore_key(
    keystore, role_name, key_name, key_num, scheme, length, password
):
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


def _setup_yubikey(yubikeys, role_name, key_name, scheme, certs_dir):
    while True:
        print(f"Registering keys for {key_name}")
        use_existing = click.confirm("Do you want to reuse already set up Yubikey?")
        if not use_existing:
            if not click.confirm(
                "WARNING - this will delete everything from the inserted key. Proceed?"
            ):
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
