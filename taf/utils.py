import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def run(*command, **kwargs):
  """Run a command and return its output. Call with `debug=True` to print to
  stdout."""
  if len(command) == 1 and isinstance(command[0], str):
    command = command[0].split()
  logger.debug(*command)

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
    logger.debug('Command "{}" returned non-zero exit status {}'
                 .format(' '.join(command), err.returncode))
    raise err
  if completed.stdout:
    logger.debug(completed.stdout)
  return completed.stdout.rstrip() if completed.returncode == 0 else None
