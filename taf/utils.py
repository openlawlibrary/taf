import click
import errno
import datetime
import time
import json
import os
import stat
import subprocess
import tempfile
import shutil
import uuid
from getpass import getpass
from functools import wraps
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    load_pem_public_key,
    load_pem_private_key,
)
from json import JSONDecoder
import taf.settings
from taf.exceptions import PINMissmatchError
from taf.log import taf_logger


def _iso_parse(date):
    return datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S.%f")


class IsoDateParamType(click.ParamType):
    name = "iso_date"

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
            name = extract_x509((Path(certs_dir) / keyid + ".pem").read_bytes())["name"]
            if not name:
                print("Cannot extract common name from x509, using key id instead.")
                cert_names.append(keyid)
            else:
                cert_names.append(name)
        except FileNotFoundError:
            print(f"Certificate does not exist ({keyid}).")
    return cert_names


def get_key_size(key_pem_path, decrypt_pwd=None):
    try:
        key = load_pem_public_key(Path(key_pem_path).read_bytes(), default_backend())
    except ValueError:
        key = load_pem_private_key(
            Path(key_pem_path).read_bytes(), decrypt_pwd, default_backend()
        )
    except Exception:
        return 0

    return key.key_size


def get_pin_for(name, confirm=True, repeat=True):
    pin = getpass(f"Enter PIN for {name}: ")
    if confirm:
        if pin != getpass(f"Confirm PIN for {name}: "):
            err_msg = "PINs don't match!"
            if repeat:
                print(err_msg)
                get_pin_for(name, confirm, repeat)
            else:
                raise PINMissmatchError(err_msg)
    return pin


def extract_json_objects_from_trusted_stdout(text, decoder=JSONDecoder()):
    """Find JSON objects in text, and yield the decoded JSON data

    Does not attempt to look for JSON arrays, text, or other JSON types outside
    of a parent JSON object.

    """
    pos = 0
    while True:
        match = text.find("{", pos)
        if match == -1:
            break
        try:
            result, index = decoder.raw_decode(text[match:])
            yield result
            pos = match + index
        except ValueError:
            pos = match + 1


def read_input_dict(value):
    if value is None:
        return {}
    if type(value) is str:
        if Path(value).is_file():
            with open(value) as f:
                try:
                    value = json.loads(f.read())
                except json.decoder.JSONDecodeError:
                    print(f"\nWARNING: {value} is not a valid json!\n")
                    return {}

        else:
            try:
                value = json.loads(value)
            except json.decoder.JSONDecodeError:
                print(f"\nWARNING: {value} is not a valid json!\n")
                return {}

    return value


def run(*command, **kwargs):
    """Run a command and return its output. Call with `debug=True` to print to
    stdout.
    In order to get bytes, call this command with `raw=True` argument.
    """
    # Skip decoding
    raw = kwargs.pop("raw", False)
    data = kwargs.pop("input", None)

    if len(command) == 1 and isinstance(command[0], str):
        command = command[0].split()
    if taf.settings.LOG_COMMAND_OUTPUT:
        taf_logger.debug("About to run command {}", " ".join(command))

    def _format_word(word, **env):
        """To support words such as @{u} needed for git commands."""
        try:
            return word.format(env)
        except KeyError:
            return word

    command = [_format_word(word, **os.environ) for word in command]
    try:
        options = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
        if not raw:
            options.update(universal_newlines=True)
        if data is not None:
            options.update(input=data)

        options.update(kwargs)
        completed = subprocess.run(command, **options)
    except subprocess.CalledProcessError as err:
        if err.stdout:
            taf_logger.debug(err.stdout)
        if err.stderr:
            taf_logger.debug(err.stderr)
        taf_logger.debug(
            "Command {} returned non-zero exit status {} with output {}",
            " ".join(command),
            err.returncode,
            err.output,
        )
        raise err

    if completed.stdout:
        if taf.settings.LOG_COMMAND_OUTPUT:
            taf_logger.debug(completed.stdout)

    if completed.returncode != 0:
        return None

    return completed.stdout if raw else completed.stdout.rstrip()


