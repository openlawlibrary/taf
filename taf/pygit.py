import pygit2
from taf.log import taf_logger as logger
from taf.exceptions import GitError


class PyGitRepository:
    def __init__(
        self,
        encapsulating_repo,
        *args,
        **kwargs,
    ):
        self.encapsulating_repo = encapsulating_repo
        self.path = encapsulating_repo.path
        self.repo = pygit2.Repository(str(self.path))

    def _get_child(self, parent, path_part):
        """
        Return the child object of a parent object.
        Used for walking a git tree.
        """
        try:
            out = parent[path_part]
        except KeyError:
            return None
        else:
            return self.repo[out.id]

    def _get_blob_at_path(self, obj, path):
        """
        for the given commit object,
        get the blob at the given path
        """
        logger.debug("Get blob at path %s", path)
        working = obj.tree
        if path.endswith("/"):
            path = path[:-1]
        path = path.split("/")
        for part in path:
            working = self._get_child(working, part)
            if working is None:
                return None
        if working and isinstance(working, pygit2.Blob):
            logger.debug("Found blob at path %s", "/".join(path))
            return working
        logger.debug("Blob not found at path %s", "/".join(path))
        return None

    def cleanup(self):
        """
        Must call this function in order to release pygit2 file handles.
        """
        self.repo.free()

    def get_file(self, commit, path):
        """
        for the given commit string,
        return the string contents of the blob at the
        given path, if it exists, otherwise raise GitError
        """
        obj = self.repo.get(commit)
        blob = self._get_blob_at_path(obj, path)
        if blob is None:
            raise GitError(
                self.encapsulating_repo,
                message=f"fatal: Path '{path}' does not exist in '{commit}'",
            )
        else:
            return blob.read_raw().decode()
