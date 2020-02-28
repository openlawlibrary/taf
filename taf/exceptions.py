class TAFError(Exception):
    pass


class CloneRepoException(TAFError):
    def __init__(self, url):
        self.message = f"Cannot clone from {url}"


class FetchException(TAFError):
    def __init__(self, path):
        self.message = f"Cannot fetch changes. Repo: {path}"


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
    pass


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
