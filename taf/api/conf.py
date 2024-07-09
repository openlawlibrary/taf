from typing import Optional
from pathlib import Path
from taf.api.keystore import generate_keys
from taf.log import taf_logger


def init(path: Optional[str] = None, build_keys: bool = False):
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

    # Create the config.toml file
    config_file_path = taf_directory / "config.toml"
    config_file_path.touch()  # Create an empty file

    # Create the keystore directory
    keystore_directory = taf_directory / "keystore"
    keystore_directory.mkdir(exist_ok=True)
    taf_logger.info("Generated .taf directory")

    generate_keys_flag = build_keys

    if not build_keys:
        # Prompt the user if they want to run the generate_keys function
        while True:
            use_keystore = (
                input("Do you want to generate keys in the keystore directory? [y/N]: ")
                .strip()
                .lower()
            )
            if use_keystore in ["y", "n"]:
                generate_keys_flag = use_keystore == "y"
                break

    if generate_keys_flag:
        keystore_path = keystore_directory
        roles_key_infos = input(
            "Enter the path to the keys description JSON file (can be left empty): "
        ).strip()

        generate_keys(str(keystore_path), roles_key_infos)
        taf_logger.info("Completed generating keys in the keystore directory")
