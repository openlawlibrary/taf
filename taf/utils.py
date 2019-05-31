import datetime
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def run(*command, **kwargs):
  """Run a command and return its output. Call with `debug=True` to print to
  stdout."""
  if len(command) == 1 and isinstance(command[0], str):
    command = command[0].split()
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
    logger.debug('Command %s returned non-zero exit status %s', ' '.join(command), err.returncode)
    raise err
  if completed.stdout:
    logger.debug(completed.stdout)
  return completed.stdout.rstrip() if completed.returncode == 0 else None


def normalize_file_line_endings(file_path):
  # replacement strings
  WINDOWS_LINE_ENDING = b'\r\n'
  UNIX_LINE_ENDING = b'\n'
  with open(file_path, 'rb') as open_file:
    content = open_file.read()

  replaced_content = content.replace(WINDOWS_LINE_ENDING, UNIX_LINE_ENDING)

  if replaced_content != content:
    with open(file_path, 'wb') as open_file:
      open_file.write(replaced_content)


def to_tuf_datetime_format(start_date, interval):
  datetime_object = start_date + datetime.timedelta(interval)
  datetime_object = datetime_object.replace(microsecond=0)
  return datetime_object.isoformat() + 'Z'
