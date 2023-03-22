from taf.api.keys import load_signing_keys
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME


def update_snapshot_and_timestamp(
    taf_repo, keystore, roles_infos, scheme=DEFAULT_RSA_SIGNATURE_SCHEME, write_all=True
):
    loaded_yubikeys = {}

    for role in ("snapshot", "timestamp"):
        keystore_keys, yubikeys = load_signing_keys(
            taf_repo, role, keystore, roles_infos, loaded_yubikeys, scheme=scheme
        )
        if len(yubikeys):
            update_method = taf_repo.roles_yubikeys_update_method(role)
            update_method(yubikeys, write=False)
        if len(keystore_keys):
            update_method = taf_repo.roles_keystore_update_method(role)
            update_method(keystore_keys, write=False)

    if write_all:
        taf_repo.writeall()
