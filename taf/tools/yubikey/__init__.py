import click
import taf.developer_tool as developer_tool


def attach_to_group(group):

    @group.group()
    def yubikey():
        pass

    @yubikey.command()
    @click.option("--path", help="File to which the exported public key will be written. "
                  "The result will be written to the console if path is not specified")
    def export_pub_key(path):
        """
        Export the inserted Yubikey's public key and save it to the specified location.
        """
        developer_tool.export_yk_public_pem(path)

    @yubikey.command()
    @click.option("--certs-dir", help="Path of the directory where the exported certificate will be saved."
                  "Set to the user home directory by default")
    def setup_signing_key(certs_dir):
        """Generate a new key on the yubikey and set the pin. Export the generated certificate
        to the specified directory.
        WARNING - this will delete everything from the inserted key.
        """
        developer_tool.setup_signing_yubikey(certs_dir)

    @yubikey.command()
    @click.argument("key-path")
    def setup_test_key(key_path):
        """Copies the specified key onto the inserted YubiKey
        WARNING - this will reset the inserted key."""
        developer_tool.setup_test_yubikey(key_path)
