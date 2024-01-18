# The Update Process

The purpose of the updater is to securely pull the authentication repository and specified target repositories and dependencies. Authentication repositories are git repositories which contain metadata files defined by TUF (The Update Framework). and target files required by the Open Law Collections framework. More details, take a look at the [specification document](./specification.md).

## Calling the updater

In a manner similar to Git, TAF updater differentiates between the clone and update commands. The clone command is intended for the initial downloading of repositories, while the update command is designed to pull in changes from an already cloned ones.

To invoke the updater, install the package and call the following command:

### Clone Command

Clone a specific authentication repository and its associated target repositories.

#### Usage

`taf repo clone https://github.com/organization/auth_repo.git [OPTIONS]`

#### Options

- `--path`: Authentication repository's location. If not specified, calculated by appending a name read from `targets/protected/info.json` file to `library-dir`.
- `--library-dir`: Directory where target repositories and, optionally, the authentication repository are located. If not specified, set to the current directory.
- `--expected-repo-type`: Indicates the expected authentication repository type (test, official, or either). Default is "either".
- `--scripts-root-dir`: Scripts root directory, which can be used to move scripts out of the authentication repository for testing purposes.
- `--profile`: Flag used to run a profiler and generate a `.prof` file.
- `--format-output`: Return formatted output including information on whether the build was successful and an error message if it was raised.
- `--exclude-target`: Globs defining which target repositories should be ignored during the update. Accepts multiple values.
- `--strict`: Enable/disable strict mode. In strict mode, an error is returned if warnings are raised. Default is disabled.
- `--from-fs`: Flag indicating and URL is a filesystem path`

`protected/info.json` needs to be in the following format:

  ```json
  {
      "namespace": "namespace",
      "name": "repo-name"
  }
```

### Update command

Update and validate the already cloned local authentication repository and its target repositories and dependencies. When
updating an existing authentication repository, the URL is automatically determined and does not need to be
specified (similarly to how `git pull` works)

#### Usage

`taf repo update [OPTIONS]`

#### Options

- `--path`: Authentication repository's location. If not specified, set to the current directory.
- `--library-dir`: Directory where target repositories and, optionally, the authentication repository are located. If not specified, calculated based on the authentication repository's path.
- `--expected-repo-type`: Indicates the expected authentication repository type (test, official, or either). Default is "either".
- `--scripts-root-dir`: Scripts root directory, which can be used to move scripts out of the authentication repository for testing purposes.
- `--profile`: Flag used to run a profiler and generate a `.prof` file.
- `--format-output`: Return formatted output including information on whether the build was successful and an error message if it was raised.
- `--exclude-target`: Globs defining which target repositories should be ignored during the update. Accepts multiple values.
- `--strict`: Enable/disable strict mode. In strict mode, an error is returned if warnings are raised. Default is disabled.

### Determining filesystem paths of repositories

If the authentication repository and the target repositories are in the same root directory, locations of the target repositories will correctly be calculated based on the authentication repository's
path with no further input. If the authentication repository's path is, say, `E:\\root\\namespace\\auth_repo`
the library root directory will be se to `E:\\root`. Names of all repositories are in the `namespace/repo-name` format.

If that is not the case, it is necessary to redefine this value using the `--library-dir` option.
Names of target repositories (as defined in `repositories.json`) are appended to the root
path (think of it as library root) thus defining the location of each target repository. If names of target repositories
are `namespace/repo1`, `namespace/repo2` etc. and the root directory is `E:\\root`, paths of the target
repositories will be calculated as `E:\\root\\namespace\\repo1`, `E:\\root\\namespace\\root2` etc.

### Dependencies

As described in the specification, one authentication repository can reference other authentication repositories.
This is defined using a special target file called `dependencies.json`. These repositories will be cloned inside
the same directory as the top authentication repository and its targets. So, if the top authentication repository's (which contains `dependecies.json`) path is `E:\\root\top-namespace\\auth_repo` and names of other repositories in `dependencies.json` are set as `namespace1\auth_repo` and `namespace2\auth_repo`, these authentication repositories will ne located at `E:\\root\namespace1\auth_repo` and `E:\\root\namespace2\auth_repo`.

### Hooks

Every authentication repository can contain target files inside `targets/scripts` folder which are expected to be Python scripts which will be executed after successful/failed update of that repository.

If a repository was successfully pulled and updated, `changed`, `succeeded` and
`completed` handlers will be called. If there were no new changes, `unchanged`,
`succeeded` and `completed` will be executed. If the update failed, `failed` and
`completed` handlers will be invoked. Scripts are linked to the mentioned events by being
put into a folder of the corresponding name in side `targets/scripts`. Each folder can
contain an arbitrary number of scripts and they will be called in alphabetical order.
Here is a sketch of the `scriprs` folder:

```bash
/scripts
    /repo
      /succeeded - every time a repo is successfully pulled
      /changed
      /unchanged
      /failed - every time a repo is not successfully pulled
      /completed  - like finally (called in both cases)
    /update
      /succeeded - once after all authentication's repositories have been successfully pulled
      /changed
      /unchanged
      /failed - if one repository failed
      /completed  - like finally (called in both cases)
```

Each script is expected to return a json containing persistent and transient data. Persistent data will automatically be saved to a file called `persistent.json` after every execution and passed to the next script, while the transient data will be passed to the next script without being stored anywhere. In addition to transient and persistent data, scripts receive information about repositories (both the auth repo and its target repositories), as well as about the update.

For more information about the data which is passed to the scripts, take a look at their [json schemas and the corresponding documentation](./schemas/descriptions.md).

### Scripts root dir

While writing the scripts, it is hard to expect that everything will work on the first try. Since scripts are target files, they
cannot be added to an authentication repository without being signed (meaning that the corresponding target files should be
updated and committed. To avoid having to go through that process while still in the development phase, a the scripts can be read any directory on the filesystem by passing the path to it
using the `--scripts-root-dir` option. This is only possible if development mode is turned on, which is currently the case. Further work will focus on making turning development mode on an off without having to modify the code.

Inside the scripts root directory, the framework expects to find the same directory structure:

```bash
scripts-root-dir
  - namespace
    - auth-repo-name
      - repo
          - changed
          - unchanged
        ...
```

### Script example

```python
import sys
import json


def process_stdin():
   return sys.stdin.read()

def do_something(data):
    transient = data["state"]["transient"]
    persistent = data["state"]["persistent"]
    transient.update({"script1": {"namespace/law": "this is transient"}})
    persistent.update({"script1": {"namespace/law": "this is persistent"}})
    return {
        "transient": transient,
        "persistent": persistent
    }

def send_state(state):
    # printed data will be sent from the script back to the updater
    print(json.dumps(do_something(data)))


if __name__ == '__main__':
    data = process_stdin()
    data = json.loads(data)
    state = do_something(data)
    send_state(state)
```
