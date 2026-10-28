"""Private Linux AF_UNIX admin construction, never public HTTP.

Development use is explicitly in-process and not isolation-qualified. Canonical
activation remains refused by SourceProfile. Authority is the only state engine.
"""
from dataclasses import asdict
import json
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import time
from typing import Callable

from .authority import Authority, canonical
from .driver import DevelopmentTask
from .supervisor import SourceProfile, contained_file
from .worker import _object

MAX_REQUEST_BYTES = 1024
MAX_RECEIPT_BYTES = 1048576


class PrivateAdmin:
    """Explicitly unqualified development reset/seal adapter.

    The operator UID must own the mode-0700 private directories; the worker UID
    is never accepted. Caller owns Authority lifetime and serializes its use.
    No actor-supplied run IDs, paths, SQL, commands, or authority handles.
    """
    def __init__(self, authority: Authority, profile: SourceProfile,
                 require_worker_stopped: Callable[[], None]):
        self.authority = authority
        self.profile = profile
        self._require_worker_stopped = require_worker_stopped
        self._task: DevelopmentTask | None = None
        self._listener: socket.socket | None = None
        self._requests = 0

    def bind_development(self) -> None:
        self.profile.validate()
        if (sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED")
                or os.getuid() != self.profile.authority_uid
                or os.getgid() != self.profile.authority_gid):
            raise RuntimeError("Linux configured authority identity required")
        if self._listener is not None:
            raise RuntimeError("admin socket already bound")
        path = self.profile.socket_root / "operator.sock"
        if path.exists() or path.is_symlink():
            raise ValueError("existing admin socket preserved; operator reconciliation required")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.settimeout(3)
            # Root is already private; no global umask or ancestor permissions changed.
            listener.bind(str(path))
            info = path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != self.profile.authority_uid:
                raise RuntimeError("unexpected admin socket ownership/type")
            os.chmod(path, 0o600, follow_symlinks=False)
            listener.listen(1)
        except BaseException:
            listener.close()
            raise
        self._listener = listener

    def _dispatch(self, request: object) -> dict[str, object]:
        if not isinstance(request, dict):
            raise ValueError("closed admin request required")
        operation = request.get("operation")
        if operation == "reset" and set(request) == {"operation", "family", "seed"}:
            family, seed = request["family"], request["seed"]
            if type(family) is not str or family not in {"F1", "F2", "F3"}:
                raise ValueError("development family required")
            if type(seed) is not int or not 0 <= seed <= 999:
                raise ValueError("bounded development seed required")
            self._require_worker_stopped()
            if self._task is not None:
                raise ValueError("seal current run before reset")
            self._task = DevelopmentTask(self.authority, family, seed)
            return {"status": "development-unqualified", "public": asdict(self._task.public)}
        if operation == "seal" and set(request) == {"operation"}:
            self._require_worker_stopped()
            if self._task is None:
                raise ValueError("no active development run")
            receipt = self.authority.seal(self._task.public)
            # Authority-generated run ID only; output root never comes from request.
            path = contained_file(self.profile.output_root,
                                  self._task.public.run_id + ".json")
            self._task = None  # sealed even if serialization/write subsequently fails
            encoded = canonical(receipt).encode("utf-8")
            if len(encoded) > MAX_RECEIPT_BYTES:
                raise ValueError("seal receipt exceeds output cap; no export claimed")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            fd = os.open(path, flags, 0o400)
            # No overwrites, deletes, DB export, or private handles to worker.
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            return {"status": "sealed-development-unqualified", "receipt": str(path),
                    "sha256": receipt["sha256"], "scorer_access": "read-only file; same authority UID",
                    "runtime_qualification": "UNVERIFIED"}
        raise ValueError("unknown operation or extra admin fields")

    def serve_once(self) -> None:
        if self._listener is None or self._requests >= 64:
            raise RuntimeError("bound admin listener and remaining request budget required")
        self._requests += 1
        connection, _ = self._listener.accept()
        with connection:
            _, uid, gid = struct.unpack("3i", connection.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
            if uid != self.profile.authority_uid or gid != self.profile.authority_gid:
                raise PermissionError("admin peer identity rejected")
            deadline = time.monotonic() + 3
            frame = bytearray()
            while not frame.endswith(b"\n"):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("admin request deadline")
                connection.settimeout(remaining)
                chunk = connection.recv(min(256, MAX_REQUEST_BYTES + 1 - len(frame)))
                if not chunk:
                    raise ValueError("truncated admin request")
                frame.extend(chunk)
                if len(frame) > MAX_REQUEST_BYTES or b"\n" in frame[:-1]:
                    raise ValueError("admin request frame rejected")
            request = json.loads(frame.decode("utf-8"), object_pairs_hook=_object)
            result = self._dispatch(request)
            response = canonical(result).encode("utf-8") + b"\n"
            if len(response) > 4096:
                raise ValueError("admin response cap exceeded")
            connection.settimeout(max(0.001, deadline - time.monotonic()))
            connection.sendall(response)

    def close(self) -> None:
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        # Preserve socket path. Never unlink a preexisting/replaced operator path.
