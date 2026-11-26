# Manual signing tests

Checks for signing with YubiKeys and keystore files that the automated tests don't cover. They need two YubiKeys with free PIV slots, called YK-A and YK-B, and taf installed with the `yubikey` extra.

Key types each YubiKey can hold:

| | YubiKey 4 | YubiKey 5 before 5.7 | YubiKey 5.7 or later |
|---|---|---|---|
| RSA 2048, ECDSA P-256, ECDSA P-384 | yes | yes | yes |
| RSA 3072 and 4096, Ed25519 | no | no | yes |

## Setup

```bash
source <taf venv>/bin/activate
mkdir -p ~/taf-signing-tests && cd ~/taf-signing-tests
```

All paths below are relative to this directory.

- Repositories are created with `--test`.
- When `taf keystore generate` asks whether to create the keystore directory, answer y.
- "Could not push changes. No remotes configured" after a command is expected.
- Keys go into the SIGNATURE, AUTHENTICATION and KEY_MANAGEMENT slots. CARD_AUTH is meant for use without a PIN and is not used here.
- taf never overwrites an occupied PIV slot. `ykman --device <serial> piv reset` frees all slots of a YubiKey and removes its keys. The PIN is then `123456`.
- To not type the PIN of a YubiKey in every command, set `PIN_<serial>`, for example `export PIN_12345678=123456`. Leave it unset in the steps that test PIN prompts.

To see which keys signed a role, compare with `taf roles list-keys`:

```bash
jq -r '.signatures[].keyid' test-ns/auth/metadata/root.json
```

## A. Main path: root and targets on YubiKeys, snapshot and timestamp in a keystore

The keys are generated in a keystore and copied onto the YubiKeys, so the setup can be repeated with the same keys.

| role | keys | threshold | scheme | where |
|---|---|---|---|---|
| root | 2 | 2 | rsa-pkcs1v15-sha256, 2048 bits | SIGNATURE of YK-A and of YK-B |
| targets | 2 | 1 | ecdsa-sha2-nistp256 | AUTHENTICATION of YK-A and of YK-B |
| maintainer, delegated by targets | 1 | 1 | rsassa-pss-sha256, 2048 bits | KEY_MANAGEMENT of YK-A |
| snapshot | 1 | 1 | ecdsa-sha2-nistp384 | keystore |
| timestamp | 1 | 1 | ed25519 | keystore |

### A1. Devices and PIN

```bash
taf yubikey list-key
taf yubikey list-slots
taf yubikey check-pin --serial <serial> --pin 000000
taf yubikey check-pin --serial <serial> --pin 123456
```

Expected:

- Both YubiKeys are listed with their firmware version.
- The wrong PIN gives "Invalid PIN. You have 2 retries left".
- The right PIN gives "PIN is valid" and resets the retries.

### A2. Generate the keys and copy them onto the YubiKeys

```bash
cat > keys-description.json <<'EOF'
{
  "roles": {
    "root": {"number": 2, "threshold": 2, "scheme": "rsa-pkcs1v15-sha256", "length": 2048},
    "targets": {
      "number": 2, "threshold": 1, "scheme": "ecdsa-sha2-nistp256",
      "delegations": {
        "maintainer": {"paths": ["test-ns/target2"], "scheme": "rsassa-pss-sha256", "length": 2048}
      }
    },
    "snapshot": {"scheme": "ecdsa-sha2-nistp384"},
    "timestamp": {"scheme": "ed25519"}
  }
}
EOF
taf keystore generate --keystore yk-keys --keys-description keys-description.json
mkdir -p keystore && mv yk-keys/snapshot* yk-keys/timestamp* keystore/
```

`keystore` now holds only snapshot and timestamp. Copy the other keys, with one YubiKey inserted at a time:

```bash
# YK-A
taf yubikey setup-test-key yk-keys/root1 --slot SIGNATURE
taf yubikey setup-test-key yk-keys/targets1 --slot AUTHENTICATION
taf yubikey setup-test-key yk-keys/maintainer --slot KEY_MANAGEMENT
# YK-B
taf yubikey setup-test-key yk-keys/root2 --slot SIGNATURE
taf yubikey setup-test-key yk-keys/targets2 --slot AUTHENTICATION
taf yubikey list-slots
```

Expected: each key is in its slot, and KEY_MANAGEMENT of YK-B is still free.

### A3. Create the repository with target repositories

The target repositories have to be next to the authentication repository, in the same namespace directory, so that taf finds them.

