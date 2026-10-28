"""Private operator media receipts; importing this module performs no capture.

The byte and local-monotonic time budgets bound inspection/reporting, not browser
output or disk usage. Private modes and no-follow checks express intent; Windows
ACLs, filesystem races, native writer behavior and hard quotas need qualification.
No file is deleted, including failed, partial and unselected captures.
"""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from time import monotonic_ns
from typing import Literal
from uuid import uuid4


MediaKind = Literal["trace", "video"]
MediaState = Literal["not_requested", "pending", "complete", "partial", "failed", "unavailable"]
Outcome = Literal["failure", "success", "unknown"]
Selection = Literal["selected", "unselected", "unknown"]


@dataclass(frozen=True)
class MediaCapturePolicy:
    """Trusted fixed configuration, never populated from actor input.

    The output root must already exist and be operator-provisioned. Add every
    private/main product checkout to excluded_roots; Worktrees and OneDrive
    components and this module's checkout are refused independently.
    """
    enabled: bool = False
    output_root: Path | None = None
    excluded_roots: tuple[Path, ...] = ()
    max_artifacts: int = 8
    max_file_bytes: int = 256 * 1024 * 1024
    max_total_bytes: int = 512 * 1024 * 1024
    max_capture_ns: int = 120_000_000_000
    max_inspection_ns: int = 10_000_000_000


@dataclass(frozen=True)
class MediaArtifact:
    kind: str
    name: str
    status: MediaState
    completed_path: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    error: str = ""
    retained_path: str | None = None


@dataclass(frozen=True)
class MediaManifest:
    requested: bool
    run_key_digest: str
    selection: Selection
    selection_reason: str
    trace_status: MediaState
    video_status: MediaState
    artifacts: tuple[MediaArtifact, ...]
    diagnostics: tuple[str, ...]
    capture_clock: str
    capture_started_ns: int | None
    capture_finished_ns: int | None
    declared_max_capture_ns: int
    declared_max_file_bytes: int
    declared_max_total_bytes: int
    declared_max_artifacts: int
    budget_enforcement: str = "post-close media inspection; manifest <=65536 bytes; no hard disk quota"
    manifest_artifact: MediaArtifact | None = None

    def evaluator_references(self, report_root: Path) -> tuple[str, ...]:
        """Return only completed permitted references under an explicit private root.

        No copy, search, upload, absolute fallback or invented manifest link.
        trace.zip remains in the private JSON receipt, not the evaluator field.
        Unknown selection retains/references available media. Unselected success
        still references its manifest, which explains private retention.
        """
        try:
            root = _checked_directory(Path(report_root))
            candidates = (() if self.manifest_artifact is None else
                          (self.manifest_artifact,))
            if self.selection != "unselected":
                candidates += tuple(a for a in self.artifacts if a.kind == "video")
            result = []
            for artifact in candidates:
                if artifact.status != "complete" or artifact.completed_path is None:
                    continue
                path = Path(artifact.completed_path)
                relative = path.relative_to(root)
                if (path.suffix.lower() not in {".json", ".webm", ".mp4"}
                        or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", p)
                               for p in relative.parts)):
                    continue
                result.append(relative.as_posix())
            return tuple(result)
        except (OSError, ValueError, TypeError):
            return ()


def _contains(root: Path, path: Path) -> bool:
    return path == root or root in path.parents


def _checked_directory(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute directory without traversal required")
    # Check each existing ancestor before resolve; refuse junctions/reparse
    # points too on Windows, where O_NOFOLLOW may not be available.
    for part in reversed((path,) + tuple(path.parents)):
        info = part.lstat()
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400
                or not stat.S_ISDIR(info.st_mode)):
            raise ValueError("directory link/reparse/non-directory refused")
    return path.resolve(strict=True)


def _safe_error(stage: str, exc: object) -> str:
    # Exception messages may contain URLs, DOM, host paths or credentials.
    # Keep only a closed stage token and exception class, never str(exc).
    token = stage if re.fullmatch(r"[a-z_]{1,48}", stage) else "media"
    return (token + ":" + type(exc).__name__)[:96]


