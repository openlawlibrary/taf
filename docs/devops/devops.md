# CI

Our CI is implemented using GitHub Actions, with the configuration file located in the `.github/workflows` directory. This workflow covers testing, building, and deploying wheels and executables following a release.

## run_tests

The first job, `run_tests`, runs the test suite across multiple Python versions on an Ubuntu environment. The critical steps include:

1. **Installing System Libraries:** On Linux, the following libraries need to be installed: `libhdf5-serial-dev`, `zlib1g-dev`, `libatlas-base-dev`, `lcov`, `swig3.0`, and `libpcsclite-dev`. They are required by the YubiKey manager dependency, which provides the ability to sign using YubiKeys (hardware keys).

2. **Creating Symlink for SWIG:** A symbolic link is created for `swig3.0` to ensure it is accessible as `swig`, allowing the system to find the required SWIG version easily.

3. **Installing Project Dependencies:** The project dependencies, including those needed for YubiKey integration, are installed.

4. **Configuring GitHub User:** Git is configured with a username and email to ensure any Git operations during the workflow do not fail.

5. **Running Pre-Commit Hooks and Tests:** The pre-commit hooks are executed to enforce code quality checks before running the test suite with `pytest`, ensuring all tests pass across the supported Python versions. If pre-commit hooks reformat any file or if flake8 or mypy issues are detected, the build will fail.

### Building and Uploading Wheels

The `build_and_upload_wheel` job builds and uploads the Python wheel to PyPI upon a release event. Key steps include:

1. **Installing System Libraries:** The same essential libraries as in the test job are installed, ensuring a consistent build environment.

2. **Installing Project and Building Wheel:** The `TAF` package and its dependencies are installed, and the package is built into a source distribution (`sdist`) and a wheel (`bdist_wheel`).

3. **Installing Publishing Dependencies:** `twine` is installed to handle the verification and upload of the built wheels.

4. **Uploading to PyPI:** The built wheels are verified with `twine check` and then uploaded to PyPI using `twine upload`. This step ensures the package is available for users to install via PyPI.

It can be noted that in the past, we used to download platform-specific DLLs required by the YubiKey manager and package them into wheels. Therefore, we were building platform-specific wheels. The DLLs are no longer required. On Linux, it is still necessary to install certain system libraries: `libhdf5-serial-dev`, `zlib1g-dev`, `libatlas-base-dev`, `lcov`, `swig3.0`, and `libpcsclite-dev`.

When testing the CI, wheels can be uploaded to TestPyPi. Replace the upload step with the following one:



```

  - name: Upload to TestPyPi
    run: |
      twine check dist/*
      twine upload --repository-url https://test.pypi.org/legacy/ dist/*
    env:
      TWINE_USERNAME: ${{ secrets.TEST_PYPI_USERNAME }}
      TWINE_PASSWORD: ${{ secrets.TEST_PYPI_PASSWORD }}
```


### Building and Testing Standalone Executables

The `build-and-test-executables` job creates standalone executables for Linux, Windows, and macOS. Each platform has specific steps:

1. **Setting Up System Dependencies:**
    - **Linux:** Installs libraries like `libhdf5-serial-dev`, `zlib1g-dev`, `libatlas-base-dev`, `lcov`, `swig3.0`, and `libpcsclite-dev`. A symlink for `swig3.0` is created.
    - **Windows:** Installs `swig` using `choco`.
    - **macOS:** Installs `swig` using `brew`.

2. **Installing Project Dependencies:** Installs the `TAF` package with YubiKey support and `pyinstaller` to facilitate the creation of standalone executables.

3. **Building Executables:** One executable is built for each platform - Windows, Linux, and macOS.

4. **Uploading Executables:** The built executables are uploaded as release assets to GitHub. The `upload-release-asset` action is used to handle this process.