```bash
mkdir -p test-ns
for r in target1 target2; do
  git init -q test-ns/$r
  echo "$r $(date +%s%N)" > test-ns/$r/file-$RANDOM.txt
  git -C test-ns/$r add . && git -C test-ns/$r commit -q -m "Add a file"
done
mkdir -p keystore-create && cp yk-keys/* keystore/* keystore-create/
taf repo create test-ns/auth --keys-description keys-description.json --keystore keystore-create --test
```

The repository is created from keystore copies of the keys on the YubiKeys, without prompts. From now on only `keystore` is used, so root, targets and maintainer can only be signed with the YubiKeys.

```bash
taf targets add-repo test-ns/target1 --path test-ns/auth --keystore keystore --no-remote-check
taf targets add-repo test-ns/target2 --path test-ns/auth --keystore keystore --no-remote-check
taf targets update-and-sign --path test-ns/auth --keystore keystore
taf targets list --path test-ns/auth
```

Expected:

- `add-repo` adds the repository to `repositories.json`, signed by targets with a YubiKey.
- `update-and-sign` writes the target files `test-ns/auth/targets/test-ns/target1` and `target2` with the repositories' commits and branches. target1 is signed by targets, target2 by maintainer.
- `targets list` shows target1 and target2. A repository that is in `repositories.json` but has no target file yet is not listed, and one that is missing on disk is skipped.

### A4. Keys and roles

```bash
taf roles list-keys --path test-ns/auth
taf roles list-keys targets --path test-ns/auth
taf yubikey get-roles --path test-ns/auth
```

Expected:

- `list-keys` lists each key once, ordered by key id, with the roles that use it.
- `get-roles` with YK-A inserted: root, targets and maintainer with path `test-ns/target2`. With YK-B: root and targets.

### A5. Update root, threshold 2

```bash
taf metadata update-expiration-dates --path test-ns/auth --keystore keystore --role root
jq -r '.signatures[].keyid' test-ns/auth/metadata/root.json
```

Run it three times:

- **Both YubiKeys inserted before the command:** only the PINs are asked. root has both key ids.
- **No YubiKey inserted:** answer y to "Sign root using YubiKey(s)?" and insert YK-A, then YK-B, when asked. root has both key ids.
- **Only YK-A inserted, then decline to insert another:** "Cannot load keys of role root", and nothing changes.

snapshot and timestamp are signed from the keystore each time, without prompts.

### A6. Update targets, threshold 1, loading more keys

```bash
taf metadata update-expiration-dates --path test-ns/auth --keystore keystore --role targets
jq -r '.signatures[].keyid' test-ns/auth/metadata/targets.json
```

Run it twice, inserting YK-A when asked:

- **Answer y to "Threshold of targets keys reached. Do you want to load more targets keys?"** and insert YK-B. targets has both key ids.
- **Answer n.** targets has one key id.

### A7. Update snapshot and timestamp

```bash
taf metadata update-expiration-dates --path test-ns/auth --keystore keystore --role snapshot --role timestamp
```

Expected: signed from the keystore, no YubiKey prompts.

### A8. New commits in the target repositories

```bash
for r in target1 target2; do
  echo "$r $(date +%s%N)" > test-ns/$r/file-$RANDOM.txt
  git -C test-ns/$r add . && git -C test-ns/$r commit -q -m "Add a file"
done
taf targets update-and-sign --path test-ns/auth --keystore keystore
git -C test-ns/auth show --stat HEAD
jq -r '.signatures[].keyid' test-ns/auth/metadata/maintainer.json
```

Insert YK-A. One command signs targets with the AUTHENTICATION key and maintainer with the KEY_MANAGEMENT key of the same YubiKey.

Expected: both target files have the new commits, and the commit changes `targets.json`, `maintainer.json`, `snapshot.json` and `timestamp.json`.

### A9. Add a delegated role, reusing a YubiKey key

```bash
git init -q test-ns/target3
echo "target3 $(date +%s%N)" > test-ns/target3/file-$RANDOM.txt
git -C test-ns/target3 add . && git -C test-ns/target3 commit -q -m "Add a file"
echo '{"roles": {"delegated_role": {"parent_role": "targets", "paths": ["test-ns/target3"], "yubikey": true, "scheme": "ecdsa-sha2-nistp256"}}}' > delegated-role.json
taf roles add --path test-ns/auth --keystore keystore --config-file delegated-role.json
```

taf asks about the key as `delegated_role1`. Insert YK-A and answer y to "reuse already set up Yubikey?".

Expected:

- Only the keys that fit the role's scheme are offered, here the P-256 key in AUTHENTICATION, not the RSA keys.
- delegated_role is added, signed by targets, and the key's certificate is written to `test-ns/auth/certs`.

