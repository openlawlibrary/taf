import datetime
from pathlib import Path

import click

import taf.developer_tool as developer_tool
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.updater.updater import update_named_repository, update_repository
from taf.utils import ISO_DATE_PARAM_TYPE as ISO_DATE


@click.group()
def cli():
    pass


@cli.command()
@click.option('--repo-path', default='repository', help='Authentication repository\'s path')
@click.option('--keystore', default=None, help='Path of the keystore file')
@click.option('--keys-description', default=None, help='A dictionary containing information about the keys or a path'
              ' to a json file which which stores the needed information')
@click.option('--commit-msg', default=None, help='Commit message to be used in case the changes'
              'should be automatically committed')
@click.option('--scheme', default=DEFAULT_RSA_SIGNATURE_SCHEME, help='A signature scheme used for signing.')
def sign_targets(repo_path, keystore, keys_description, commit_msg, scheme):
    developer_tool.register_target_files(repo_path, keystore, keys_description, commit_msg, scheme)


@cli.command()
@click.option('--repo-path', default='repository', help='Authentication repository\'s path')
@click.option('--file-path', help="Target file's path, relative to the targets directory")
@click.option('--keystore', default='keystore', help='Path of the keystore file')
@click.option('--keys-description', default=None, help='A dictionary containing information about the keys or a path'
              ' to a json file which which stores the needed information')
@click.option('--scheme', default=DEFAULT_RSA_SIGNATURE_SCHEME, help='A signature scheme used for signing.')
def add_target_file(repo_path, file_path, keystore, keys_description, scheme):
    developer_tool.register_target_file(repo_path, file_path, keystore, keys_description, scheme)


@cli.command()
@click.option('--repo-path')
@click.option('--role')
@click.option('--pub-key-path')
def add_signing_key(repo_path, role, pub_key_path):
    developer_tool.add_signing_key(repo_path, role, pub_key_path)


@cli.command()
@click.option('--repo-path', default='repository', help='Location of the repository')
@click.option('--targets-dir', default='targets', help='Directory where the target '
              'repositories are located')
@click.option('--namespace', default=None, help='Namespace of the target repositories')
def update_repos_from_fs(repo_path, targets_dir, namespace):
    "Updates target repositories by traversing given targets directory "
    developer_tool.update_target_repos_from_fs(repo_path, targets_dir, namespace)


@cli.command()
@click.option("--repo-path", default="repository", help="Location of the repository")
@click.option('--targets-dir', default='targets', help='Directory where the target '
              'repositories are located')
@click.option('--namespace', default=None, help='Namespace of the target repositories')
def update_repos_from_repositories_json(repo_path, targets_dir, namespace):
    "Updates target repositories by traversing repositories.json "
    developer_tool.update_target_repos_from_repositories_json(repo_path)


@cli.command()
@click.option('--repo-path', default='repository', help='Location of the authentication repository')
@click.option('--targets-dir', default='targets', help='Directory where the target '
              'repositories are located')
@click.option('--namespace', default='', help='Namespace of the target repositories')
@click.option('--targets-rel-dir', default=None, help=' Directory relative to which urls '
              'of the target repositories are set, if they do not have remote set')
@click.option('--keystore', default='keystore', help='Location of the keystore file')
@click.option('--keys-description', help='A dictionary containing information about the '
              'keys or a path to a json file which which stores the needed information')
@click.option('--custom', default=None, help='A dictionary containing custom '
              'targets info which will be included in repositories.json')
def build_auth_repo(repo_path, targets_dir, namespace, targets_rel_dir, keystore,
                    keys_description, custom):
    developer_tool.build_auth_repo(repo_path, targets_dir, namespace, targets_rel_dir, keystore,
                                   keys_description, custom)


@cli.command()
@click.option('--repo-path', default='repository', help='Location of the repository')
@click.option('--keystore', default=None, help='Location of the keystore file')
@click.option('--keys-description', help='A dictionary containing information about the '
              'keys or a path to a json file which which stores the needed information')
@click.option('--commit-msg', default=None, help='Commit message. If provided, the '
              'changes will be committed automatically')
@click.option('--test', is_flag=True, default=False, help='Indicates if the created repository '
              'is a test authentication repository')
def create_repo(repo_path, keystore, keys_description, commit_msg, test):
    developer_tool.create_repository(repo_path, keystore, keys_description, commit_msg, test)


@cli.command()
@click.option('--path', help='File where to write the exported public key. Result will be written '
              'to console if path is not specified')
def export_yk_pub_key(path):
    developer_tool.export_yk_public_pem(path)


@cli.command()
@click.option('--keystore', default='keystore', help='Location of the keystore file')
@click.option('--keys-description', help='A dictionary containing information about the keys or a path'
              ' to a json file which which stores the needed information')
def generate_keys(keystore, keys_description):
    developer_tool.generate_keys(keystore, keys_description)


