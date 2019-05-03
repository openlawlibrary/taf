import click

from taf.repository_tool import load_repository


@click.group()
def cli():
  pass


@cli.command()
@click.argument('repo-path')
@click.argument('file-path')
@click.argument('keystore-path')
@click.option('--targets-role', default='targets', help='Targets metadata file to be updated')
def add_target_file(repo_path, file_path, keystore_path, targets_role):
  with load_repository(repo_path) as tuf_repo:
    tuf_repo.add_existing_target(file_path)
    tuf_repo.write_roles_metadata(targets_role, keystore_path, True)


cli()
