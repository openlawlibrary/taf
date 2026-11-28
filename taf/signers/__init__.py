"""Signers of a role's keys, and the places that hold the keys.

Each place that can hold keys, like keystore files, YubiKeys or an HSM, has its
own module with a key storage class. load_role_signers loads signers from the
storages in order of their priority, and a storage's setup_keys loads or
creates the keys of a new role. A new place to keep keys needs a new module
with a key storage class, which load_signers and setup_roles_keys then use.
"""
