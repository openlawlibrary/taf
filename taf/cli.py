import click

from taf.repository_tool import load_repository
from taf.updater.updater import update as taf_updater


@click.group()
def cli():
  pass


@cli.command()
@click.option('--repo-path', help='Authentication repository\'s path')
@click.option('--file-path', help='Target file\'s path, relative to the targets directory')
@click.option('--keystore-path', help='Path of the keystore file')
@click.option('--targets-role', default='targets', help='Targets metadata file to be updated')
def add_target_file(repo_path, file_path, keystore_path, targets_role):
  with load_repository(repo_path) as tuf_repo:
    tuf_repo.add_existing_target(file_path)
    tuf_repo.write_roles_metadata(targets_role, keystore_path, True)

@cli.command()
@click.option('--url', default='https://github.com/openlawlibrary/smc-law-test', help='Authentication repository\'s url')
@click.option('--clients-directory', default='E:\\OLL\\tuf_updater_test', help='Directory containing the client\'s authentication repository')
@click.option('--repo-name', default='smc-law-test')
def update(url, clients_directory, repo_name):
  taf_updater(url, clients_directory, repo_name)
cli()
