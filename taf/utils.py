import platform
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
import sys

from io import BytesIO
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
from taf.log import taf_logger
import taf.settings
from taf.exceptions import PINMissmatchError
from typing import List, Optional, Tuple, Dict
from securesystemslib.hash import digest_fileobject
from securesystemslib.storage import FilesystemBackend, StorageBackendInterface


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


def is_non_empty_directory(path: Path):
    if path.is_dir():
        return any(path.iterdir())
    return False


def is_run_from_python_executable() -> bool:
    """
    `sys frozen returns True if the Python interpreter is frozen using a tool like pyinstaller.
    """
    return getattr(sys, "frozen", False)


def read_input_dict(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
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
    timeout = kwargs.pop("timeout", None)

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
    if timeout:
        command.append("--progress")
    try:
        options = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if not raw:
            options.update(universal_newlines=True)
        if data is not None:
            options.update(input=data)

        options.update(kwargs)
        if not timeout:
            options.update(check=True)
            completed = subprocess.run(command, **options)
        else:
            options.update(text=True, bufsize=1)
            completed = run_with_timeout(command, options, timeout)

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
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


def run_with_timeout(command, options, timeout=300):
    """Function to run a command with adaptive timeout and handle output."""
    buffer_size = 1024
    last_output_time = time.time()
    last_chunk = None
    with subprocess.Popen(command, **options) as proc:
        last_output_time = time.time()
        while True:
            # Read from stdout with a specific buffer size
            current_chunk = proc.stdout.read(buffer_size)
            if current_chunk:
                if last_chunk != current_chunk:
                    last_chunk = current_chunk
                    last_output_time = time.time()

            if time.time() - last_output_time > timeout:
                proc.kill()
                proc.wait()  # Ensure the process is cleaned up
                raise subprocess.CalledProcessError(
                    1,
                    proc.args,
                    output=None,
                    stderr=f"Command timed out after {timeout} seconds",
                )
            if proc.poll() is not None:
                break  # Process completed
            time.sleep(0.1)

        if proc.returncode == 0:
            return subprocess.CompletedProcess(
                proc.args, proc.returncode, stdout=last_chunk
            )
        else:
            raise subprocess.CalledProcessError(
                proc.returncode, proc.args, output="".join(last_chunk)
            )


def run_subprocess(command):
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True
        ).stdout
        return result
    except subprocess.CalledProcessError as e:
        taf_logger.error("An error occurred while executing {}: {}", command, e.output)
        raise e


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


def secret_yes_no_prompt(message: str) -> bool:
    """
    Ask user a yes/no question about loading more keys in a "hidden" manner.
    The user must type y or n explicitly. Any other input will re-prompt.
    """
    while True:
        response = click.prompt(
            message,
            hide_input=True,
            show_default=False,
            type=str,
        )
        response = response.strip().lower()

        if response in ("y", "n"):
            return response == "y"
        else:
            click.echo("Invalid input. Please type 'y' or 'n'.")


def to_tuf_datetime_format(start_date, interval):
    """Used to convert datetime to format used while writing metadata:
    e.g. "2020-05-29T21:59:34Z",
    """
    datetime_object = start_date + datetime.timedelta(interval)
    datetime_object = datetime_object.replace(microsecond=0)
    return datetime_object.isoformat() + "Z"


def resolve_keystore_path(
    keystore: Optional[str], roles_key_infos: Optional[str]
) -> str:
    if not keystore:
        return ""

    keystore_path = Path(keystore).expanduser().resolve()
    if roles_key_infos:
        roles_key_infos_path = Path(roles_key_infos)
        if roles_key_infos_path.is_file() and not keystore_path.is_absolute():
            keystore_path = (roles_key_infos_path.parent / keystore_path).resolve()

    return str(keystore_path)


def get_file_details(
    filepath: str,
    hash_algorithms: List[str] = ["sha256"],
    storage_backend: Optional[StorageBackendInterface] = None,
) -> Tuple[int, Dict[str, str]]:

    # Making sure that the format of 'filepath' is a path string.
    if not isinstance(filepath, str) or not filepath:
        raise ValueError("The filepath must be a non-empty string.")

    if not isinstance(hash_algorithms, list):
        raise ValueError("The hash_algorithms must be a list.")
    for algo in hash_algorithms:
        if algo not in ["sha256", "sha512"]:  # Add any other valid algorithms as needed
            raise ValueError(f"Invalid hash algorithm: {algo}")

    if storage_backend is None:
        storage_backend = FilesystemBackend()

    # Getting the file length
    if not os.path.isabs(filepath):
        raise ValueError("The 'filepath' must be an absolute path")

    # Check if the file exists and get its size
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"The file at '{filepath}' cannot be opened or found")

    file_length = os.path.getsize(filepath)

    # Getting the file hashes
    file_hashes = {}
    with storage_backend.get(filepath) as fileobj:
        original_content = fileobj.read()
        normalized_content = normalize_line_endings(original_content)
        fileobj = BytesIO(normalized_content)
        for algorithm in hash_algorithms:
            digest_object = digest_fileobject(fileobj, algorithm)
            file_hashes.update({algorithm: digest_object.hexdigest()})
            fileobj.seek(
                0
            )  # Reset file object position after reading for the next hash

    return file_length, file_hashes


def ensure_pre_push_hook(auth_repo_path: Path) -> bool:
    hooks_dir = auth_repo_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pre_push_script = hooks_dir / "pre-push"
    resources_pre_push_script = (
        Path(__file__).parent / "resources" / "pre-push"
    ).resolve()

    # always copy the newest version of the pre-push hook

    shutil.copy(resources_pre_push_script, pre_push_script)
    try:
        if platform.system() != "Windows":
            # Unix-like systems
            pre_push_script.chmod(0o755)
    except Exception as e:
        taf_logger.error(f"Error setting executable permission: {e}")
        return False

    # Check if permissions were set correctly on Unix-like systems
    if platform.system() != "Windows" and not os.access(pre_push_script, os.X_OK):
        taf_logger.error(
            f"Failed to set pre-push git hook executable permission. Please set it manually for {pre_push_script}."
        )
        return False
    taf_logger.info("Pre-push hook updated successfully.")
    return True


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
            # This message should be shown regardless of verbosity setting
            taf_logger.log("NOTICE", self.start_message)

    def end(self):
        self.elapsed_time = time.time() - self.start_time
        if self.end_message is not None:
            taf_logger.log("NOTICE", self.end_message.format(int(self.elapsed_time)))

    def __call__(self, orig_func=None):
        @wraps(orig_func)
        def wrapper_func(*args, **kwargs):
            self.start()
            result = orig_func(*args, **kwargs) if orig_func else None
            self.end()
            return result

        return wrapper_func


class TempPartition:
    def __init__(self, ref_path):
        self.ref_partition = self.get_partition_root(ref_path)
        temp_dir_partition = self.get_partition_root(Path(tempfile.gettempdir()))

        if temp_dir_partition == self.ref_partition:
            self.temp_dir = Path(tempfile.mkdtemp())
        else:
            taf_dir = self.ref_partition / ".taf"
            taf_dir.mkdir(exist_ok=True)
            self.temp_dir = tempfile.mkdtemp(dir=str(taf_dir))

    def get_partition_root(self, path):
        # Get the root directory of the partition containing the specified path
        while not os.path.ismount(path):
            path = path.parent
        return path

    def cleanup(self):
        # Remove the temporary directory and the ".taf" directory
        if Path(self.temp_dir).is_dir():
            shutil.rmtree(self.temp_dir, onerror=on_rm_error)

    def __enter__(self):
        return self.temp_dir, self.partition

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
