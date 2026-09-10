"""
Minimal git hosting provider API, used to change a remote repository's
default branch after a new declared (e.g. publication) branch is merged.
Uses `urllib` rather than `requests` to avoid adding a dependency.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

from taf.exceptions import TAFError

GIT_URL_RE = re.compile(
    r"(git|ssh|http(s)?)(@|:\/\/)?(?P<provider_owner_repo>[\w\.\:\/\-~]+)(\.git)(\/)?$"
)


class GitProviderError(TAFError):
    pass


def _extract_provider_owner_repo(git_remote_url: str):
    """
    Extract provider name, owner name and repository name from a remote
    origin URL, e.g.:
        https://github.com/some-org/some-repo.git
        git@github.com:some-org/some-repo.git
    """
    git_remote_url = (
        git_remote_url if git_remote_url.endswith(".git") else f"{git_remote_url}.git"
    )

    match = GIT_URL_RE.match(git_remote_url)
    if match is None:
        raise ValueError(
            f"Git repository at {git_remote_url} does not have a valid remote origin url!"
        )

    provider, owner, repo_name = (
        match.group("provider_owner_repo").replace(":", "/").split("/")
    )
    if provider is None or owner is None or repo_name is None:
        raise ValueError(
            "Cannot extract provider, owner and repo information from remote "
            f"origin url: {git_remote_url}"
        )

    return provider, owner, repo_name


class GitProvider:
    """Base class representing a git hosting provider."""

    API_BASE_URL: Optional[str] = None

    def __init__(self, owner: str, repo_name: str, access_token: Optional[str] = None):
        self.owner = owner
        self.name = repo_name
        self.access_token = access_token

    def set_default_branch(self, branch_name: str) -> None:
        raise NotImplementedError


class GitHubProvider(GitProvider):
    """Talks to the GitHub REST API."""

    API_BASE_URL = "https://api.github.com"

    def set_default_branch(self, branch_name: str) -> None:
        url = f"{self.API_BASE_URL}/repos/{self.owner}/{self.name}"
        data = json.dumps({"default_branch": branch_name}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="PATCH",
            headers={
                "Authorization": f"token {self.access_token}",
                "Content-Type": "application/json",
                "Accept": "application/vnd.github+json",
            },
        )
        try:
            with urllib.request.urlopen(request) as response:  # nosec B310
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            err_msg = os.linesep.join(
                err.get("message", "") for err in body.get("errors", [])
            )
            if not err_msg:
                err_msg = body.get("message", "")
            raise GitProviderError(err_msg)

        if body.get("default_branch", "") != branch_name:
            raise GitProviderError(
                f"Could not set default branch of {self.owner}/{self.name} to {branch_name}"
            )


def get_git_provider(repo, access_token: Optional[str] = None) -> GitProvider:
    """Return a `GitProvider` for `repo`, based on its remote origin URL."""
    provider_name, owner_name, repo_name = _extract_provider_owner_repo(
        repo.get_remote_url()
    )
    provider_class = {"github.com": GitHubProvider}.get(provider_name, GitProvider)
    return provider_class(owner_name, repo_name, access_token)
