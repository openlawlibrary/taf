import os
import sys
from pathlib import Path

_YKPERS_PATH = str((Path(__file__).parent.parent / 'ykpers').resolve())
_PLATFORM = sys.platform


def _set_env(env_name, path):
  try:
    os.environ[env_name] += os.pathsep + path
  except KeyError:
    os.environ[env_name] = path


if _PLATFORM == 'darwin':
  _set_env('DYLD_LIBRARY_PATH', _YKPERS_PATH)
elif _PLATFORM == 'linux':
  _set_env('LD_LIBRARY_PATH', _YKPERS_PATH)
elif _PLATFORM == 'win32':
  _set_env('PATH', _YKPERS_PATH)
else:
  raise Exception('Platform "{}" is not supported!'.format(_PLATFORM))


# ON macOS
# BEFORE PACKAGING

# install_name_tool -change @executable_path/../lib/libyubikey.0.dylib @loader_path/libyubikey.0.dylib libykpers-1.dylib
# install_name_tool -change @executable_path/../lib/libjson-c.2.dylib @loader_path/libjson-c.2.dylib libykpers-1.dylib
