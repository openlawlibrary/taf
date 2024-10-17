import functools
from typing import Optional
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import GitError, RepositoryNotCleanError, TAFError
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
            raise RepositoryNotCleanError(repo.name)

        # Call the original function
        return func(*args, **kwargs)

    return wrapper