```bash
taf targets add-repo test-ns/target3 --path test-ns/auth --keystore keystore --no-remote-check
taf targets update-and-sign --path test-ns/auth --keystore keystore
jq -r '.signatures[].keyid' test-ns/auth/metadata/delegated_role.json
```

Expected: target3's target file is signed by delegated_role.

### A10. Add a key to targets, then rotate it

Changing targets' keys changes root, so both YubiKeys are needed.

```bash
taf yubikey setup-signing-key --scheme ecdsa-sha2-nistp384 --slot KEY_MANAGEMENT    # YK-B
taf yubikey export-pub-key --slot KEY_MANAGEMENT --output yk-b-km.pub              # YK-B
taf roles add-signing-key --path test-ns/auth --keystore keystore --role targets --pub-key-path yk-b-km.pub
taf yubikey export-pub-key --slot KEY_MANAGEMENT --output maintainer.pub           # YK-A
taf roles rotate-key <keyid of yk-b-km.pub> --path test-ns/auth --keystore keystore --role targets --pub-key-path maintainer.pub
taf roles rotate-key <keyid of yk-b-km.pub> --path test-ns/auth --keystore keystore --role targets --pub-key-path maintainer.pub --scheme rsassa-pss-sha256
taf roles list-keys targets --path test-ns/auth
```

Expected:

- `add-signing-key` adds the P-384 key without `--scheme`, and root is signed by both YubiKeys.
- The first `rotate-key` stops with "An RSA key can be used with several signing schemes ... pass --scheme".
- The second one revokes the P-384 key and adds the maintainer key to targets, in two commits.

### A11. YubiKeys with all signing slots used

Both YubiKeys now hold keys in SIGNATURE, AUTHENTICATION and KEY_MANAGEMENT.

```bash
taf yubikey list-slots
taf yubikey setup-signing-key --scheme ecdsa-sha2-nistp256
for r in target1 target2 target3; do
  echo "$r $(date +%s%N)" > test-ns/$r/file-$RANDOM.txt
  git -C test-ns/$r add . && git -C test-ns/$r commit -q -m "Add a file"
done
taf targets update-and-sign --path test-ns/auth --keystore keystore
```

Expected:

- `setup-signing-key` fails with "The SIGNATURE slot on YubiKey ... already has a key".
- With both YubiKeys inserted, targets, maintainer and delegated_role are each signed with the keys from their own slots.

### A12. Both keys of a role on one YubiKey

When only one YubiKey is at hand. Use a spare YubiKey, or reset one and copy its keys back from `yk-keys` afterwards. Copy both targets keys into two slots and sign:

```bash
taf yubikey setup-test-key yk-keys/targets1 --slot SIGNATURE
taf yubikey setup-test-key yk-keys/targets2 --slot AUTHENTICATION
taf metadata update-expiration-dates --path test-ns/auth --keystore keystore --role targets
jq -r '.signatures[].keyid' test-ns/auth/metadata/targets.json
```

Expected: the PIN is asked once, both keys are loaded from the one YubiKey, and targets has both key ids. "Do you want to load more targets keys?" is not asked, since both keys come from the same device.

With delegated_role using one of these keys (A9), a commit in target1 and one in target3 are signed in one `update-and-sign`: targets with both slots, delegated_role with its slot.

During `repo create` and `roles add`, taf takes only one key per role from each YubiKey. Two keys of a role on one YubiKey have to be copied there, as here.

### A13. YubiKey public keys in the keys description

When maintainers send their public keys instead of setting up keys during `repo create`.

```bash
taf yubikey export-pub-key --slot AUTHENTICATION --output yk-a-targets.pub    # YK-A
jq -n --rawfile pem yk-a-targets.pub '{
  yubikeys: {yk_a: {public: $pem, scheme: "ecdsa-sha2-nistp256"}},
  roles: {
    root: {scheme: "ecdsa-sha2-nistp256"},
    targets: {yubikeys: ["yk_a"], scheme: "ecdsa-sha2-nistp256"},
    snapshot: {scheme: "ecdsa-sha2-nistp384"},
    timestamp: {scheme: "ecdsa-sha2-nistp384"}
  }
}' > keys-description-public.json
echo '{"roles": {"root": {"scheme": "ecdsa-sha2-nistp256"}, "targets": {"scheme": "ecdsa-sha2-nistp256"}, "snapshot": {"scheme": "ecdsa-sha2-nistp384"}, "timestamp": {"scheme": "ecdsa-sha2-nistp384"}}}' > keys-description-root-keystore.json
taf keystore generate --keystore keystore-public --keys-description keys-description-root-keystore.json
taf repo create test-ns/auth-public --keys-description keys-description-public.json --keystore keystore-public --test
```

