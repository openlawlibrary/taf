import functools
from logging import ERROR
from typing import Optional
from logdecorator import log_on_error
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import RepositoryNotCleanError, TAFError
from taf.git import GitRepository
from taf.log import taf_logger


def check_if_clean(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        path = kwargs.get("path", None)
        if path is None:
            path = args[0]
        repo = GitRepository(path=path)
        if repo.something_to_commit():
            raise RepositoryNotCleanError(
                "Repository has uncommitted changes. Commit or revert the changes and run the command again."
            )

        # Call the original function
        return func(*args, **kwargs)

    return wrapper


@log_on_error(
    ERROR,
    "An error occurred while committing and pushing changes: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def commit_and_push(
    auth_repo: AuthenticationRepository,
    commit_msg: Optional[str] = None,
    push: Optional[bool] = True,
) -> None:
    if commit_msg is None:
        commit_message = input("\nEnter commit message and press ENTER\n\n")
    auth_repo.commit(commit_message)
    if push:
        auth_repo.push()
        taf_logger.info("Successfully pushed to remote")
