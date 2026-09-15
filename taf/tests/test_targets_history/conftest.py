"""Builders for target file contents in both formats."""

from typing import Any, Dict, List

from taf.tests.test_updater.test_target_validator.conftest import make_commits

TARGET_NAME = "namespace/repo"
MAIN = "main"
PUBLICATION = "publication/2026-01-15"


def make_entry(label: str = MAIN, branch: str = MAIN, **custom: Any) -> Dict[str, Any]:
    """A target file entry for a distinct commit. Keyword arguments become custom data."""
    return {"branch": branch, "commit": make_commits(label, 1)[0].value, **custom}


def make_history(count: int, branch: str = MAIN) -> List[Dict[str, Any]]:
    """A list of `count` entries for distinct commits on `branch`, oldest first."""
    return [
        {"branch": branch, "commit": commit.value, "build-date": "2026-01-15"}
        for commit in make_commits(branch, count)
    ]