@cli.command()
@click.option('--repo-path', default='repository', help='Location of the repository')
@click.option('--targets-dir', default='targets', help='Directory where the target '
              'repositories are located')
@click.option('--namespace', default='', help='Namespace of the target repositories')
@click.option('--targets-rel-dir', default=None, help=' Directory relative to which urls '
              'of the target repositories are set, if they do not have remote set')
@click.option('--keystore', default='keystore', help='Location of the keystore file')
@click.option('--keys-description', help='A dictionary containing information about the '
              'keys or a path to a json file which which stores the needed information')
@click.option('--custom', default=None, help='A dictionary containing custom '
              'targets info which will be included in repositories.json')
@click.option('--commit', is_flag=True, default=True, help='Indicates if changes should be committed')
@click.option('--test', is_flag=True, default=False, help='Indicates if the created repository '
              'is a test authentication repository')
def init_repo(repo_path, targets_dir, namespace, targets_rel_dir, keystore,
              keys_description, custom, commit, test):
    developer_tool.init_repo(repo_path, targets_dir, namespace, targets_rel_dir, keystore,
                             keys_description, repos_custom=custom, commit=commit, test=test)


@cli.command()
@click.option('--repo-path', default='repository', help='Location of the repository')
@click.option('--targets-dir', default='targets', help='Directory where the target '
              'repositories are located')
@click.option('--namespace', default=None, help='Namespace of the target repositories')
@click.option('--targets-rel-dir', default=None, help=' Directory relative to which urls '
              'of the target repositories are set, if they do not have remote set')
@click.option('--custom', default=None, help='A dictionary containing custom '
              'targets info which will be included in repositories.json')
def generate_repositories_json(repo_path, targets_dir, namespace, targets_rel_dir, custom):
    developer_tool.generate_repositories_json(repo_path, targets_dir, namespace, targets_rel_dir,
                                              custom)


@cli.command()
@click.option('--repo-path', default='repository', help='Location of the repository')
@click.option('--keystore', default='keystore', help='Location of the keystore file')
@click.option('--keys-description', help='A dictionary containing information about the keys or a path'
              ' to a json file which which stores the needed information')
@click.option('--role', default='timestamp', help='Metadata role whose expiration date should be '
              'updated')
@click.option('--start-date', default=datetime.datetime.now(), help='Date to which the intercal is added', type=ISO_DATE)
@click.option('--interval', default=None, help='Time interval added to the start date', type=int)
@click.option('--commit-msg', default=None, help='Commit message to be used in case the changes'
              'should be automatically committed')
def update_expiration_date(repo_path, keystore, keys_description, role, start_date, interval,
                           commit_msg):
    developer_tool.update_metadata_expiration_date(repo_path, keystore, keys_description, role,
                                                   start_date, interval, commit_msg)


@cli.command()
@click.option('--url', help="Authentication repository's url")
@click.option('--clients-dir', help="Directory containing the client's authentication repository")
@click.option('--targets-dir', help="Directory containing the target repositories")
@click.option('--from-fs', is_flag=True, default=False, help='Indicates if the we want to clone a '
              'repository from the filesystem')
def update(url, clients_dir, targets_dir, from_fs):
    update_repository(url, clients_dir, targets_dir, from_fs)


@cli.command()
@click.option('--url', help="Authentication repository's url")
@click.option('--clients-dir', help="Directory containing the client's authentication repository")
@click.option('--repo-name', help="Repository's name")
@click.option('--targets-dir', help="Directory containing the target repositories")
@click.option('--from-fs', is_flag=True, default=False, help='Indicates if the we want to clone a '
              'repository from the filesystem')
def update_named_repo(url, clients_dir, repo_name, targets_dir, from_fs):
    update_named_repository(url, clients_dir, repo_name, targets_dir, from_fs)


@cli.command()
@click.option('--certs-dir', help='Path of the directory where the exported certificate will be saved')
def setup_signing_yubikey(certs_dir):
    developer_tool.setup_signing_yubikey(certs_dir)


@cli.command()
@click.option('--key-path', default=None, help='Path to the key which should be copied to a Yubikey')
def setup_test_yubikey(key_path):
    import taf.yubikey as yk

    if key_path is None:
        key_path = Path(__file__).parent.parent / "tests" / "data" / "keystore" / "targets"
    else:
        key_path = Path(key_path)

    key_pem = key_path.read_bytes()

    click.echo("\nImporting RSA private key from {} to Yubikey...".format(key_path))

    pin = yk.DEFAULT_PIN
    pub_key = yk.setup(pin, 'Test Yubikey', private_key_pem=key_pem)

    click.echo("\nPrivate key successfully imported.\n")
    click.echo("\nPublic key (PEM): \n{}".format(pub_key.decode("utf-8")))
    click.echo("Pin: {}\n".format(pin))


cli()
