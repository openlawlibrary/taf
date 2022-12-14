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
    if hasattr(os, "add_dll_directory"):  # python 3.8
        os.add_dll_directory(_PLATFORM_LIBS)
    else:
        _set_env("PATH", _PLATFORM_LIBS)
else:
    raise Exception(f'Platform "{_PLATFORM}" is not supported!')
