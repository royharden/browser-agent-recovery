"""Trusted boundary construction; canonical activation deliberately fails closed.

No namespace, egress or UID denial qualification is implemented by this module.
Only direct children created by OwnedWorker can be stopped by it.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import stat
import subprocess
import sys


MISSING_HOOKS = (
    "privileged launcher with distinct nonroot authority/worker UID and GID",
    "mount/user/network namespaces and deny-by-default worker egress",
    "worker filesystem/ACL denial of authority DB, socket, ledger and output",
    "descendant containment and bounded whole-worker termination acknowledgement",
    "fresh browser context per run with trusted receipt/DOM IPC joined",
    "Linux UID/ACL/egress/descriptor denial probes and external admission",
)


class BoundaryUnavailable(RuntimeError):
    pass


def private_root(path: Path, uid: int) -> Path:
    """Validate provisioned root; never create/chown/chmod caller paths.

    Linux deployment must additionally pin roots by descriptors/mounts to prevent
    rename races. This preflight alone is not a filesystem sandbox.
    """
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute canonical private root required")
    if any("onedrive" in part.casefold() for part in path.parts):
        raise ValueError("private roots must be outside OneDrive")
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("symlink component rejected")
        if not component.is_dir():
            raise ValueError("provisioned directory required")
        # No untrusted writer may replace selected roots through an ancestor.
        if os.name == "posix" and component.stat().st_mode & 0o022:
            raise ValueError("group/world writable root ancestor rejected")
    info = path.stat()
    if os.name != "posix" or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o700:
        raise BoundaryUnavailable("Linux authority-owned mode-0700 roots required")
    return path


def contained_file(root: Path, name: str) -> Path:
    """A single fixed basename; no actor-selected paths or existing symlinks."""
    if (not name or name in {".", ".."} or any(c not in
            "abcdefghijklmnopqrstuvwxyz0123456789-_." for c in name)):
        raise ValueError("safe private basename required")
    target = root / name
    if target.parent != root or target.is_symlink():
        raise ValueError("private path containment rejected")
    if target.exists() and (not target.is_file() or target.stat().st_nlink != 1):
        raise ValueError("private regular unlinked file required")
    return target


@dataclass(frozen=True)
class SourceProfile:
    authority_uid: int
    authority_gid: int
    worker_uid: int
    worker_gid: int
    database_root: Path
    socket_root: Path
    output_root: Path
    stop_timeout_s: int = 3
    max_worker_bytes: int = 16384

    def validate(self) -> None:
        ids = (self.authority_uid, self.authority_gid, self.worker_uid, self.worker_gid)
        if any(type(value) is not int or not 1 <= value <= 2**31 - 1 for value in ids):
            raise ValueError("configured nonroot numeric identities required")
        if self.authority_uid == self.worker_uid or self.authority_gid == self.worker_gid:
            raise ValueError("distinct authority/worker UID and GID required")
        if type(self.stop_timeout_s) is not int or not 1 <= self.stop_timeout_s <= 10:
            raise ValueError("bounded stop timeout required")
        if type(self.max_worker_bytes) is not int or not 1 <= self.max_worker_bytes <= 16384:
            raise ValueError("bounded worker frame cap required")
        roots = (self.database_root, self.socket_root, self.output_root)
        for root in roots:
            private_root(root, self.authority_uid)
        if any(a == b or a in b.parents or b in a.parents
               for i, a in enumerate(roots) for b in roots[i + 1:]):
            raise ValueError("separate nonoverlapping private roots required")

    def construction_report(self) -> dict[str, object]:
        return {"profile": "canonical-source-unjoined", "activated": False,
                "runtime_qualification": "UNVERIFIED", "missing_hooks": MISSING_HOOKS}

    def require_activation(self) -> None:
        self.validate()
        # Never accept caller booleans/certificates as completed enforcement.
        raise BoundaryUnavailable("canonical activation refused: " + "; ".join(MISSING_HOOKS))


def minimal_worker_environment() -> dict[str, str]:
    """Literal whitelist, never os.environ.copy(): no credentials/private paths."""
    return {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"}


class OwnedWorker:
    """Direct-child lifecycle source. No public arbitrary argv or shell API.

    Canonical start is refused until the missing privileged launcher is joined.
    A direct Popen child alone would not contain browser descendants.
    """
    def __init__(self, profile: SourceProfile):
        self.profile = profile
        self._child: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        self.profile.require_activation()
        # Deliberately no Popen fallback. Future launcher must own all descendants,
        # close all inherited FDs and drop supplementary groups before exec.
        raise BoundaryUnavailable("privileged worker launcher is not joined")

    def launch_plan(self) -> dict[str, object]:
        """Reviewable fixed source plan, not an executable activation receipt."""
        return {"argv": (sys.executable, "-I", "-m", "rlab.worker"),
                "shell": False, "close_fds": True, "pass_fds": (),
                "env": minimal_worker_environment(), "uid": self.profile.worker_uid,
                "gid": self.profile.worker_gid, "supplementary_groups": (),
                "status": "UNJOINED; no process launched"}

    def stop(self) -> None:
        child = self._child
        if child is None:
            return
        if child.poll() is None:
            child.terminate()  # Only our retained Popen handle; no PID scans/groups.
            try:
                child.wait(timeout=self.profile.stop_timeout_s)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=self.profile.stop_timeout_s)
        self._child = None

    def require_stopped(self) -> None:
        if self._child is not None:
            raise BoundaryUnavailable("stop and acknowledge owned worker before seal/reset")
        # No launch means no sandbox-qualified stopped run either. An admin caller
        # may use this callback for explicitly labelled in-process development.
