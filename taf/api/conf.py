from shutil import Error, copytree
import shutil
from typing import Optional
from pathlib import Path
from taf.api.keystore import generate_keys
from taf.log import taf_logger
from taf.utils import read_input_dict


def init(
    path: Optional[str] = None,
    keystore: Optional[str] = None,
    roles_key_infos: Optional[str] = None,
):
    # Determine the directory path
    if path:
        taf_directory = Path(path) / ".taf"
    else:
        taf_directory = Path(".taf")

    if taf_directory.exists() and taf_directory.is_dir():
        taf_logger.log("NOTICE", ".taf directory already exists.")
    else:
        # Create the .taf directory
        taf_directory.mkdir(exist_ok=True)
        taf_logger.log("NOTICE", "Generated .taf directory")

    # Create the config.toml file
    config_file_path = taf_directory / "config.toml"
    config_file_path.touch()  # Create an empty file

    # Create the keystore directory
    keystore_directory = taf_directory / "keystore"
    keystore_directory.mkdir(exist_ok=True)

    # If any of these parameters exist you can assume the user wants to generate keys

    # check if keystore already exists
    roles_key_infos_dict = read_input_dict(roles_key_infos)
    keystore = (
        keystore or (roles_key_infos and roles_key_infos_dict.get("keystore")) or None
    )
    should_generate_keys = False
    keystore_path = Path(keystore) if keystore else None
    if not keystore:
        # Prompt the user if they want to run the generate_keys function
        while True:
            use_keystore = (
                input("Do you want to generate keys in the keystore directory? [y/N]: ")
                .strip()
                .lower()
            )
            if use_keystore in ["y", "n"]:
                should_generate_keys = use_keystore == "y"
                break

        if should_generate_keys:
            # First check if the user already specified keystore
            copy_keystore = (
                input(
                    "Do you want to load an existing keystore from another location? [y/N]: "
                )
                .strip()
                .lower()
            )
            if copy_keystore == "y":
                while True:
                    keystore_input = input(
                        "Enter the path to the existing keystore:"
                    ).strip()
                    keystore_path = Path(keystore_input)
                    if keystore_path.exists() and keystore_path.is_dir():
                        keystore = keystore_input  # Assign the string path to the keystore variable
                        should_generate_keys = (
                            False  # no need to generate keys, they will be copied
                        )
                        break
                    else:
                        taf_logger.error(
                            f"Provided keystore path {keystore} is invalid."
                        )
    # Check if keystore is specified now. If so copy the keys
    if keystore and keystore_path and keystore_path.is_dir():
        try:
            copytree(keystore, keystore_directory, dirs_exist_ok=True)
            taf_logger.log(
                "NOTICE", f"Copied keystore from {keystore} to {keystore_directory}"
            )
        except FileNotFoundError:
            taf_logger.error(f"Provided keystore path {keystore} not found.")
        except Error as e:
            taf_logger.error(f"Error occurred while copying keystore: {e}")

    if should_generate_keys:
        generate_keys(keystore_directory, roles_key_infos)
        taf_logger.log(
            "NOTICE",
            f"Successfully generated keys inside the {keystore_directory} directory",
        )

    if roles_key_infos is not None and Path(roles_key_infos).is_file():
        infos_config_path = (taf_directory / Path(roles_key_infos).name).absolute()
        shutil.copy(str(roles_key_infos), str(infos_config_path))
