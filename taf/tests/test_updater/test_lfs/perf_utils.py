"""Helpers for measuring what a Git LFS checkout costs.

Both measurements run the checkout in a fresh interpreter. Peak memory is a
process high-water mark, so it has to be read from a process that did nothing
else, and the spawn count needs an environment the parent does not share.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple

from taf.git import GitRepository

#: Prints its own peak RSS, so the parent measures a process that only checked
#: out. The watermark is reset first: Linux carries `ru_maxrss`/`VmHWM` across
#: fork and exec, so a child otherwise reports whatever its parent had peaked at.
CHECKOUT_SCRIPT = """
import sys
from pathlib import Path
from taf.git import GitRepository


def peak_rss_kb():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1])
    raise AssertionError("VmHWM missing from /proc/self/status")


Path("/proc/self/clear_refs").write_text("5")
client = GitRepository(path=sys.argv[1])
client.checkout_branch(sys.argv[2])
print("RSS:%d" % peak_rss_kb())
"""

#: Stands in for git-lfs on PATH, recording each execution before handing over.
SPAWN_COUNTER = """#!/bin/sh
echo x >> "$GIT_LFS_SPAWN_LOG"
exec "$GIT_LFS_REAL" "$@"
"""


def counting_git_lfs(directory: Path, real_git_lfs: str, log: Path) -> dict:
    """Environment whose ``git-lfs`` records every execution in ``log``."""
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / "git-lfs"
    shim.write_text(SPAWN_COUNTER)
    shim.chmod(0o755)
    log.write_text("")
    return {
        **os.environ,
        "PATH": f"{directory}{os.pathsep}{os.environ['PATH']}",
        "GIT_LFS_REAL": real_git_lfs,
        "GIT_LFS_SPAWN_LOG": str(log),
    }


def measure_checkout(client: GitRepository, branch: str, env: dict) -> Tuple[int, str]:
    """Check ``branch`` out in a fresh interpreter; return (peak RSS in KB, output)."""
    result = subprocess.run(
        [sys.executable, "-c", CHECKOUT_SCRIPT, str(client.path), branch],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"checkout failed: {result.stderr[-2000:]}"
    rss = [
        int(line.split(":", 1)[1])
        for line in result.stdout.splitlines()
        if line.startswith("RSS:")
    ]
    assert rss, f"the checkout reported no RSS: {result.stdout} {result.stderr[-500:]}"
    return rss[0], result.stdout
