from typing import Dict
from taf.constants import TARGETS_DIRECTORY_NAME
from taf.git import GitRepository
import json
from pathlib import Path
import shutil


def read_json(path):
    return json.loads(Path(path).read_text())


def nested_git_repository(parent: Path, name: str = "nested") -> GitRepository:
    """Return a `GitRepository` for a new directory inside `parent`.

    The directory is not a repository. `discover_repository` walks upward, so
    anything read through pygit2 here answers from whatever encloses `parent`.
    """
    path = Path(parent) / name
    path.mkdir(parents=True)
    return GitRepository(path=path)


def copy_repositories_json(
    repositories_json_template: Dict, namespace: str, auth_repo_path: Path
):
    output = auth_repo_path / TARGETS_DIRECTORY_NAME

    repositories = {
        "repositories": {
            repo_name.format(namespace=namespace): repo_data
            for repo_name, repo_data in repositories_json_template[
                "repositories"
            ].items()
        }
    }
    output.mkdir(parents=True, exist_ok=True)
    Path(output / "repositories.json").write_text(json.dumps(repositories))


def copy_mirrors_json(mirrors_json_path: Path, auth_repo_path: Path):
    output = auth_repo_path / TARGETS_DIRECTORY_NAME
    shutil.copy(str(mirrors_json_path), output)
