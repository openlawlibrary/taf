import datetime
import logging
import os
import stat
import subprocess
from getpass import getpass

import click

import taf.settings
from oll_sc.api import sc_is_present
from oll_sc.exceptions import SmartCardError
from taf.exceptions import PINMissmatchError
from taf.repository_tool import get_yubikey_public_key

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


def get_pin_for(name, confirm=True):
  pin = getpass('Enter PIN for {}: '.format(name))
  if confirm:
    if pin != getpass('Confirm PIN for {}: '.format(name)):
      raise PINMissmatchError("PINs doesn't match!")
  return pin


def get_yubikey_pin_for_keyid(expected_keyids, key_slot=(2,), holders_name=' '):
  if isinstance(expected_keyids, str):
    expected_keyids = (expected_keyids)
  if isinstance(key_slot, int) or isinstance(key_slot, str):
    key_slot = (int(key_slot),)

  while True:
    try:
      input("Please insert {} yubikey and press ENTER.\n".format(holders_name))
      if not sc_is_present():
        continue

      key_pin = get_pin_for(holders_name)
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
