from shutil import Error, copytree
from typing import Optional
from pathlib import Path
from taf.api.keystore import generate_keys
from taf.log import taf_logger


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
        taf_logger.info(".taf directory already exists.")
    else:
        # Create the .taf directory
        taf_directory.mkdir(exist_ok=True)
        taf_logger.info("Generated .taf directory")

    # Create the config.toml file
    config_file_path = taf_directory / "config.toml"
    config_file_path.touch()  # Create an empty file

    # Create the keystore directory
    keystore_directory = taf_directory / "keystore"
    keystore_directory.mkdir(exist_ok=True)

    # If any of these parameters exist you can assume the user wants to generate keys
    if not keystore and not roles_key_infos:
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
    if should_generate_keys or (keystore and not roles_key_infos):
        # First check if the user already specified keystore
        if not keystore:
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
                        break
                    else:
                        taf_logger.error(
                            f"Provided keystore path {keystore} is invalid."
                        )
        # Check if keystore is specified now. If so copy the keys
        if keystore:
            try:
                copytree(keystore, keystore_directory, dirs_exist_ok=True)
                taf_logger.info(
                    f"Copied keystore from {keystore} to {keystore_directory}"
                )
            except FileNotFoundError:
                taf_logger.error(f"Provided keystore path {keystore} not found.")
            except Error as e:
                taf_logger.error(f"Error occurred while copying keystore: {e}")

        # If there is no keystore path specified, ask for keys description and generate keys
        elif not roles_key_infos:
            roles_key_infos = input(
                "Enter the path to the keys description JSON file (can be left empty): "
            ).strip()
            if not roles_key_infos:
                roles_key_infos = "."
    if roles_key_infos:
        generate_keys(keystore_directory, roles_key_infos)
        taf_logger.info(
            f"Successfully generated keys inside the {keystore_directory} directory"
        )
