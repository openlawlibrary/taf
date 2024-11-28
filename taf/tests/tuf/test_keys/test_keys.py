import pytest
from tuf.api.metadata import Metadata, Root
from taf.tuf.keys import load_public_key_from_file, load_signer_from_file

from securesystemslib.exceptions import UnverifiedSignatureError


def test_keys(tuf_repo, keystore_delegations):
    """
    Test loading public and private keys, and compatiblity with existing
    metadata:
    - newly loaded keys can verify old signatures on metadata
    - old keys in metadata can verify signatures from newly loaded signers

    """

    root = Metadata[Root].from_file(tuf_repo.metadata_path / "root.json")
    for name in [
        "root1",
        "root2",
        "root3",
        "snapshot",
        "targets1",
        "targets2",
        "timestamp",
    ]:
        public_key = load_public_key_from_file(keystore_delegations / f"{name}.pub")

        # assert hard-coded scheme and correct legacy keyid
        assert public_key.scheme == "rsa-pkcs1v15-sha256"
        assert public_key.keyid in root.signed.keys

        signer = load_signer_from_file(keystore_delegations / name, None)

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
