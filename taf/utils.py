import datetime
import json
import os
import stat
import subprocess
from getpass import getpass
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    load_pem_public_key,
    load_pem_private_key,
)

import click
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
    stdout."""
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
        options = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
            universal_newlines=True,
        )
        options.update(kwargs)
        completed = subprocess.run(command, **options)
    except subprocess.CalledProcessError as err:
        if err.stdout:
            taf_logger.debug(err.stdout)
        if err.stderr:
            taf_logger.debug(err.stderr)
        taf_logger.debug(
            "Command {} returned non-zero exit status {}",
            " ".join(command),
            err.returncode,
        )
        raise err
    if completed.stdout:
        if taf.settings.LOG_COMMAND_OUTPUT:
            taf_logger.debug(completed.stdout)
    return completed.stdout.rstrip() if completed.returncode == 0 else None


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
    os.chmod(path, stat.S_IWRITE)
    os.unlink(path)


def to_tuf_datetime_format(start_date, interval):
    """Used to convert datetime to format used while writing metadata:
    e.g. "2020-05-29T21:59:34Z",
    """
    datetime_object = start_date + datetime.timedelta(interval)
    datetime_object = datetime_object.replace(microsecond=0)
    return datetime_object.isoformat() + "Z"