Here root is in `keystore-public` so that only targets uses a YubiKey.

Expected: "Sign using yk_a Yubikey?". Answer y, insert YK-A, and the repository is created with that key in targets.

Without `"scheme"` for an RSA YubiKey key in the `yubikeys` section, `repo create` stops with a message to set it.

## B. YubiKey key types and slots

Insert one YubiKey at a time.

```bash
taf yubikey setup-signing-key --scheme rsa-pkcs1v15-sha256 --key-size 2048 --slot <free slot>
taf yubikey setup-signing-key --scheme rsa-pkcs1v15-sha256 --slot <free slot>    # 3072 bits by default
taf yubikey setup-signing-key --scheme ecdsa-sha2-nistp384 --slot <free slot>
taf yubikey setup-signing-key --scheme ed25519 --slot <free slot>
taf yubikey setup-signing-key --scheme ecdsa-sha2-nistp256 --slot <occupied slot>
taf yubikey list-slots
```

Expected:

- Keys the YubiKey can hold (see the table above) are set up in the given slot.
- The others fail with "cannot hold this key ... Use a 2048-bit RSA key", and nothing is written to the slot.
- The occupied slot is refused, on YubiKey 4 too, which has no slot metadata.

Copying a key the YubiKey can't hold fails the same way. On firmware older than 5.7:

```bash
taf yubikey setup-test-key keystore/timestamp --slot <free slot>    # Ed25519
```

Expected: "cannot hold this key: ED25519 requires YubiKey 5.7 or later", and the slot stays free.

Export:

```bash
taf yubikey export-pub-key --slot <slot of an RSA key>
taf yubikey export-pub-key --slot <slot of an RSA key> --scheme rsa-pkcs1v15-sha256
taf yubikey export-pub-key --slot <slot of an ECDSA key>
taf yubikey export-certificate --slot <slot of an ECDSA key> --output cert
```

Expected:

- RSA key without `--scheme`: serial and PEM, no key id.
- RSA key with `--scheme`: also the key id.
- ECDSA key: key id without `--scheme`.
- Empty slot: "Failed to export public key: APDU error: SW=0x6a82 (FILE_NOT_FOUND)".

During `repo create` or `roles add`, when reusing a YubiKey that also holds keys of another type, only the keys that fit the role's scheme are offered.

## C. Keystore files only

### C1. Keys description without schemes is refused

```bash
echo '{"roles": {"root": {}, "targets": {}, "snapshot": {}, "timestamp": {}}}' > keys-description-noscheme.json
taf keystore generate --keystore keystore-noscheme --keys-description keys-description-noscheme.json
```

Expected: "A signing scheme is needed to generate a key", no key files written.

### C2. Generate keys of every type

```bash
cat > keys-description-keystore.json <<'EOF'
{
  "roles": {
    "root": {"number": 3, "threshold": 2, "scheme": "ed25519"},
    "targets": {
      "scheme": "ecdsa-sha2-nistp256",
      "delegations": {
        "delegated_role": {"paths": ["dir1/*"], "number": 2, "threshold": 2,
                           "scheme": "rsassa-pss-sha256", "length": 2048}
      }
    },
    "snapshot": {"scheme": "ml-dsa-65/1"},
    "timestamp": {"scheme": "rsa-pkcs1v15-sha256"}
  }
}
EOF
taf keystore generate --keystore keystore-all --keys-description keys-description-keystore.json
ls -l keystore-all
sha256sum keystore-all/* > keystore-all.sha256
taf keystore generate --keystore keystore-all --keys-description keys-description-keystore.json   # answer n
sha256sum -c keystore-all.sha256
```

Expected:

- `root1-3`, `targets`, `delegated_role1-2`, `snapshot`, `timestamp`, each with a `.pub` file.
- Private key files are `-rw-------`.
- The second run asks "... already exists. Overwrite it?" for each file. After answering n, all checksums match.

### C3. Create a repository and sign with every key type

```bash
taf repo create auth-keystore --keys-description keys-description-keystore.json --keystore keystore-all --test
taf metadata update-expiration-dates --path auth-keystore --keystore keystore-all --role root
mkdir -p auth-keystore/targets/dir1
echo a > auth-keystore/targets/dir1/a.txt
echo b > auth-keystore/targets/b.txt
taf targets sign --path auth-keystore --keystore keystore-all
```

