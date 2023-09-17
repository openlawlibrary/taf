import functools
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import RepositoryNotCleanError
from taf.git import GitRepository


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


def commit_and_push(
    auth_repo: AuthenticationRepository, commit_msg=None, push=True
) -> None:
    if commit_msg is None:
        commit_message = input("\nEnter commit message and press ENTER\n\n")
    auth_repo.commit(commit_message)
    if push:
        auth_repo.push()
