import datetime
from pathlib import Path
from taf.exceptions import TargetsMetadataUpdateError
from taf.git import GitRepository
from taf.keys import load_signing_keys
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.repository_tool import Repository, is_delegated_role


def check_expiration_dates(
    repo_path, interval=None, start_date=None, excluded_roles=None
):
    """
    <Purpose>
        Check if any metadata files (roles) are expired or will expire in the next <interval> days.
        Prints a list of expired roles.
    <Arguments>
        repo_path:
        Authentication repository's location
        interval:
        Number of days ahead to check for expiration
        start_date:
        Date from which to start checking for expiration
        excluded_roles:
        List of roles to exclude from the check
    """
    repo_path = Path(repo_path)
    taf_repo = Repository(repo_path)

    expired_dict, will_expire_dict = taf_repo.check_roles_expiration_dates(
        interval, start_date, excluded_roles
    )

    if expired_dict or will_expire_dict:
        now = datetime.datetime.now()
        print(
            f"Given a {interval} day interval from today ({start_date.strftime('%Y-%m-%d')}):"
        )
        for role, expiry_date in expired_dict.items():
            delta = now - expiry_date
            print(
                f"{role} expired {delta.days} days ago (on {expiry_date.strftime('%Y-%m-%d')})"
            )
        for role, expiry_date in will_expire_dict.items():
            delta = expiry_date - now
            print(
                f"{role} will expire in {delta.days} days (on {expiry_date.strftime('%Y-%m-%d')})"
            )
    else:
        print(f"No roles will expire within the given {interval} day interval")


def update_metadata_expiration_date(
    repo_path,
    roles,
    interval,
    keystore=None,
    scheme=None,
    start_date=None,
    no_commit=False,
):
    if start_date is None:
        start_date = datetime.datetime.now()

    taf_repo = Repository(repo_path)
    loaded_yubikeys = {}
    roles_to_update = []

    if "root" in roles:
        roles_to_update.append("root")
    if "targets" in roles:
        roles_to_update.append("targets")
    for role in roles:
        if is_delegated_role(role):
            roles_to_update.append(role)

    if len(roles_to_update) or "snapshot" in roles:
        roles_to_update.append("snapshot")
    roles_to_update.append("timestamp")

    for role in roles_to_update:
        try:
            keys, yubikeys = load_signing_keys(
                taf_repo,
                role,
                loaded_yubikeys=loaded_yubikeys,
                keystore=keystore,
                scheme=scheme,
            )
            # sign with keystore
            if len(keys):
                taf_repo.update_role_keystores(
                    role, keys, start_date=start_date, interval=interval
                )
            if len(yubikeys):  # sign with yubikey
                taf_repo.update_role_yubikeys(
                    role, yubikeys, start_date=start_date, interval=interval
                )
        except Exception as e:
            print(f"Could not update expiration date of {role}. {str(e)}")
            return
        else:
            print(f"Updated expiration date of {role}")

    if no_commit:
        print("\nNo commit was set. Please commit manually. \n")
    else:
        auth_repo = GitRepository(path=repo_path)
        commit_message = input("\nEnter commit message and press ENTER\n\n")
        auth_repo.commit(commit_message)


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


def update_target_metadata(
    taf_repo,
    added_targets_data,
    removed_targets_data,
    keystore,
    roles_infos,
    write=False,
    scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
):
    """Update given targets data with an appropriate role, as well as snapshot and
    timestamp roles.
    """
    added_targets_data = {} if added_targets_data is None else added_targets_data
    removed_targets_data = {} if removed_targets_data is None else removed_targets_data

    roles_targets = taf_repo.roles_targets_for_filenames(
        list(added_targets_data.keys()) + list(removed_targets_data.keys())
    )

    if not roles_targets:
        raise TargetsMetadataUpdateError(
            "There are no added/modified/removed target files."
        )

    # update targets
    loaded_yubikeys = {}
    for role, target_paths in roles_targets.items():
        keystore_keys, yubikeys = load_signing_keys(
            taf_repo, role, keystore, roles_infos, loaded_yubikeys, scheme=scheme
        )
        targets_data = dict(
            added_targets_data={
                path: val
                for path, val in added_targets_data.items()
                if path in target_paths
            },
            removed_targets_data={
                path: val
                for path, val in removed_targets_data.items()
                if path in target_paths
            },
        )

        if len(yubikeys):
            taf_repo.update_targets_yubikeys(yubikeys, write=False, **targets_data)
        if len(keystore_keys):
            taf_repo.update_targets_keystores(
                keystore_keys, write=False, **targets_data
            )

    if write:
        update_snapshot_and_timestamp(taf_repo, keystore, roles_infos, scheme=scheme)
