import datetime
import logging
import os
import stat
import subprocess
from getpass import getpass
from pathlib import Path

import click

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
      err_msg = "PINs doesn't match!"
      if repeat:
        print(err_msg)
        get_pin_for(name, confirm, repeat)
      else:
        raise PINMissmatchError(err_msg)
  return pin


def get_yubikey_pin_for_keyid(expected_keyids, key_slot=(2,), holders_name=' '):
  from taf.repository_tool import get_yubikey_public_key
  from oll_sc.api import sc_is_present
  from oll_sc.exceptions import SmartCardError

  if isinstance(expected_keyids, str):
    expected_keyids = (expected_keyids)
  if isinstance(key_slot, int) or isinstance(key_slot, str):
    key_slot = (int(key_slot),)

  while True:
    try:
      input("Please insert {}'s yubikey and press ENTER.\n".format(holders_name))
      if not sc_is_present():
        continue

      key_pin = get_pin_for(holders_name, confirm=False)
      inserted_key = get_yubikey_public_key(key_slot, key_pin)
      if inserted_key['keyid'] not in expected_keyids:
        print("Please insert valid yubikey!")
        continue

      return key_pin

    except (PINMissmatchError, SmartCardError) as e:
      print(str(e))
      continue


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
  with open(file_path, 'r') as open_file:
    content = open_file.read()

  replaced_content = normalize_line_endings(content)
  if replaced_content != content:
    with open(file_path, 'w') as open_file:
      open_file.write(replaced_content)


def normalize_line_endings(file_content):

  WINDOWS_LINE_ENDING = '\r\n'
  UNIX_LINE_ENDING = '\n'
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
