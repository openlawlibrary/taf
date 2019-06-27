import datetime
import json
import os

import click

import taf.developer_tool as developer_tool
from taf.updater.updater import update_named_repository, update_repository
from taf.utils import ISO_DATE_PARAM_TYPE as ISO_DATE


@click.group()
def cli():
  pass


@cli.command()
@click.option('--repo-path', default='repository', help='Authentication repository\'s path')
@click.option('--targets-key-slot', default=None, help='Targets key (YubiKey) slot with signing key')
@click.option('--targets-key-pin', default=None, help='Targets key (YubiKey) pin.')
@click.option('--keystore', default='keystore', help='Path of the keystore file')
@click.option('--keys-description', default=None, help='A dictionary containing information about the keys or a path'
              ' to a json file which which stores the needed information')
@click.option('--update-all', is_flag=True, default=True, help='Update snapshot and timestamp')
@click.option('--commit-msg', default=None, help='Commit message to be used in case the changes'
              'should be automatically committed')
def add_targets(repo_path, targets_key_slot, targets_key_pin, keystore,
                keys_description, update_all, commit_msg):
  if not os.path.exists(keystore) and (update_all or not(targets_key_slot and targets_key_pin)):
    click.echo('\nError: Keystore must be provided and exist on disk if update_all is True or '
               'if the targets key should be loaded from the file system')
    return
  if os.path.isfile(keys_description):
    with open(keys_description) as f:
      keys_description = json.loads(f.read())
  developer_tool.register_target_files(repo_path, keystore, keys_description,
                                       targets_key_slot, targets_key_pin, update_all, commit_msg)


@cli.command()
@click.option('--repo-path',  default='repository', help='Authentication repository\'s path')
@click.option('--file-path', help="Target file's path, relative to the targets directory")
@click.option('--targets-key-slot', default=None, help='Targets key (YubiKey) slot with signing key')
@click.option('--targets-key-pin', default=None, help='Targets key (YubiKey) pin.')
@click.option('--keystore', default='keystore', help='Path of the keystore file')
@click.option('--keys-description', default=None, help='A dictionary containing information about the keys or a path'
              ' to a json file which which stores the needed information')
@click.option('--update-all', is_flag=True, default=False, help='Update snapshot and timestamp')
def add_target_file(repo_path, file_path, targets_key_slot, targets_key_pin, keystore,
                    keys_description, update_all):
  if not os.path.exists(keystore) and (update_all or not(targets_key_slot and targets_key_pin)):
    click.echo('\nError: Keystore must be provided and exist on disk if update_all is True or '
               'if the targets key should be loaded from the file system')
    return
  if os.path.isfile(keys_description):
    with open(keys_description) as f:
      keys_description = json.loads(f.read())
  developer_tool.register_target_file(repo_path, file_path, keystore, keys_description,
                                      targets_key_slot, targets_key_pin, update_all)


@cli.command()
@click.option('--repo-path', default='repository', help='Location of the repository')
@click.option('--targets-dir', default='targets', help='Directory where the target '
              'repositories are located')
@click.option('--namespace', default='', help='Namespace of the target repositories')
def add_target_repos(repo_path, targets_dir, namespace):
  developer_tool.add_target_repos(repo_path, targets_dir, namespace)


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
@click.option('--repos-custom', default=None, help='A dictionary containing custom '
              'targets info which will be included in repositories.json')
def build_auth_repo(repo_path, targets_dir, namespace, targets_rel_dir, keystore,
                    keys_description, repos_custom):
  if os.path.isfile(keys_description):
    with open(keys_description) as f:
      keys_description = json.loads(f.read())
  developer_tool.build_auth_repo(repo_path, targets_dir, namespace, targets_rel_dir, keystore,
                                 keys_description, repos_custom)


@cli.command()
@click.option('--repo-path', default='repository', help='Location of the repository')
@click.option('--keystore', default='keystore', help='Location of the keystore file')
@click.option('--keys-description', help='A dictionary containing information about the '
              'keys or a path to a json file which which stores the needed information')
@click.option('--commit', is_flag=True, default=True, help='Indicates if changes should be committed')
def create_repo(repo_path, keystore, keys_description, commit):
  if os.path.isfile(keys_description):
    with open(keys_description) as f:
      keys_description = json.loads(f.read())
  developer_tool.create_repository(repo_path, keystore, keys_description, commit)


@cli.command()
@click.option('--keystore', default='keystore', help='Location of the keystore file')
@click.option('--keys-description', help='A dictionary containing information about the keys or a path'
              ' to a json file which which stores the needed information')
def generate_keys(keystore, keys_description):
  if os.path.isfile(keys_description):
    with open(keys_description) as f:
      keys_description = json.loads(f.read())
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
@click.option('--repos-custom', default=None, help='A dictionary containing custom '
              'targets info which will be included in repositories.json')
@click.option('--commit', is_flag=True, default=True, help='Indicates if changes should be committed')
def init_repo(repo_path, targets_dir, namespace, targets_rel_dir, keystore,
              keys_description, repos_custom, commit):
  developer_tool.init_repo(repo_path, targets_dir, namespace, targets_rel_dir, keystore,
                           keys_description, repos_custom=repos_custom, should_commit=commit)


@cli.command()
@click.option('--repo-path', default='repository', help='Location of the repository')
@click.option('--targets-dir', default='targets', help='Directory where the target '
              'repositories are located')
@click.option('--namespace', default='', help='Namespace of the target repositories')
@click.option('--targets-rel-dir', default=None, help=' Directory relative to which urls '
              'of the target repositories are set, if they do not have remote set')
def generate_repositories_json(repo_path, targets_dir, namespace, targets_rel_dir):
  developer_tool.generate_repositories_json(repo_path, targets_dir, namespace, targets_rel_dir)


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


cli()
