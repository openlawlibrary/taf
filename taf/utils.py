import datetime
import logging
import os
import stat
import subprocess
from getpass import getpass
from pathlib import Path

import click
import securesystemslib

import taf.settings
from taf.exceptions import PINMissmatchError

logger = logging.getLogger(__name__)


def _iso_parse(date):
  return datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')


class IsoDateParamType(click.ParamType):
  name = 'iso_date'

  def convert(self, value, param, ctx):
    if value is None:
      return datetime.datetime.now()

    if isinstance(value, datetime.datetime):
      return value
    try:
      return _iso_parse(value)
    except ValueError as ex:
      self.fail(str(ex), param, ctx)


ISO_DATE_PARAM_TYPE = IsoDateParamType()


def extract_x509(cert_pem):
  from cryptography import x509
  from cryptography.hazmat.backends import default_backend

  cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

  def _get_attr(oid):
    attrs = cert.subject.get_attributes_for_oid(oid)
    return attrs[0].value if len(attrs) > 0 else ""

  return {
      "name": _get_attr(x509.OID_COMMON_NAME),
      "organization": _get_attr(x509.OID_ORGANIZATION_NAME),
      "country": _get_attr(x509.OID_COUNTRY_NAME),
      "state": _get_attr(x509.OID_STATE_OR_PROVINCE_NAME),
      "locality": _get_attr(x509.OID_LOCALITY_NAME),
      "valid_from": cert.not_valid_before.strftime("%Y-%m-%d"),
      "valid_to": cert.not_valid_after.strftime("%Y-%m-%d"),
  }


def get_cert_names_from_keyids(certs_dir, keyids):
  cert_names = []
  for keyid in keyids:
    try:
      name = extract_x509((Path(certs_dir) / keyid + ".pem").read_bytes())['name']
      if not name:
        print("Cannot extract common name from x509, using key id instead.")
        cert_names.append(keyid)
      else:
        cert_names.append(name)
    except FileNotFoundError:
      print("Certificate does not exist ({}).".format(keyid))
  return cert_names


def get_pin_for(name, confirm=True, repeat=True):
  pin = getpass('Enter PIN for {}: '.format(name))
  if confirm:
    if pin != getpass('Confirm PIN for {}: '.format(name)):
      err_msg = "PINs don't match!"
      if repeat:
        print(err_msg)
        get_pin_for(name, confirm, repeat)
      else:
        raise PINMissmatchError(err_msg)
  return pin


def run(*command, **kwargs):
  """Run a command and return its output. Call with `debug=True` to print to
  stdout."""
  if len(command) == 1 and isinstance(command[0], str):
    command = command[0].split()
  if taf.settings.LOG_COMMAND_OUTPUT:
    logger.debug('About to run command %s', ' '.join(command))

  def _format_word(word, **env):
    """To support word such as @{u} needed for git commands."""
    try:
      return word.format(env)
    except KeyError:
      return word
  command = [_format_word(word, **os.environ) for word in command]
  try:
    options = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True,
                   universal_newlines=True)
    options.update(kwargs)
    completed = subprocess.run(command, **options)
  except subprocess.CalledProcessError as err:
    if err.stdout:
      logger.debug(err.stdout)
    if err.stderr:
      logger.debug(err.stderr)
    logger.info('Command %s returned non-zero exit status %s', ' '.join(command), err.returncode)
    raise err
  if completed.stdout:
    if taf.settings.LOG_COMMAND_OUTPUT:
      logger.debug(completed.stdout)
  return completed.stdout.rstrip() if completed.returncode == 0 else None


def normalize_file_line_endings(file_path):
  with open(file_path, 'rb') as open_file:
    content = open_file.read()
  replaced_content = normalize_line_endings(content)
  if replaced_content != content:
    with open(file_path, 'wb') as open_file:
      open_file.write(replaced_content)