Expected: no prompts. root is signed with Ed25519, delegated_role with both RSA-PSS keys, targets with ECDSA, snapshot with ML-DSA and timestamp with RSA.

### C4. A keystore file that can't be read is skipped

```bash
chmod 000 keystore-all/root1
taf metadata update-expiration-dates --path auth-keystore --keystore keystore-all --role root
chmod 600 keystore-all/root1
```

Expected: warning "Could not open keystore file file2:.../root1: ... Permission denied". root is still signed with root2 and root3.

### C5. Adding a key: RSA needs `--scheme`, other types don't

```bash
echo '{"roles": {"root": {"scheme": "rsa-pkcs1v15-sha256", "length": 2048}, "targets": {"scheme": "ecdsa-sha2-nistp256"}, "snapshot": {"scheme": "ed25519"}, "timestamp": {"scheme": "ed25519"}}}' > keys-description-extra.json
taf keystore generate --keystore keystore-extra --keys-description keys-description-extra.json
taf roles add-signing-key --path auth-keystore --keystore keystore-all --role targets --pub-key-path keystore-extra/root.pub
taf roles add-signing-key --path auth-keystore --keystore keystore-all --role targets --pub-key-path keystore-extra/root.pub --scheme rsa-pkcs1v15-sha256
taf roles add-signing-key --path auth-keystore --keystore keystore-all --role targets --pub-key-path keystore-extra/targets.pub
taf roles add-signing-key --path auth-keystore --keystore keystore-all --role targets
```

Expected:

1. Stops with "An RSA key can be used with several signing schemes ... pass --scheme".
2. Adds the RSA key.
3. Adds the ECDSA key without `--scheme`.
4. "Public key not provided or invalid".

### C6. New role, key generated

```bash
echo '{"roles": {"new_role": {"parent_role": "targets", "paths": ["dir2/*"], "scheme": "ecdsa-sha2-nistp384"}}}' > new-role.json
taf roles add --path auth-keystore --keystore keystore-all --config-file new-role.json
ls -l keystore-all/new_role*
```

Expected: `new_role` (`-rw-------`) and `new_role.pub` are created, and the role is in metadata.

### C7. A keystore file that can't be loaded is not replaced

```bash
echo garbage > keystore-all/bad_role
cp keystore-all/root1 keystore-all/mismatch_role
echo '{"roles": {"bad_role": {"paths": ["dir3/*"], "scheme": "ecdsa-sha2-nistp256"}}}' > bad-role.json
echo '{"roles": {"mismatch_role": {"paths": ["dir4/*"], "scheme": "rsa-pkcs1v15-sha256"}}}' > mismatch-role.json
taf roles add --path auth-keystore --keystore keystore-all --config-file bad-role.json
cat keystore-all/bad_role
taf roles add --path auth-keystore --keystore keystore-all --config-file mismatch-role.json
cmp keystore-all/root1 keystore-all/mismatch_role && echo unchanged
```

Expected:

- Both fail with "Could not open keystore file ...: <reason>. The file is not replaced with a new key".
- `bad_role` still contains `garbage`, and `mismatch_role` is unchanged.
- Neither role is added.

### C8. `targets add-repo` uses the role's scheme from `--config-file`

```bash
git init -q namespace/target1 && git -C namespace/target1 commit -q --allow-empty -m init
echo '{"role": {"parent_role": "targets", "keys_number": 1, "scheme": "ed25519"}}' > add-repo.json
taf targets add-repo namespace/target1 --path auth-keystore --keystore keystore-all --role target_role --config-file add-repo.json --no-remote-check
```

Expected: `target_role` is created with an Ed25519 key, generated after "Generate new keys?".

### C9. Keystore path with `#` is refused

```bash
cp -r keystore-all 'key#store'
taf metadata update-expiration-dates --path auth-keystore --keystore 'key#store' --role timestamp
```

Expected: "Keystore path ... can't contain '#' or '?'".

## D. Repositories created with an older taf version

Use a repository whose keys description has no schemes and whose YubiKeys hold RSA keys.

```bash
taf metadata update-expiration-dates --path <repo> --keystore <keystore> --role timestamp --no-commit
taf targets sign --path <repo> --keystore <keystore> --no-commit
git -C <repo> status --short
```

Expected: keystore and YubiKey keys load with their scheme taken from metadata, with no "scheme needed" error.

Undo the changes:

```bash
git -C <repo> checkout -- . && git -C <repo> clean -fd
```

## Clean-up

```bash
rm -rf ~/taf-signing-tests
```
