class TAFError(Exception):
  pass


class InvalidBranchError(TAFError):
  pass


class InvalidCommitError(TAFError):
  pass


class InvalidKeyError(TAFError):
  def __init__(self, metadata_role):
    super().__init__('Cannot sign {} metadata file with inserted key.'.format(metadata_role))


class InvalidOrMissingMetadataError(TAFError):
  pass


class InvalidRepositoryError(TAFError):
  pass


class MetadataUpdateError(TAFError):
  def __init__(self, metadata_role, message):
    super().__init__('Error happened while updating {} metadata role(s):\n\n{}'
                     .format(metadata_role, message))
    self.metadata_role = metadata_role
    self.message = message


class RootMetadataUpdateError(MetadataUpdateError):
  def __init__(self, message):
    super().__init__('root', message)


class PINMissmatchError(Exception):
  pass


class SnapshotMetadataUpdateError(MetadataUpdateError):
  def __init__(self, message):
    super().__init__('snapshot', message)


class TargetsMetadataUpdateError(MetadataUpdateError):
  def __init__(self, message):
    super().__init__('targets', message)


class TimestampMetadataUpdateError(MetadataUpdateError):
  def __init__(self, message):
    super().__init__('timestamp', message)


class NoSpeculativeBranchError(TAFError):
  pass


class RepositoriesNotFoundError(TAFError):
  pass


class UpdateFailedError(TAFError):
  pass


class YubikeyError(Exception):
  pass
