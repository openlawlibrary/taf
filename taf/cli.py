import datetime
from pathlib import Path

import click
import taf.developer_tool as developer_tool
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.keystore import read_private_key_from_keystore, load_tuf_private_key
from taf.updater.updater import update_named_repository, update_repository
from taf.utils import ISO_DATE_PARAM_TYPE as ISO_DATE
from taf.utils import read_input_dict


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
@click.option('--url', help="Authentication repository's url")
@click.option('--clients-dir', help="Directory containing the client's authentication repository")
@click.option('--targets-dir', help="Directory containing the target repositories")
@click.option('--from-fs', is_flag=True, default=False, help='Indicates if the we want to clone a '
              'repository from the filesystem')
@click.option('--authenticate-test-repo', is_flag=True, help="Indicates that the authentication "
              "repository is a test repository")
def update(url, clients_dir, targets_dir, from_fs, authenticate_test_repo):
    update_repository(url, clients_dir, targets_dir, from_fs,
                      authenticate_test_repo=authenticate_test_repo)


@cli.command()
@click.option('--url', help="Authentication repository's url")
@click.option('--clients-dir', help="Directory containing the client's authentication repository")
@click.option('--repo-name', help="Repository's name")
@click.option('--targets-dir', help="Directory containing the target repositories")
@click.option('--from-fs', is_flag=True, default=False, help='Indicates if the we want to clone a '
              'repository from the filesystem')
@click.option('--authenticate-test-repo', is_flag=True, help="Indicates that the authentication "
              "repository is a test repository")
def update_named_repo(url, clients_dir, repo_name, targets_dir, from_fs, authenticate_test_repo):
    update_named_repository(url, clients_dir, repo_name, targets_dir, from_fs,
                            authenticate_test_repo=authenticate_test_repo)



cli()
