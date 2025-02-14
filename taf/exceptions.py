from typing import List, Optional, Any, Tuple
import subprocess


class TAFError(Exception):
    pass

    def __str__(self):
        try:
            return self.message
        except AttributeError:
            return super().__str__()


class GitAccessDeniedException(TAFError):
    def __init__(self, repo, operation, message=None):
        self.message = f"Cannot {operation} {repo.name} from any of the following URLs: {repo.urls}"
        if message is not None:
            self.message = f"{self.message}\n{message}"


class CloneRepoException(GitAccessDeniedException):
    def __init__(self, repo, operation="clone", message=None):
        super().__init__(repo, operation, message)


class CommandValidationError(TAFError):
    pass


class FetchException(TAFError):
    def __init__(self, path: str):
        self.message = f"Cannot fetch changes. Repo: {path}"


class GitError(TAFError):
    def __init__(
        self,
        repo: Any,
        command: Optional[str] = None,
        error: Optional[subprocess.CalledProcessError] = None,
        message: Optional[str] = None,
    ):
        if message is None:
            if command is not None:
                message = f"error occurred while executing {command}"
                if error is not None:
                    message = f"{message}:\n{str(error.stdout)}"
            elif error is not None:
                message = str(error)
            else:
                message = "error occurred"
        self.message = f"{repo.log_prefix}{message}" if repo is not None else message
        self.repo = repo
        self.command = command
        self.error = error


class InvalidBranchError(TAFError):
    pass


class InvalidCommitError(TAFError):
    pass


class InvalidKeyError(TAFError):
    def __init__(self, metadata_role: Optional[str]):
        super().__init__(
            f"Cannot sign {metadata_role} metadata file with inserted key."
        )


class InvalidOrMissingMetadataError(TAFError):
    pass


class InvalidRepositoryError(TAFError):
    pass


class InvalidPINError(TAFError):
    pass


class PushFailedError(GitError):
    pass


class RemoveMetadataKeyThresholdError(TAFError):
    def __init__(self, threshold: int):
        super().__init__(
            f"Remaining key number must be greater or equal to threshold ({threshold})."
        )


class RepositoryInstantiationError(TAFError):
    def __init__(self, repo_path: str, message: str):
        super().__init__(f"Could not instantiate repository {repo_path}\n\n: {message}")
        self.repo_path = repo_path
        self.message = message


class RepositoryNotCleanError(TAFError):
    def __init__(self, repo_name: str):
        message = f"Repository {repo_name} has uncommitted changes. Commit and push or revert the changes and run the command again."
        super().__init__(message)
        self.message = message


class RepositoryNotSynced(TAFError):
    def __init__(self, repo_name: str):
        message = (
            f"Repository {repo_name} is not synced with remote, or the synchronization status could not be verified due to communication issues."
            "\nRun the updater and try again."
        )
        super().__init__(message)
        self.message = message


class MultipleRepositoriesNotCleanError(TAFError):
    def __init__(
        self,
        dirty_index_repos: List[str],
        unpushed_commits_repos_and_branches: List[Tuple[str, str]],
    ):
        message = ""
        dirty_repo_list = ", ".join(dirty_index_repos)
        if len(dirty_index_repos) >= 1:
            message += f"Repositories {dirty_repo_list} have uncommitted changes. Commit and push or use --force to revert and run the command again."
        unpushed_repo_branches = ", ".join(
            [
                f"{repo}: ({branch})"
                for repo, branch in unpushed_commits_repos_and_branches
            ]
        )
        if len(unpushed_commits_repos_and_branches) >= 1:
            message += f"\nThe following {'repository has' if len(unpushed_commits_repos_and_branches) == 1 else 'repositories have'} unpushed commits on branches: {unpushed_repo_branches}. Push the commits and run the command again."
        super().__init__(message)
        self.message = message


class NoRemoteError(GitError):
    def __init__(self, repo):
        message = f"No remotes configured for repository {repo.name}"
        super().__init__(message)


class ScriptExecutionError(TAFError):
    def __init__(self, script: str, error_msg: str):
        message = (
            f"An error happened during execution of script {script}:\n\n: {error_msg}"
        )
        super().__init__(message)
        self.message = message
        self.script = script


class SignersNotLoaded(TAFError):
    def __init__(self, roles):
        message = f"Signers of roles {', '.join(roles)} not loaded."
        super().__init__(message)


class MetadataUpdateError(TAFError):
    def __init__(self, metadata_role: str, message: str):
        super().__init__(
            f"Error happened while updating {metadata_role} metadata role(s):\n\n{message}"
        )
        self.metadata_role = metadata_role
        self.message = message


class MissingInfoJsonError(TAFError):
    pass


class NothingToCommitError(GitError):
    pass


class RootMetadataUpdateError(MetadataUpdateError):
    def __init__(self, message: str):
        super().__init__("root", message)


class KeystoreError(TAFError):
    pass


class PINMissmatchError(Exception):
    pass


class RolesKeyDataConversionError(TAFError):
    def __init__(self, exceptions: List[Exception]):
        message = "\n".join([str(exception) for exception in exceptions])
        super().__init__(message)


class SnapshotMetadataUpdateError(MetadataUpdateError):
    def __init__(self, message: str):
        super().__init__("snapshot", message)


class SigningError(TAFError):
    pass


class TargetsError(TAFError):
    def __init__(self, message: str):
        self.message = message


class TargetsMetadataUpdateError(MetadataUpdateError):
    def __init__(self, message: str):
        super().__init__("targets", message)


class TimestampMetadataUpdateError(MetadataUpdateError):
    def __init__(self, message: str):
        super().__init__("timestamp", message)


class PygitError(TAFError):
    pass


class NoSpeculativeBranchError(TAFError):
    pass


class RepositoriesNotFoundError(TAFError):
    pass


class UpdateFailedError(TAFError):
    pass


class ValidationFailedError(TAFError):
    pass


class YubikeyError(TAFError):
    pass
