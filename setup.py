from setuptools import find_packages, setup
from importlib.util import find_spec

PACKAGE_NAME = "taf"
VERSION = "0.18.0"
AUTHOR = "Open Law Library"
AUTHOR_EMAIL = "info@openlawlib.org"
DESCRIPTION = "Implementation of archival authentication"
KEYWORDS = "update updater secure authentication archival"
URL = "https://github.com/openlawlibrary/taf/tree/master"

with open("README.md", encoding="utf-8") as file_object:
    long_description = file_object.read()

packages = find_packages()

# Create platform specific wheel
# https://stackoverflow.com/a/45150383/9669050
try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel

    class bdist_wheel(_bdist_wheel):
        def finalize_options(self):
            _bdist_wheel.finalize_options(self)
            self.root_is_pure = False

except ImportError:
    bdist_wheel = None

ci_require = [
    "bandit>=1.6.0",
    "black>=19.3b0",
    "coverage==4.5.3",
    "pre-commit>=1.18.3",
    "pytest-cov==2.7.1",
    "freezegun==0.3.15",
]

dev_require = ["bandit>=1.6.0", "black>=19.3b0", "pre-commit>=1.18.3"]

tests_require = [
    "pytest==6.2.5",
    "freezegun==0.3.15",
    "jsonschema==3.2.0",
]

yubikey_require = ["yubikey-manager==3.0.0"]

kwargs = {
    "name": PACKAGE_NAME,
    "version": VERSION,
    "description": DESCRIPTION,
    "long_description": long_description,
    "long_description_content_type": "text/markdown",
    "url": URL,
    "author": AUTHOR,
    "author_email": AUTHOR_EMAIL,
    "keywords": KEYWORDS,
    "packages": packages,
    "cmdclass": {"bdist_wheel": bdist_wheel},
    "include_package_data": True,
    "data_files": [("lib/site-packages/taf", ["./LICENSE.txt", "./README.md"])],
    "zip_safe": False,
    "install_requires": [
        "click==7.1",
        "colorama>=0.3.9",
        "oll-tuf==0.11.2.dev9",
        "loguru==0.4.0",
        "cryptography==3.2.1",
        "pyOpenSSL==20.0.1",
        "pygit2==0.28.2;python_version=='3.6'",
        "pygit2==1.9.*;python_version>='3.7'",
        "cattrs==1.*",
    ],
    "extras_require": {
        "ci": ci_require,
        "test": tests_require,
        "dev": dev_require,
        "yubikey": yubikey_require,
    },
    "tests_require": tests_require,
    "entry_points": {
        "console_scripts": [
            "taf = taf.tools.cli.taf:main",
            "olc = taf.tools.cli.olc:main",
        ],
        "pytest11": ["taf_yubikey_utils = taf.tests.yubikey_utils"],
    },
    "classifiers": [
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Topic :: Security",
        "Topic :: Software Development",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: Implementation :: CPython",
    ],
}


try:
    tests_exist = find_spec("taf.tests")
except ModuleNotFoundError:
    tests_exist = False
if tests_exist:
    kwargs["entry_points"]["pytest11"] = (
        ["taf_yubikey_utils = taf.tests.yubikey_utils"],
    )

setup(**kwargs)
