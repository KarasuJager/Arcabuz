from __future__ import annotations

import base64
import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import fields, is_dataclass
from pathlib import Path

from fuzzrank.models import Candidate, Report


def serializable(value):
    if is_dataclass(value):
        result = {f.name: serializable(getattr(value, f.name)) for f in fields(value)}
        if isinstance(value, Candidate):
            result["engines"] = value.engines
        return result
    if isinstance(value, bytes):
        return {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return value


def atomic_write(path: Path, content: bytes) -> None:
    atomic_write_chunks(path, [content])


def atomic_write_chunks(path: Path, content: Iterable[bytes]) -> None:
    """Replace only a completed file; temporary files remain in the same directory."""
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".fuzzrank-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            for chunk in content:
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class ReportEncoder(json.JSONEncoder):
    def default(self, value):
        if is_dataclass(value):
            result = {f.name: getattr(value, f.name) for f in fields(value)}
            if isinstance(value, Candidate):
                result["engines"] = value.engines
            return result
        if isinstance(value, (bytes, set, frozenset)):
            return serializable(value)
        return super().default(value)


def write(report: Report, path: Path) -> None:
    encoder = ReportEncoder(ensure_ascii=True, indent=2, allow_nan=False)
    atomic_write_chunks(path, (chunk.encode("utf-8") for chunk in encoder.iterencode(report)))
