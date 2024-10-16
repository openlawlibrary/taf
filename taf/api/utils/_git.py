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


def commit_and_push(
    auth_repo: AuthenticationRepository,
    commit_msg: Optional[str] = None,
    push: Optional[bool] = True,
) -> None:
    if commit_msg is None:
        commit_msg = input("\nEnter commit message and press ENTER\n\n")
    auth_repo.commit(commit_msg)

    if push and auth_repo.has_remote():
        try:
            auth_repo.push()
            taf_logger.log("NOTICE", "Successfully pushed to remote")

            new_commit_branch = auth_repo.default_branch
            if new_commit_branch:
                new_commit = auth_repo.top_commit_of_branch(new_commit_branch)
                if new_commit:
                    auth_repo.set_last_validated_commit(new_commit)
                    taf_logger.info(f"Updated last_validated_commit to {new_commit}")
            else:
                taf_logger.warning(
                    "Default branch is None, skipping last_validated_commit update."
                )
        except GitError as e:
            taf_logger.error(
                f"Push failed: {str(e)}. Please check if there are upstream changes."
            )
            raise TAFError("Push operation failed") from e
