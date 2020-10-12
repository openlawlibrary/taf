# Building Wheels

TAF has an option to sign files with external token (Yubikey) which can be enabled by installing an extra dependency `[yubikey]`.
We use official library `yubikey-manager` to communicate with Yubikey, which relies on system dependent libraries (DLLs, dylibs, so).
In order for signing to work without any additional installations, we are building platform specific wheels which contain all needed platform dependent libraries.

Important files:

- [setup.py](../setup.py) is extended with `cmdclass={"bdist_wheel": bdist_wheel},` which ensures that platform specific wheels will be built
- [libs](../taf/libs) directory contains all DLLs/dylibs/so files

  - libykpers
  - libyubikey
  - libusb
  - libjson-c

- [\_\_init\_\_.py](../taf/__init__.py) adds all files from `libs` to a specific environment variable

## azure-pipelines.yml

This script contains all the logic for downloading and packaging platform specific files when building wheels.

### Platforms

Section `strategy` defines for which platform/architecture and python version TAF wheels are built.

To add a new python version you can extend `matrix` section with the following template:

```txt
linux-ubuntu-16-04-{PYTHON_VERSION_JOB_NAME}:
  imageName: "ubuntu-16.04"
  pythonVersion: {PYTHON_VERSION}
macOS-{PYTHON_VERSION_JOB_NAME}:
  imageName: "macOS-10.14"
  pythonVersion: {PYTHON_VERSION}
windows-64bit-{PYTHON_VERSION_JOB_NAME}:
  imageName: "vs2017-win2016"
  pythonVersion: {PYTHON_VERSION}
  platform: x64
  winArch: "win64"
windows-32bit-{PYTHON_VERSION_JOB_NAME}:
  imageName: "vs2017-win2016"
  pythonVersion: {PYTHON_VERSION}
  platform: x86
  winArch: "win32"
```

with replaced values of `{PYTHON_VERSION_JOB_NAME}` (e.g. py36) and `{PYTHON_VERSION}` (e.g. '3.6').

### Steps explained

- `UsePythonVersion@0` - set python version
- `Linus/masOS/Windows Setup` - downloads "libykpers, libyubikey, libusb, libjson-c" and copies files inside "taf/libs" directory
- `Build TAF` - build wheels
- `PublishBuildArtifacts` - uploads [artifacts](https://dev.azure.com/openlawlibrary/TAF/_build/results?buildId=476&view=artifacts) to the azure job
- `Upload wheels` - when new tag is pushed, uploads wheels to `pypi`
