
import os

from setuptools import find_packages, setup

PACKAGE_NAME = 'taf'
VERSION = '0.1.0'
AUTHOR = 'Open Law Library'
AUTHOR_EMAIL = 'info@openlawlib.org'
DESCRIPTION = 'Implementation of archival authentication'
KEYWORDS = 'update updater secure authentication archival'
URL = 'https://github.com/openlawlibrary/taf/tree/master'

with open('README.md', encoding='utf-8') as file_object:
  long_description = file_object.read()

packages = find_packages()

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
  include_package_data=True,
  data_files=[
    ('lib/site-packages/taf', [
      './LICENSE.txt',
      './README.md'
    ])
  ],
  zip_safe=False,
  install_requires = [
    'oll-tuf'
  ],
  entry_points={
        'console_scripts': [
            'taf = taf.oll.cli:main'
        ]
  },
  classifiers=[
    'Development Status :: 2 - Pre-Alpha',
    'Intended Audience :: Developers',
    'Intended Audience :: Information Technology',
    'Topic :: Security',
    'Topic :: Software Development'
    'License :: OSI Approved :: Apache Software License',
    'Operating System :: OS Independent',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Programming Language :: Python :: Implementation :: CPython',
  ]
)