def normalize_line_endings(file_content):
  WINDOWS_LINE_ENDING = b'\r\n'
  UNIX_LINE_ENDING = b'\n'
  replaced_content = file_content.replace(
      WINDOWS_LINE_ENDING, UNIX_LINE_ENDING).rstrip(UNIX_LINE_ENDING)
  return replaced_content


def on_rm_error(_func, path, _exc_info):
  """Used by when calling rmtree to ensure that readonly files and folders
  are deleted.
  """
  os.chmod(path, stat.S_IWRITE)
  os.unlink(path)


def to_tuf_datetime_format(start_date, interval):
  """Used to convert datetime to format used while writing metadata:
    e.g. "2020-05-29T21:59:34Z",
  """
  datetime_object = start_date + datetime.timedelta(interval)
  datetime_object = datetime_object.replace(microsecond=0)
  return datetime_object.isoformat() + 'Z'


def import_rsa_publickey_from_file(filepath, scheme):
  """
  <Purpose>
    Import the RSA key stored in 'filepath'.  The key object returned is in the
    format 'securesystemslib.formats.RSAKEY_SCHEMA'.  If the RSA PEM in
    'filepath' contains a private key, it is discarded.

  <Arguments>
    filepath:
      <filepath>.pub file, an RSA PEM file.
    scheme:
      RSA signature scheme (str)

  <Exceptions>
    securesystemslib.exceptions.FormatError, if 'filepath' is improperly
    formatted.

    securesystemslib.exceptions.Error, if a valid RSA key object cannot be
    generated.  This may be caused by an improperly formatted PEM file.

  <Side Effects>
    'filepath' is read and its contents extracted.

  <Returns>
    An RSA key object conformant to 'securesystemslib.formats.RSAKEY_SCHEMA'.
  """
  securesystemslib.formats.PATH_SCHEMA.check_match(filepath)
  securesystemslib.formats.RSA_SCHEME_SCHEMA.check_match(scheme)

  # Read the contents of the key file that should be in PEM format and contains
  # the public portion of the RSA key.
  with open(filepath, 'rb') as file_object:
    rsa_pubkey_pem = file_object.read().decode('utf-8')

  # Convert 'rsa_pubkey_pem' to 'securesystemslib.formats.RSAKEY_SCHEMA' format.
  try:
    rsakey_dict = securesystemslib.keys.import_rsakey_from_public_pem(rsa_pubkey_pem,
                                                                      scheme)

  except securesystemslib.exceptions.FormatError as e:
    raise securesystemslib.exceptions.Error('Cannot import improperly formatted'
                                            ' PEM file.' + repr(str(e)))

  return rsakey_dict


def import_rsa_privatekey_from_file(filepath, scheme, password=None):
  """
  <Purpose>
    Import the encrypted PEM file in 'filepath', decrypt it, and return the key
    object in 'securesystemslib.RSAKEY_SCHEMA' format.

  <Arguments>
    filepath:
      <filepath> file, an RSA encrypted PEM file.  Unlike the public RSA PEM
      key file, 'filepath' does not have an extension.

    scheme:
      RSA signature scheme (str)

    password:
      The passphrase to decrypt 'filepath'.

  <Exceptions>
    securesystemslib.exceptions.FormatError, if the arguments are improperly
    formatted.

    securesystemslib.exceptions.CryptoError, if 'filepath' is not a valid
    encrypted key file.

  <Side Effects>
    The contents of 'filepath' is read, decrypted, and the key stored.

  <Returns>
    An RSA key object, conformant to 'securesystemslib.RSAKEY_SCHEMA'.
  """
  securesystemslib.formats.PATH_SCHEMA.check_match(filepath)
  securesystemslib.formats.RSA_SCHEME_SCHEMA.check_match(scheme)

  try:
    private_key = securesystemslib.interface.import_rsa_privatekey_from_file(
        filepath, password, scheme)

  except securesystemslib.exceptions.CryptoError:
    if password is None:
      private_key = securesystemslib.interface.import_rsa_privatekey_from_file(
          filepath, password, prompt=True)

    else:
      raise

  return private_key
