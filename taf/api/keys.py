import click

from pathlib import Path
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


def export_yk_certificate(certs_dir, key):
    if certs_dir is None:
        certs_dir = Path.home()
    else:
        certs_dir = Path(certs_dir)
    certs_dir.mkdir(parents=True, exist_ok=True)
    cert_path = certs_dir / f"{key['keyid']}.cert"
    print(f"Exporting certificate to {cert_path}")
    with open(cert_path, "wb") as f:
        f.write(yk.export_piv_x509())


def load_sorted_keys_of_roles(
    auth_repo, roles_infos, repository, keystore, yubikeys, existing_roles=None
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
                repository,
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
    role_infos=None,
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

    # check if it is specified in role key infos that key is stored on yubikey
    # in such a case, do not attempt to load the key from keystore
    is_yubikey = None
    if role_infos is not None and role in role_infos:
        is_yubikey = role_infos[role].get("yubikey")

    if not is_yubikey and keystore is not None:
        # try loading files from the keystore first
        # does not assume that all keys of a role are stored in keystore files just
        # because one of them is
        keystore = Path(keystore)
        # names of keys are expected to be role or role + counter
        key_names = [f"{role}{counter}" for counter in range(1, signing_keys_num + 1)]
        key_names.insert(0, role)
        for key_name in key_names:
            if (keystore / key_name).is_file():
                try:
                    key = read_private_key_from_keystore(
                        keystore, key_name, role_infos, num_of_signatures, scheme
                    )
                    # load only valid keys
                    if taf_repo.is_valid_metadata_key(role, key, scheme=scheme):
                        keys.append(key)
                        num_of_signatures += 1
                except KeystoreError:
                    pass

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
            if is_yubikey is None:
                is_yubikey = click.confirm(f"Sign {role} using YubiKey(s)?")
            if is_yubikey:
                public_key, _ = yk.yubikey_prompt(
                    key_name, role, taf_repo, loaded_yubikeys=loaded_yubikeys
                )
                yubikeys.append(public_key)
            else:
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
            print(f"{key_path} is not a file!")
        else:
            if is_public:
                print(f"Could not load public key {key_path}")
            else:
                print(f"Could not load private key {key_path}")

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
