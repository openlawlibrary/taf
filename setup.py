from setuptools import find_packages, setup

PACKAGE_NAME = "taf"
VERSION = "0.35.5"
AUTHOR = "Open Law Library"
AUTHOR_EMAIL = "info@openlawlib.org"
DESCRIPTION = "Implementation of archival authentication"
KEYWORDS = "update updater secure authentication archival"
URL = "https://github.com/openlawlibrary/taf/tree/master"

with open("README.md", encoding="utf-8") as file_object:
    long_description = file_object.read()

packages = find_packages()

ci_require = [
    "bandit>=1.6.0",
    "black>=19.3b0",
    "coverage==4.5.3",
    "pre-commit>=1.18.3",
    "pytest-cov==2.7.1",
    "freezegun==0.3.15",
]

executable_require = ["lxml"]

dev_require = ["bandit>=1.6.0", "black>=19.3b0", "pre-commit>=1.18.3"]

tests_require = [
    "pytest==8.*",
    "freezegun==0.3.15",
    "jsonschema==3.2.0",
    "jinja2==3.1.*",
    "pytest-mock==3.14.*",
    "pytest-benchmark==4.0.0",
]

yubikey_require = [
    "yubikey-manager==5.5.*",
    "pyscard==2.2.1; python_version >= '3.9'",
]


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
    "include_package_data": True,
    "data_files": [("lib/site-packages/taf", ["./LICENSE.md", "./README.md"])],
    "zip_safe": False,
    "install_requires": [
        "cattrs>=23.1.2",
        "click==8.*",
        "colorama>=0.3.9",
        "tuf==5.*",
        "cryptography==43.0.*",
        "securesystemslib==1.*",
        "loguru==0.7.*",
        'pygit2==1.9.*; python_version < "3.11"',
        'pygit2==1.14.*; python_version >= "3.11"',
        "pyOpenSSL==24.2.*",
        "logdecorator==2.*",
        "tomli==2.0.*",
    ],
    "extras_require": {
        "ci": ci_require,
        "test": tests_require,
        "dev": dev_require,
        "yubikey": yubikey_require,
        "executable": executable_require,
    },
    "tests_require": tests_require,
    "entry_points": {
        "console_scripts": [
            "taf = taf.tools.cli.taf:taf",
            "olc = taf.tools.cli.olc:main",
        ],
    },
    "classifiers": [
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Topic :: Security",
        "Topic :: Software Development",
        "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: Implementation :: CPython",
    ],
}

setup(**kwargs)
