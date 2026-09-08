"""Exact-origin filtering for imported records. This module performs no requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def canonical_url(url: str) -> str:
    if not isinstance(url, str) or re.search(r"[\x00-\x20\x7f\\]", url):
        raise ValueError("URL must be an HTTP(S) URL without whitespace or control characters")
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("URL must include an http:// or https:// origin")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Credentials in URLs are not supported")
    host = parts.hostname.encode("idna").decode("ascii").lower()
    if "%" in host or not re.fullmatch(r"[a-z0-9.\-:]+", host):
        raise ValueError("Invalid URL hostname")
    port = parts.port  # validates range and syntax
    if port == 0:
        raise ValueError("Port must be between 1 and 65535")
    netloc = f"[{host}]" if ":" in host else host
    if port and port != {"http": 80, "https": 443}[parts.scheme.lower()]:
        netloc += f":{port}"
    # Preserve path case, percent-encoding, slash and query ordering semantics.
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))


def origin(url: str) -> str:
    parts = urlsplit(canonical_url(url))
    return f"{parts.scheme}://{parts.netloc}"


@dataclass(frozen=True)
class Scope:
    target: str
    origins: frozenset[str]

    @classmethod
    def load(cls, target: str, scope_file: Path | None = None) -> Scope:
        target = canonical_url(target)
        origins = {origin(target)}
        if scope_file:
            for line in scope_file.read_text(encoding="utf-8-sig").splitlines():
                entry = line.strip()
                if not entry or entry.startswith("#"):
                    continue
                parsed = urlsplit(canonical_url(entry))
                if parsed.path != "/" or parsed.query or urlsplit(entry).fragment:
                    raise ValueError(
                        "Scope entries must be exact origins, without paths or wildcards"
                    )
                origins.add(origin(entry))
        return cls(target, frozenset(origins))

    def contains(self, url: str) -> bool:
        return origin(url) in self.origins
