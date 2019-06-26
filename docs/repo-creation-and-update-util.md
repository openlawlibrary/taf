# Authentication repository creation and update utility

TAF provides a number of commands for creating and updating the authentication repositories.
Some of them focus on creation and initial setup of the repositories, while the others
provide an easy way of updating information about target repositories.

At the moment, creation of repositories does not support using YubiKeys. However,
if a key used to sign the metadata files is imported to a YubiKey, that YubiKey can
later be used for signing. Since keystore files might be password protected and since
certain information about the keys must be provided when creating an authentication repository,
many of the commands have an option called `keys-description`. This parameter is expected
to contain a json, like the following one:

```
{
  "root": {
    "number": 3,
    "length": 2048,
    "passwords": ["password1", "password2", "password3"]
	  "threshold": 2
  },
  "targets": {
    "length": 2048
  },
  "snapshot": {},
  "timestamp": {}
}
```

So, for each metadata role (root, targets, snaphost, timestamp) there is a description of its keys.
Configurable properties include the following:
- `number` - total number of the role's keys
- `length` - length of the role's keys. Only needed when this json is used to generate keys.
- `passwords` - a list of the passwords of the keystore files corresponding to the current role. The first
                entry in the list is expected to specify the first key's password.
- `threshold` - role's keys threshold

Names of keys must follow a certain naming convention, that is that their names are composed of role's name
and a counter (if there is more than one key). E.g. `root1`', `root2`, `targets1`, `targets2`, `snapshot` etc.