def normalize_file_line_endings(file_path):
    with open(file_path, "rb") as open_file:
        content = open_file.read()
    replaced_content = normalize_line_endings(content)
    if replaced_content != content:
        with open(file_path, "wb") as open_file:
            open_file.write(replaced_content)


def normalize_line_endings(file_content):
    WINDOWS_LINE_ENDING = b"\r\n"
    UNIX_LINE_ENDING = b"\n"
    replaced_content = file_content.replace(
        WINDOWS_LINE_ENDING, UNIX_LINE_ENDING
    ).rstrip(UNIX_LINE_ENDING)
    return replaced_content


def on_rm_error(_func, path, _exc_info):
    """Used by when calling rmtree to ensure that readonly files and folders
    are deleted.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError as e:
        taf_logger.debug(f"File at path {path} not found, error trace - {e}")
        return
    try:
        os.unlink(path)
    except (OSError, PermissionError) as e:
        taf_logger.debug(
            "WARNING: Failed to clean up temporary update files: {}. This is a known issue when running TAF in a subprocess. You could consider upgrading taf to see if cleanup errors persist",
            e,
        )
        pass


def safely_save_json_to_disk(data, permanent_path):
    tfile = tempfile.NamedTemporaryFile(mode="w+t", delete=False)
    if data is not None:
        json.dump(data, tfile, indent=4)
    else:
        Path(permanent_path).write_text("")

    temp_file_path = tfile.name
    tfile.close()
    safely_move_file(temp_file_path, permanent_path, overwrite=True)


def safely_move_file(src, dst, overwrite=False):
    """Rename a file from ``src`` to ``dst``.

    *   Moves must be atomic.  ``shutil.move()`` is not atomic.
        Note that multiple threads may try to write to the cache at once,
        so atomicity is required to ensure the serving on one thread doesn't
        pick up a partially saved image from another thread.

    *   Moves must work across filesystems.  Often temp directories and the
        cache directories live on different filesystems.  ``os.rename()`` can
        throw errors if run across filesystems.

    So we try ``os.rename()``, but if we detect a cross-filesystem copy, we
    switch to ``shutil.move()`` with some wrappers to make it atomic.
    https://alexwlchan.net/2019/03/atomic-cross-filesystem-moves-in-python/
    MIT licensed.
    """
    src = str(src)
    dst = str(dst)
    if overwrite and os.path.isfile(dst):
        os.remove(dst)
    try:
        os.rename(src, dst)
    except OSError as err:
        if err.errno == errno.EXDEV:
            # Generate a unique ID, and copy `<src>` to the target directory
            # with a temporary name `<dst>.<ID>.tmp`.  Because we're copying
            # across a filesystem boundary, this initial copy may not be
            # atomic.  We intersperse a random UUID so if different processes
            # are copying into `<dst>`, they don't overlap in their tmp copies.
            copy_id = uuid.uuid4()
            tmp_dst = f"{dst}.{copy_id}.tmp"
            shutil.copyfile(src, tmp_dst)
            # Then do an atomic rename onto the new name, and clean up the
            # source image.
            os.rename(tmp_dst, dst)
            os.unlink(src)
        else:
            raise


def to_tuf_datetime_format(start_date, interval):
    """Used to convert datetime to format used while writing metadata:
    e.g. "2020-05-29T21:59:34Z",
    """
    datetime_object = start_date + datetime.timedelta(interval)
    datetime_object = datetime_object.replace(microsecond=0)
    return datetime_object.isoformat() + "Z"


class timed_run:
    """Decorator to let us capture the elapsed time and optionally print a timer and start/end
    messages around function calls"""

    def __init__(self, start_message=None, end_message="  completed in {} seconds"):
        self.start_message = start_message
        self.end_message = end_message
        self.start_time = None
        self.elapsed_time = None

    def start(self):
        self.start_time = time.time()
        if self.start_message is not None:
            print(self.start_message)

    def end(self):
        self.elapsed_time = time.time() - self.start_time
        if self.end_message is not None:
            print(self.end_message.format(int(self.elapsed_time)))

    def __call__(self, orig_func=None):
        @wraps(orig_func)
        def wrapper_func(*args, **kwargs):
            self.start()
            result = orig_func(*args, **kwargs) if orig_func else None
            self.end()
            return result

        return wrapper_func
