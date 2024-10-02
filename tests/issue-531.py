import sys
import click

@click.command()
@catch_cli_exception(handle=TAFError, print_error=True)
def cli_update_repo():
    
    try:
        success = update_repo()  
        if not success:
            raise TAFError("Repo update failed")
    except TAFError as e:
        click.echo(f"Error: {e}")
        sys.exit(1)  
    except Exception as e:
        click.echo(f"Unexpected error: {e}")
        sys.exit(1)  
    
    click.echo("Repo updated successfully")
    sys.exit(0)  
