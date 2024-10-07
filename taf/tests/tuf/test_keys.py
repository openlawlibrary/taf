import pytest

from taf.tests.tuf import TEST_DATA_PATH
from taf.tuf.keys import load_public_key_from_file, load_signer_from_file
from tuf.api.metadata import Metadata, Root
from securesystemslib.exceptions import UnverifiedSignatureError


class TestKeys:
    def test_keys(self):
        """Smoke test for key functions.

        Test loading public and private keys, and compatiblity with existing
        metadata:
        - newly loaded keys can verify old signatures on metadata
        - old keys in metadata can verify signatures from newly loaded signers

        """
        root_path = (
            TEST_DATA_PATH
            / "repos"
            / "test-repository-tool"
            / "test-happy-path-pkcs1v15"
            / "taf"
            / "metadata"
            / "root.json"
        )

        root = Metadata[Root].from_file(root_path)
        store_path = TEST_DATA_PATH / "keystores" / "keystore"
        for name in ["root1", "root2", "root3", "snapshot", "targets", "timestamp"]:
            public_key = load_public_key_from_file(store_path / f"{name}.pub")

            # assert hard-coded scheme and correct legacy keyid
            assert public_key.scheme == "rsa-pkcs1v15-sha256"
            assert public_key.keyid in root.signed.keys

            signer = load_signer_from_file(store_path / name, None)

            # assert public key loaded from disk matches public key derived
            # from private key loaded from disk
            assert public_key == signer.public_key

            # assert existing keys verify new signatures
            sig = signer.sign(b"DATA")
            existing_key = root.signed.keys[public_key.keyid]
            existing_key.verify_signature(sig, b"DATA")
            with pytest.raises(UnverifiedSignatureError):
                existing_key.verify_signature(sig, b"NOT DATA")

            # assert newly loaded keys verify existing signatures
            if name.startswith("root"):  # there are only root sigs on root metadata
                existing_sig = root.signatures[public_key.keyid]
                public_key.verify_signature(existing_sig, root.signed_bytes)
                with pytest.raises(UnverifiedSignatureError):
                    existing_key.verify_signature(sig, b"NOT DATA")
