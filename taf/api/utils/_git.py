import functools
from taf.exceptions import RepositoryNotCleanError, RepositoryNotSynced
from taf.git import GitRepository


def check_if_clean_and_synced(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        skip_check = kwargs.pop("skip_clean_check", False)
        if not skip_check:
            path = kwargs.get("path", None)
            if path is None:
                path = args[0]
            repo = GitRepository(path=path)
            if repo.something_to_commit():
                raise RepositoryNotCleanError(repo.name)
            if repo.has_remote():
                if not repo.synced_with_remote(repo.default_branch):
                    raise RepositoryNotSynced(repo.name)

        return func(*args, **kwargs)

    return wrapper
