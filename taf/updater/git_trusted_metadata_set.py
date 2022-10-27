import datetime
from tuf.ngclient._internal import trusted_metadata_set


class GitTrustedMetadataSet(trusted_metadata_set.TrustedMetadataSet):
    """
    This class represents a "divergence" from TUF metadata validation.
    TUF, by design, checks if metadata expired by validating "expiration_date" field during "refresh".
    As of TUF 2.0.0, this means that "expiration_date" from the loaded metadata is compared to current time,
    which only makes sense when we're validating the latest metadata. However,
    TAF validates metadata across history. We do not want to validate expiration for each commit (revision),
    since it will always be considered "expired".
    Instead, for each revision in commit history we override the "reference_time" attribute so that
    past metadata will not be considered expired.

    See: GitUpdater
    """

    def __init__(self, data):
        super(GitTrustedMetadataSet, self).__init__(data)
        self.reference_time = datetime.datetime.min
