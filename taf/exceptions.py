class TAFError(Exception):
    pass

    def __str__(self):
        try:
            return self.message
        except AttributeError:
            return super().__str__()


class CloneRepoException(TAFError):
    def __init__(self, repo):
        self.message = (
            f"Cannot clone {repo.name} from any of the following URLs: {repo.repo_urls}"
        )


class FetchException(TAFError):
    def __init__(self, path):
        self.message = f"Cannot fetch changes. Repo: {path}"


class GitError(TAFError):
    def __init__(self, repo, command=None, error=None, message=None):
        if message is None:
            if command is not None:
                message = f"error occurred while executing {command}"
                if error is not None:
                    message = f"{message}:\n{error.output}"
            elif error is not None:
                message = error.output
            else:
                message = "error occurred"
        self.message = f"{repo.log_prefix}{message}"
        self.repo = repo
        self.command = command
        self.error = error


class InvalidBranchError(TAFError):
    pass


class InvalidCommitError(TAFError):
    pass


class InvalidKeyError(TAFError):
    def __init__(self, metadata_role):
        super().__init__(
            f"Cannot sign {metadata_role} metadata file with inserted key."
        )


class InvalidOrMissingMetadataError(TAFError):
    pass


class InvalidRepositoryError(TAFError):
    pass


class InvalidPINError(TAFError):
    pass


class RepositoryInstantiationError(TAFError):
    def __init__(self, repo_path, message):
        super().__init__(f"Could not instantiate repository {repo_path}\n\n: {message}")
        self.repo_path = repo_path
        self.message = message


class MetadataUpdateError(TAFError):
    def __init__(self, metadata_role, message):
        super().__init__(
            f"Error happened while updating {metadata_role} metadata role(s):\n\n{message}"
        )
        self.metadata_role = metadata_role
        self.message = message


class RootMetadataUpdateError(MetadataUpdateError):
    def __init__(self, message):
        super().__init__("root", message)


class KeystoreError(TAFError):
    pass


class PINMissmatchError(Exception):
    pass


class SnapshotMetadataUpdateError(MetadataUpdateError):
    def __init__(self, message):
        super().__init__("snapshot", message)


class SigningError(TAFError):
    pass


class TargetsError(TAFError):
    def __init__(self, message):
        self.message = message


class TargetsMetadataUpdateError(MetadataUpdateError):
    def __init__(self, message):
        super().__init__("targets", message)


class TimestampMetadataUpdateError(MetadataUpdateError):
    def __init__(self, message):
        super().__init__("timestamp", message)


class NoSpeculativeBranchError(TAFError):
    pass


class RepositoriesNotFoundError(TAFError):
    pass


class UpdateFailedError(TAFError):
    pass


class YubikeyError(Exception):
    pass
