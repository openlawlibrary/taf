from setuptools import find_packages, setup

PACKAGE_NAME = 'taf'
VERSION = '0.1.6'
AUTHOR = 'Open Law Library'
AUTHOR_EMAIL = 'info@openlawlib.org'
DESCRIPTION = 'Implementation of archival authentication'
KEYWORDS = 'update updater secure authentication archival'
URL = 'https://github.com/openlawlibrary/taf/tree/master'

with open('README.md', encoding='utf-8') as file_object:
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
    "pylint==2.3.1",
    "bandit==1.6.0",
    "coverage==4.5.3",
    "pytest-cov==2.7.1",
]

dev_require = [
    "autopep8==1.4.4",
    "pylint==2.3.1",
    "bandit==1.6.0",
]

tests_require = [
    "pytest==4.5.0",
]

yubikey_require = [
    "yubikey-manager==3.0.0",
]

setup(
    name=PACKAGE_NAME,
    version=VERSION,
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type='text/markdown',
    url=URL,
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    keywords=KEYWORDS,
    packages=packages,
    cmdclass={'bdist_wheel': bdist_wheel},
    include_package_data=True,
    data_files=[
        ('lib/site-packages/taf', [
            './LICENSE.txt',
            './README.md'
        ])
    ],
    zip_safe=False,
    install_requires=[
        'click==6.7',
        'colorama>=0.3.9'
        'cryptography>=2.3.1',
        'oll-tuf==0.11.2.dev8',
    ],
    extras_require={
        'ci': ci_require,
        'test': tests_require,
        'dev': dev_require,
        'yubikey': yubikey_require,
    },
    tests_require=tests_require,
    entry_points={
        'console_scripts': [
            'taf = taf.cli:main'
        ]
    },
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Topic :: Security',
        'Topic :: Software Development',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
    ]
)
