"""Exact loopback task-route policy; backend must enforce it on every request."""
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class RoutePolicy:
    origin: str
    start_path: str

    def __post_init__(self) -> None:
        if (not isinstance(self.origin, str) or any(c in self.origin for c in "%\\?#")
                or any(ord(c) < 33 for c in self.origin)):
            raise ValueError("canonical origin required")
        parsed = urlsplit(self.origin)
        if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}
                or parsed.port is None or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("explicit exact loopback HTTP origin required")
        if (not self.start_path.startswith("/tasks/") or len(self.start_path) > 512
                or any(c in self.start_path for c in "%\\?#")
                or any(ord(c) < 33 for c in self.start_path)
                or any(p in {"", ".", ".."} for p in self.start_path[1:].split("/"))):
            raise ValueError("canonical task namespace required")

    def authorize(self, url: str, method: str, *, redirect: bool = False,
                  download: bool = False, upload: bool = False) -> str:
        if (not isinstance(url, str) or len(url) > 768 or type(method) is not str
                or redirect or download or upload
                or any(c in url for c in "%\\?#") or any(ord(c) < 33 for c in url)
                or url.startswith("//")):
            raise ValueError("unsafe browser request")
        parsed = urlsplit(url)
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("query/fragment/user-info refused")
        if parsed.scheme or parsed.netloc:
            if parsed.scheme + "://" + parsed.netloc != self.origin:
                raise ValueError("other origin refused")
        elif not url.startswith("/"):
            raise ValueError("only absolute local paths accepted")
        path = parsed.path
        allowed = {self.start_path: {"GET"}, self.start_path + "/history": {"GET"},
                   self.start_path + "/action": {"POST"}}
        if path not in allowed or method not in allowed[path]:
            raise ValueError("path or method outside closed task routes")
        return self.origin + path
