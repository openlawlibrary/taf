import functools
from taf.exceptions import RepositoryNotCleanError, RepositoryNotSynced
from taf.git import GitRepository


def check_if_clean_and_synced(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        skip_clean_check = kwargs.pop("skip_clean_check", False)
        skip_remote_check = kwargs.pop("skip_remote_check", False)

        if not skip_clean_check or not skip_remote_check:
            path = kwargs.get("path", None)
            if path is None:
                path = args[0]
            repo = GitRepository(path=path)

        if not skip_clean_check:
            if repo.something_to_commit():
                raise RepositoryNotCleanError(repo.name)

        if not skip_remote_check:
            if repo.has_remote():
                if not repo.synced_with_remote(repo.default_branch):
                    raise RepositoryNotSynced(repo.name)

        return func(*args, **kwargs)

    return wrapper
