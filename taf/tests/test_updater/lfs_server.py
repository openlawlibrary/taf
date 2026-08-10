"""A minimal Git LFS server for tests, speaking the real Batch API over HTTP.

This is not a mock: it is a real server implementing the documented Git LFS
protocol (``POST /objects/batch`` plus ``basic`` transfer GET/PUT), which the
real ``git-lfs`` client talks to over a real socket. Nothing in TAF is stubbed.

Why a server is needed at all: git-lfs looks for objects at the endpoint it
resolves for the repository - ``lfs.url`` (typically from a committed
``.lfsconfig``), else derived from the git remote. TAF materializes a client's
target repository from an intermediate *bare* clone, and bare clones carry no
LFS objects, so whether a clone succeeds depends entirely on whether some
endpoint other than that intermediate repo can supply the objects. Only a
server reproduces the deployed topology (GitHub/GitLab hosting the objects).

Storage is a flat directory keyed by oid. ``downloads``/``uploads`` record what
the client actually asked for, so a test can assert the bytes genuinely came
over the wire rather than from a local hardlink.

Protocol reference: https://github.com/git-lfs/git-lfs/blob/main/docs/api/batch.md
"""

import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional

LFS_CONTENT_TYPE = "application/vnd.git-lfs+json"


class _LFSRequestHandler(BaseHTTPRequestHandler):
    """Handles the two endpoints the ``basic`` transfer adapter needs."""

    # the server instance sets this; avoids globals
    lfs_server: "LFSServer"

    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 - signature is fixed
        """Silence the default stderr access log; tests capture what they need."""

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", LFS_CONTENT_TYPE)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if not self.path.rstrip("/").endswith("/objects/batch"):
            self.send_error(404)
            return

        request = json.loads(self._read_body() or b"{}")
        operation = request.get("operation")
        server = self.lfs_server
        objects: List[Dict] = []

        for requested in request.get("objects", []):
            oid = requested.get("oid", "")
            size = requested.get("size", 0)
            entry: Dict = {"oid": oid, "size": size, "authenticated": True}
            href = f"{server.url}/storage/{oid}"

            if operation == "upload":
                entry["actions"] = {"upload": {"href": href}}
            elif server.has_object(oid):
                entry["actions"] = {"download": {"href": href}}
            else:
                # the protocol's way of saying "this object is not here"
                entry["error"] = {"code": 404, "message": f"object {oid} not found"}
            objects.append(entry)

        self._send_json(200, {"transfer": "basic", "objects": objects})

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        oid = self._oid_from_storage_path()
        if oid is None:
            self.send_error(404)
            return
        server = self.lfs_server
        if not server.has_object(oid):
            self.send_error(404)
            return

        data = server.read_object(oid)
        server.record_download(oid)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        oid = self._oid_from_storage_path()
        if oid is None:
            self.send_error(404)
            return
        self.lfs_server.write_object(oid, self._read_body())
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _oid_from_storage_path(self) -> Optional[str]:
        prefix = "/storage/"
        if prefix not in self.path:
            return None
        oid = self.path.rsplit(prefix, 1)[1].strip("/")
        # oids are hex sha256; refuse anything else so a path can never escape
        if len(oid) != 64 or not all(c in "0123456789abcdef" for c in oid):
            return None
        return oid


class LFSServer:
    """A Git LFS endpoint on 127.0.0.1, backed by a directory of objects."""

    def __init__(self, storage: Path):
        self.storage = Path(storage)
        self.storage.mkdir(parents=True, exist_ok=True)
        self.downloads: List[str] = []
        self.uploads: List[str] = []
        self._lock = threading.Lock()
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._port: Optional[int] = None

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> "LFSServer":
        handler = type(
            "_BoundLFSRequestHandler", (_LFSRequestHandler,), {"lfs_server": self}
        )
        # port 0 -> the OS picks a free port, so parallel runs cannot collide
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    def __enter__(self) -> "LFSServer":
        return self.start()

    def __exit__(self, *exc_info) -> None:
        self.stop()

    @property
    def url(self) -> str:
        if self._port is None:
            raise RuntimeError("LFS server is not running")
        return f"http://127.0.0.1:{self._port}"

    # --- object store -----------------------------------------------------
    def _path_for(self, oid: str) -> Path:
        return self.storage / oid

    def has_object(self, oid: str) -> bool:
        return self._path_for(oid).is_file()

    def read_object(self, oid: str) -> bytes:
        return self._path_for(oid).read_bytes()

    def write_object(self, oid: str, data: bytes) -> None:
        self._path_for(oid).write_bytes(data)
        with self._lock:
            self.uploads.append(oid)

    def record_download(self, oid: str) -> None:
        with self._lock:
            self.downloads.append(oid)

    def reset_counters(self) -> None:
        with self._lock:
            self.downloads.clear()
            self.uploads.clear()

    # --- test helpers -----------------------------------------------------
    def seed_from_repo(self, repo_path: Path) -> List[str]:
        """Publish every LFS object in ``repo_path`` to this server.

        Returns the oids published. Mirrors what ``git lfs push`` would have
        done, without needing a push remote configured on a test origin.
        """
        published = []
        objects_dir = Path(repo_path) / ".git" / "lfs" / "objects"
        for path in objects_dir.rglob("*"):
            if path.is_file():
                shutil.copyfile(path, self._path_for(path.name))
                published.append(path.name)
        return published

    def take_local_objects(self, repo_path: Path) -> List[str]:
        """Publish objects to the server, then delete the repo's local copies.

        Leaves the server as the *only* source, so a successful checkout in a
        clone is proof that the object travelled over HTTP.
        """
        published = self.seed_from_repo(repo_path)
        objects_dir = Path(repo_path) / ".git" / "lfs" / "objects"
        if objects_dir.is_dir():
            shutil.rmtree(objects_dir)
        return published
