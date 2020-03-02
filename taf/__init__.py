"""Add platform-dependent libraries to the path.
"""
import os
import sys
from pathlib import Path

import tuf.repository_tool

tuf.repository_tool.METADATA_STAGED_DIRECTORY_NAME = (
    tuf.repository_tool.METADATA_DIRECTORY_NAME
)


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