class MediaCaptureSession:
    """One run, one allocation, one immutable finalization; no browser ownership."""
    def __init__(self, policy: MediaCapturePolicy, run_key: str):
        self.policy = policy
        self._run_digest = sha256(str(run_key).encode("utf-8")).hexdigest()
        self._root: Path | None = None
        self._run_dir: Path | None = None
        self._trace_path: Path | None = None
        self._video_dir: Path | None = None
        self._started: int | None = None
        self._did_start = False
        self._states: dict[str, MediaState] = {"trace": "not_requested", "video": "not_requested"}
        self._artifacts: list[MediaArtifact] = []
        self._diagnostics: list[str] = []
        self._manifest: MediaManifest | None = None

    @property
    def active(self) -> bool:
        return (self._trace_path is not None and self._video_dir is not None
                and self._manifest is None)

    @property
    def trace_path(self) -> Path | None:
        return self._trace_path

    @property
    def video_dir(self) -> Path | None:
        return self._video_dir

    @property
    def manifest(self) -> MediaManifest | None:
        return self._manifest

    @property
    def status(self) -> tuple[str, str, str]:
        error = ";".join(self._diagnostics)[:768]
        if not self.policy.enabled:
            error = "trace/video not requested"
        return self._states["trace"], self._states["video"], error

    def note_error(self, stage: str, exc: object) -> None:
        if self._manifest is not None:
            return
        diagnostic = _safe_error(stage, exc)
        if diagnostic not in self._diagnostics and len(self._diagnostics) < 16:
            self._diagnostics.append(diagnostic)
        for kind in ("trace", "video"):
            if stage.startswith(kind):
                self._states[kind] = ("partial" if self._states[kind] in {"pending", "complete", "partial"}
                                      else "failed")

    def start(self) -> "MediaCaptureSession":
        if self._did_start or self._manifest is not None:
            return self
        self._did_start = True
        if not self.policy.enabled:
            return self
        self._states = {"trace": "unavailable", "video": "unavailable"}
        try:
            p = self.policy
            numbers = (p.max_artifacts, p.max_file_bytes, p.max_total_bytes,
                       p.max_capture_ns, p.max_inspection_ns)
            if (type(p.enabled) is not bool or any(type(value) is not int for value in numbers)
                    or not 1 <= p.max_artifacts <= 32
                    or not 1 <= p.max_file_bytes <= 1024 * 1024 * 1024
                    or not p.max_file_bytes <= p.max_total_bytes <= 4 * 1024 * 1024 * 1024
                    or not 1 <= p.max_capture_ns <= 3_600_000_000_000
                    or not 1 <= p.max_inspection_ns <= 60_000_000_000
                    or p.output_root is None):
                raise ValueError("bounded explicit operator policy required")
            root = _checked_directory(Path(p.output_root))
            if any(x.casefold() in {"onedrive", "onedrive-personal", "worktrees"}
                   or x.casefold().startswith("onedrive - ") for x in root.parts):
                raise ValueError("OneDrive/worktree media root refused")
            excluded = (Path(__file__).resolve().parents[2],) + tuple(p.excluded_roots)
            for path in excluded:
                if not Path(path).is_absolute():
                    raise ValueError("absolute excluded root required")
                if _contains(Path(path).resolve(), root):
                    raise ValueError("product media root refused")
            self._root = root
            run_dir = root / ("capture-" + self._run_digest[:16] + "-" + uuid4().hex)
            run_dir.mkdir(mode=0o700)  # exclusive; preserve on any later failure
            self._run_dir = _checked_directory(run_dir)
            video = run_dir / "video"
            video.mkdir(mode=0o700)
            self._video_dir = _checked_directory(video)
            self._trace_path = run_dir / "trace.zip"
            self._started = monotonic_ns()
            self._states = {"trace": "pending", "video": "pending"}
        except Exception as exc:
            self.note_error("allocation", exc)
            self._trace_path = self._video_dir = None
        return self

    def record_started(self, kind: MediaKind) -> None:
        if self.active and kind in self._states:
            self._states[kind] = "pending"

    note_started = record_started

    def _inspect(self, kind: str, path: Path, *, max_bytes: int) -> MediaArtifact:
        if self._run_dir is None or not path.is_absolute():
            raise ValueError("allocated absolute capture path required")
        relative = path.relative_to(self._run_dir)
        if (not relative.parts or len(relative.parts) > 2
                or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", x) or x in {".", ".."}
                       for x in relative.parts)):
            raise ValueError("bounded owned capture name required")
        parent = _checked_directory(path.parent)
        if not _contains(self._run_dir, parent):
            raise ValueError("capture escaped run directory")
        initial = path.lstat()
        if (not stat.S_ISREG(initial.st_mode) or initial.st_size <= 0
                or getattr(initial, "st_file_attributes", 0) & 0x400
                or initial.st_nlink != 1):
            raise ValueError("nonempty nonlinked regular capture required")
        if initial.st_size > max_bytes:
            raise ValueError("declared inspection byte budget exceeded")
        started = monotonic_ns()
        digest = sha256()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino, opened.st_size) !=
                    (initial.st_dev, initial.st_ino, initial.st_size)):
                raise ValueError("capture changed before inspection")
            read = 0
            while True:
                if monotonic_ns() - started > self.policy.max_inspection_ns:
                    raise TimeoutError("local inspection budget exceeded")
                chunk = stream.read(min(65536, max_bytes - read + 1))
                if not chunk:
                    break
                read += len(chunk)
                if read > max_bytes:
                    raise ValueError("inspection byte budget exceeded")
                digest.update(chunk)
            final = os.fstat(stream.fileno())
            after = path.lstat()
            signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if (read != initial.st_size or signature(initial) != signature(final)
                    or signature(final) != signature(after)):
                raise ValueError("capture changed during inspection")
        return MediaArtifact(kind, relative.as_posix(), "complete", str(path), read, digest.hexdigest())

    def register_completed(self, kind: MediaKind, path: Path) -> None:
        if not self.active or kind not in {"trace", "video"}:
            return
        try:
            path = Path(path)
            if ((kind == "trace" and path != self._trace_path)
                    or (kind == "video" and (path.parent != self._video_dir
                                             or path.suffix.lower() not in {".webm", ".mp4"}))):
                raise ValueError("fixed capture destination required")
            if any(a.completed_path == str(path) for a in self._artifacts):
                return
            if len(self._artifacts) >= self.policy.max_artifacts:
                raise ValueError("declared artifact count exceeded")
            used = sum(a.size_bytes or 0 for a in self._artifacts)
            artifact = self._inspect(kind, path, max_bytes=min(self.policy.max_file_bytes,
                                                             self.policy.max_total_bytes - used))
            self._artifacts.append(artifact)
            self._states[kind] = ("partial" if any(x.startswith(kind + "_")
                                                   for x in self._diagnostics) else "complete")
        except Exception as exc:
            self.note_error(kind + "_inspect", exc)
            # A failed later artifact does not erase an earlier valid receipt.
            self._states[kind] = "partial"

    def finalize(self, *, outcome: Outcome = "unknown", sample_key: str | None = None) -> MediaManifest:
        if self._manifest is not None:
            return self._manifest
        self.start()
        finished = monotonic_ns() if self._started is not None else None
        if self._started is not None and finished - self._started > self.policy.max_capture_ns:
            self.note_error("capture_budget", TimeoutError())
            self._states = {kind: "partial" for kind in self._states}
        # A failed tracing.stop can leave a real partial ZIP. Inspect only the
        # one preallocated trace name; never scan a directory or claim it closed.
        if (self._trace_path is not None and self._run_dir is not None
                and not any(a.kind == "trace" for a in self._artifacts)):
            try:
                self._trace_path.lstat()
                if len(self._artifacts) >= self.policy.max_artifacts:
                    raise ValueError("declared artifact count exceeded")
                used = sum(a.size_bytes or 0 for a in self._artifacts)
                partial = self._inspect("trace", self._trace_path,
                                        max_bytes=min(self.policy.max_file_bytes,
                                                      self.policy.max_total_bytes - used))
                self._artifacts.append(replace(partial, status="partial", completed_path=None,
                                               retained_path=partial.completed_path,
                                               error="trace completion not established"))
                self._states["trace"] = "partial"
            except FileNotFoundError:
                pass
            except Exception as exc:
                self.note_error("trace_partial_inspect", exc)
        for kind in ("trace", "video"):
            if self._states[kind] == "pending":
                self._states[kind] = "partial"
        selection: Selection = "unknown"
        reason = "outcome unavailable; retain all available media privately"
        if outcome == "failure":
            selection, reason = "selected", "failure always selected"
        elif outcome == "success" and isinstance(sample_key, str) and 1 <= len(sample_key) <= 512:
            # Stable paired variant/block key only. No arm, score, timestamp,
            # random state or favorable-outcome value enters this decision.
            selected = int.from_bytes(sha256(sample_key.encode("utf-8")).digest()[:8], "big") % 10 == 0
            selection = "selected" if selected else "unselected"
            reason = "stable paired-key 10 percent bucket; all captures retained privately"
        elif outcome == "success":
            reason = "stable paired-key unavailable; retain all available media privately"
        manifest = MediaManifest(self.policy.enabled, self._run_digest, selection, reason,
                                 self._states["trace"], self._states["video"],
                                 tuple(self._artifacts), tuple(self._diagnostics),
                                 "local_monotonic_ns; not authority/effect clock", self._started,
                                 finished, self.policy.max_capture_ns, self.policy.max_file_bytes,
                                 self.policy.max_total_bytes, self.policy.max_artifacts)
        if self._run_dir is not None:
            try:
                path = self._run_dir / "manifest.json"
                _checked_directory(self._run_dir)
                payload = json.dumps(asdict(manifest), sort_keys=True, separators=(",", ":")).encode("utf-8")
                if len(payload) > 65536:
                    raise ValueError("bounded manifest exceeded")
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(path, flags, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                receipt = self._inspect("manifest", path, max_bytes=65536)
                manifest = replace(manifest, manifest_artifact=receipt)
            except Exception as exc:
                self.note_error("manifest_write", exc)
                manifest = replace(manifest, diagnostics=tuple(self._diagnostics),
                                   manifest_artifact=MediaArtifact("manifest", "manifest.json", "failed",
                                                                   error=_safe_error("manifest_write", exc)))
        self._manifest = manifest
        return manifest
