import os

import click

from taf.repository_tool import load_repository
from taf.updater.updater import update_repository, update_named_repository
from tuf.repository_tool import TARGETS_DIRECTORY_NAME


@click.group()
def cli():
  pass


@cli.command()
@click.option('--repo-path', help='Authentication repository\'s path')
@click.option('--file-path', help='Target file\'s path, relative to the targets directory')
@click.option('--targets-key-slot', default=None, help='Targets key (YubiKey) slot with signing key')
@click.option('--targets-key-pin', default=None, help='Targets key (YubiKey) pin.')
@click.option('--update-all', is_flag=True, default=False, help='Update snapshot and timestamp')
@click.option('--keystore', default='', help='Path of the keystore file')
def add_target_file(repo_path, file_path, targets_key_slot, targets_key_pin, update_all, keystore):
  if update_all and not os.path.exists(keystore):
    click.echo('\nError: Option "--keystore" is required if "--update-all" is passed.')
    return

  with load_repository(repo_path) as taf_repo:
    taf_repo.add_existing_target(file_path)

    if update_all:
      taf_repo.update_targets(targets_key_slot, targets_key_pin, write=False)
      taf_repo.update_snapshot_and_timestmap(keystore)  # Calls writeall()
    else:
      taf_repo.update_targets(targets_key_slot, targets_key_pin)


@cli.command()
@click.option('--repo-path', help='Authentication repository\'s path')
@click.option('--targets-key-slot', default=None, help='Targets key (YubiKey) slot with signing key')
@click.option('--targets-key-pin', default=None, help='Targets key (YubiKey) pin.')
@click.option('--update-all', is_flag=True, default=False, help='Update snapshot and timestamp')
@click.option('--keystore', default='', help='Path of the keystore file')
def add_targets(repo_path, targets_key_slot, targets_key_pin, update_all, keystore):
  if update_all and not os.path.exists(keystore):
    click.echo('\nError: Missing option "--keystore" if --update-all is passed.')
    return

  targets_path = os.path.join(repo_path, TARGETS_DIRECTORY_NAME)
  with load_repository(repo_path) as taf_repo:
    for root, _, filenames in os.walk(targets_path):
      for filename in filenames:
        relpath = os.path.relpath(os.path.join(root, filename), targets_path)
        relpath = os.path.normpath(relpath).replace(os.path.sep, '/')
        taf_repo.add_existing_target(relpath)

    if update_all:
      taf_repo.update_targets(targets_key_slot, targets_key_pin, write=False)
      taf_repo.update_snapshot_and_timestmap(keystore)  # Calls writeall()
    else:
      taf_repo.update_targets(targets_key_slot, targets_key_pin)


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
@click.option('--target-dir', help="Directory containing the target repositories")
@click.option('--from-fs', is_flag=True, default=False, help='Indicates if the we want to clone a '
              'repository from the filesystem')
def update_named_repo(url, clients_dir, repo_name, targets_dir, from_fs):
  update_named_repository(url, clients_dir, repo_name, targets_dir, from_fs)


cli()
