import json
from pathlib import Path
import shutil
from tuf.repository_tool import TARGETS_DIRECTORY_NAME


def copy_repositories_json(repositories_json_template, namespace, auth_repo_path):
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


def copy_mirrors_json(mirrors_json_path, namespace, auth_repo_path):
    output = auth_repo_path / TARGETS_DIRECTORY_NAME
    shutil.copy(str(mirrors_json_path), output)
