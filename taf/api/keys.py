from taf.developer_tool import DEFAULT_ROLE_SETUP_PARAMS, _get_key_name, _setup_keystore_key, _setup_yubikey
from taf.exceptions import KeystoreError


def _setup_roles_keys(
    role_name, key_info, certs_dir=None, keystore=None, yubikeys=None
):
    yubikey_keys = []
    keystore_keys = []

    num_of_keys = key_info.get("number", DEFAULT_ROLE_SETUP_PARAMS["number"])
    is_yubikey = key_info.get("yubikey", DEFAULT_ROLE_SETUP_PARAMS["yubikey"])
    scheme = key_info.get("scheme", DEFAULT_ROLE_SETUP_PARAMS["scheme"])
    length = key_info.get("length", DEFAULT_ROLE_SETUP_PARAMS["length"])
    passwords = key_info.get("passwords", DEFAULT_ROLE_SETUP_PARAMS["passwords"])

    for key_num in range(num_of_keys):
        key_name = _get_key_name(role_name, key_num, num_of_keys)
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
            keystore_keys, _ = _setup_roles_keys(
                role_name, key_info, repository, keystore=keystore
            )
            for public_key, private_key in keystore_keys:
                signing_keys.setdefault(role_name, []).append(private_key)
                verification_keys.setdefault(role_name, []).append(public_key)

        for role_name, key_info in yubikey_roles:
            if role_name in existing_roles:
                continue
            _, yubikey_keys = _setup_roles_keys(
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
