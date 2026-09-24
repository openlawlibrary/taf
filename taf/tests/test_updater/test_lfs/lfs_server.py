"""A minimal Git LFS server for tests, speaking the real Batch API over HTTP.

Implements the two endpoints the ``basic`` transfer adapter needs -
``POST /objects/batch`` plus GET/PUT of the object itself - so the real
``git-lfs`` client talks to it over a real socket.

A server is what reproduces the deployed topology, where the objects live on
GitHub or GitLab rather than in any repository TAF can reach: TAF materializes a
client's target repository from an intermediate bare clone, and bare clones carry
no LFS objects.

Storage is a flat directory keyed by oid. ``downloads`` records what the client
asked for, so a test can assert the bytes came over the wire rather than from a
local hardlink.

Protocol reference: https://github.com/git-lfs/git-lfs/blob/main/docs/api/batch.md
"""

import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional

LFS_CONTENT_TYPE = "application/vnd.git-lfs+json"


class LFSServer:
    """A Git LFS endpoint on 127.0.0.1, backed by a directory of objects."""

    def __init__(self, storage: Path):
        self.storage = Path(storage)
        self.storage.mkdir(parents=True, exist_ok=True)
        self.downloads: List[str] = []
        self.requests: List[str] = []
        self._lock = threading.Lock()
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._port: Optional[int] = None

    def __enter__(self) -> "LFSServer":
        return self.start()

    def __exit__(self, *exc_info) -> None:
        self.stop()

    def has_object(self, oid: str) -> bool:
        return self._path_for(oid).is_file()

    def read_object(self, oid: str) -> bytes:
        return self._path_for(oid).read_bytes()

    def record_download(self, oid: str) -> None:
        with self._lock:
            self.downloads.append(oid)

    def record_request(self, oid: str) -> None:
        """Note that a client asked the Batch API where ``oid`` can be had."""
        with self._lock:
            self.requests.append(oid)

    def reset_counters(self) -> None:
        with self._lock:
            self.downloads.clear()
            self.requests.clear()

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

    def take_local_objects(self, repo_path: Path) -> List[str]:
        """Publish ``repo_path``'s LFS objects here, then delete its local copies.

        Leaves the server as the only source, so a successful checkout in a
        clone is proof that the object travelled over HTTP.
        """
        objects_dir = Path(repo_path) / ".git" / "lfs" / "objects"
        published = []
        for path in objects_dir.rglob("*"):
            if path.is_file():
                shutil.copyfile(path, self._path_for(path.name))
                published.append(path.name)
        if objects_dir.is_dir():
            shutil.rmtree(objects_dir)
        return published

    @property
    def url(self) -> str:
        if self._port is None:
            raise RuntimeError("LFS server is not running")
        return f"http://127.0.0.1:{self._port}"

    def _path_for(self, oid: str) -> Path:
        return self.storage / oid


class _LFSRequestHandler(BaseHTTPRequestHandler):
    """Handles the two endpoints the ``basic`` transfer adapter needs."""

    lfs_server: "LFSServer"

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
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

    def do_POST(self) -> None:
        if not self.path.rstrip("/").endswith("/objects/batch"):
            self.send_error(404)
            return

        request = json.loads(self._read_body() or b"{}")
        server = self.lfs_server
        objects: List[Dict] = []

        for requested in request.get("objects", []):
            oid = requested.get("oid", "")
            server.record_request(oid)
            size = requested.get("size", 0)
            entry: Dict = {"oid": oid, "size": size, "authenticated": True}
            href = f"{server.url}/storage/{oid}"

            if server.has_object(oid):
                entry["actions"] = {"download": {"href": href}}
            else:
                # the protocol's way of saying "this object is not here"
                entry["error"] = {"code": 404, "message": f"object {oid} not found"}
            objects.append(entry)

        self._send_json(200, {"transfer": "basic", "objects": objects})

    def log_message(self, format, *args):
        """Silence the default stderr access log; tests capture what they need."""

    def _oid_from_storage_path(self) -> Optional[str]:
        prefix = "/storage/"
        if prefix not in self.path:
            return None
        oid = self.path.rsplit(prefix, 1)[1].strip("/")
        # oids are hex sha256; refuse anything else so a path can never escape
        if len(oid) != 64 or not all(c in "0123456789abcdef" for c in oid):
            return None
        return oid

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
