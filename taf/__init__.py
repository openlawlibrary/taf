"""Add platform-dependent libraries to the path.
"""
import os
import sys
from pathlib import Path


class YubikeyMissingLibrary:
    """If `yubikey-manager` is not installed and we try to use any function from `taf.yubikey`
    module, we will log appropriate error message and exit with code 1.
    """

    ERR_MSG = '"yubikey-manager" is not installed. Run "pip install taf[yubikey]" to install it.'

    def __getattr__(self, name):
        from taf.log import taf_logger

        taf_logger.warning(YubikeyMissingLibrary.ERR_MSG)
        sys.exit(1)


_PLATFORM = sys.platform

_PLATFORM_LIBS = str((Path(__file__).parent / "libs").resolve())


def _set_env(env_name, path):
    try:
        os.environ[env_name] += os.pathsep + path
    except KeyError:
        os.environ[env_name] = path


if _PLATFORM == "darwin":
    _set_env("DYLD_LIBRARY_PATH", _PLATFORM_LIBS)
elif _PLATFORM == "linux":
    _set_env("LD_LIBRARY_PATH", _PLATFORM_LIBS)
elif _PLATFORM == "win32":
    _set_env("PATH", _PLATFORM_LIBS)
else:
    raise Exception(f'Platform "{_PLATFORM}" is not supported!')


def _tuf_patches():
    from functools import wraps
    import tuf.repository_lib
    import tuf.repository_tool

    from taf.utils import normalize_file_line_endings

    # Replace staging metadata directory name
    tuf.repository_tool.METADATA_STAGED_DIRECTORY_NAME = (
        tuf.repository_tool.METADATA_DIRECTORY_NAME
    )

    # Replace get_metadata_fileinfo with file-endings normalization
    def get_metadata_fileinfo(get_metadata_fileinfo_fn):
        @wraps(get_metadata_fileinfo_fn)
        def normalized(filename, custom=None):
            normalize_file_line_endings(filename)
            return get_metadata_fileinfo_fn(filename, custom=None)

        return normalized

    tuf.repository_lib.get_metadata_fileinfo = get_metadata_fileinfo(
        tuf.repository_lib.get_metadata_fileinfo
    )


_tuf_patches()
