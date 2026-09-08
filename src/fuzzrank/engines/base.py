"""Shared bounded input loading and strict record validation."""

from __future__ import annotations

import base64
import json
import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path

from fuzzrank.models import ImportResult, Observation
from fuzzrank.scope import canonical_url

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_INPUT_BYTES = 128 * 1024 * 1024
MAX_BODY_BYTES = 1024 * 1024
MAX_RECORDS = 100_000


def read_input(path: Path, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    chunks, size = [], 0
    with path.open("rb") as stream:
        while size <= max_bytes:
            chunk = stream.read(min(65536, max_bytes + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
    if size > max_bytes:
        raise ValueError(
            f"{path.name}: input exceeds the {max_bytes} byte limit; split it into smaller files"
        )
    return b"".join(chunks)


def _integer(value: object, label: str, optional: bool = True) -> int | None:
    if value is None and optional:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def observation(row: dict, *, engine: str, source: str, record: int) -> Observation:
    status = _integer(row.get("status_code"), "status_code", optional=False)
    if status is None or not 100 <= status <= 599:
        raise ValueError("status_code must be between 100 and 599")
    method = row.get("method", "GET")
    if not isinstance(method, str) or not re.fullmatch(r"[A-Za-z!#$%&'*+.^_`|~-]{1,32}", method):
        raise ValueError("Invalid HTTP method")
    headers = row.get("headers", {})
    if not isinstance(headers, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in headers.items()
    ):
        raise ValueError("headers must map strings to strings")
    headers = {k.lower(): v for k, v in headers.items()}
    body = None
    if row.get("body_base64") is not None and row.get("body") is not None:
        raise ValueError("Specify either body or body_base64, not both")
    if row.get("body_base64") is not None:
        try:
            body = base64.b64decode(row["body_base64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid base64 body") from exc
    elif row.get("body") is not None:
        if not isinstance(row["body"], str):
            raise ValueError("body must be a UTF-8 string")
        body = row["body"].encode("utf-8")
    if body is not None and len(body) > MAX_BODY_BYTES:
        raise ValueError(
            "Body exceeds the 1 MiB limit; original input remains in the source archive"
        )
    truncated = row.get("truncated", False)
    if type(truncated) is not bool:
        raise ValueError("truncated must be a boolean")
    baseline = row.get("baseline", False)
    if type(baseline) is not bool:
        raise ValueError("baseline must be a boolean")
    content_type = row.get("content_type", headers.get("content-type", ""))
    location = row.get("location", headers.get("location", ""))
    if not isinstance(content_type, str) or not isinstance(location, str):
        raise ValueError("content_type and location must be strings")
    timestamp = row.get("timestamp")
    if timestamp is not None and type(timestamp) not in (str, float, int):
        raise ValueError("timestamp must be a string or number")
    if isinstance(timestamp, float) and not math.isfinite(timestamp):
        raise ValueError("timestamp must be finite")
    url = row.get("url")
    canonical_url(url)  # Validate, but preserve the original URL in evidence.
    if not isinstance(engine, str) or not engine.strip() or len(engine) > 80:
        raise ValueError("engine must be a nonempty string of at most 80 characters")
    return Observation(
        engine=engine,
        method=method.upper(),
        url=url,
        status_code=status,
        content_length=_integer(row.get("content_length"), "content_length"),
        word_count=_integer(row.get("word_count"), "word_count"),
        line_count=_integer(row.get("line_count"), "line_count"),
        headers=headers,
        content_type=content_type,
        location=location,
        timestamp=timestamp,
        body=body,
        truncated=truncated,
        source=source,
        record=record,
        baseline=baseline,
    )


def _unique_mapping(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key[:80]}")
        result[key] = value
    return result


def decode_json(data: bytes) -> object:
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique_mapping)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc


class BodyPool:
    """Investigation-scoped interning, never a process-global evidence cache."""

    def __init__(self):
        self.bodies: dict[bytes, bytes] = {}

    def intern(self, item: Observation) -> Observation:
        if item.body is None:
            return item
        shared = self.bodies.setdefault(item.body, item.body)
        return item if shared is item.body else replace(item, body=shared)


@dataclass(frozen=True)
class InvalidRecord:
    reason: str


def collect(rows: Iterable, converter: Callable, source: str) -> ImportResult:
    result = ImportResult()
    if isinstance(rows, list) and len(rows) > MAX_RECORDS:
        raise ValueError(f"{source}: exceeds {MAX_RECORDS} records")
    pool = BodyPool()
    for number, row in enumerate(rows, 1):
        if number > MAX_RECORDS:
            raise ValueError(f"{source}: exceeds {MAX_RECORDS} records")
        try:
            if isinstance(row, InvalidRecord):
                raise ValueError(row.reason)
            if not isinstance(row, dict):
                raise ValueError("record must be an object")
            item = converter(row, source, number)
            if item is None:
                result.ignored_records += 1
            else:
                result.observations.append(pool.intern(item))
                for note in item.evidence_notes:
                    result.diagnostics.append(
                        {"severity": "warning", "source": source, "record": number, "message": note}
                    )
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
            result.rejected_records += 1
            result.diagnostics.append(
                {"severity": "error", "source": source, "record": number, "message": str(exc)}
            )
            if len(result.warnings) < 30:
                result.warnings.append(f"{source}, record {number}: {exc}")
    if result.rejected_records > 30:
        result.warnings.append(f"{result.rejected_records - 30} further record errors omitted")
    return result


def json_lines(data: bytes) -> Iterable:
    for line in BytesIO(data.removeprefix(b"\xef\xbb\xbf")):
        if line.strip():
            try:
                yield json.loads(line.decode("utf-8"), object_pairs_hook=_unique_mapping)
            except (ValueError, RecursionError) as exc:
                yield InvalidRecord(f"Invalid JSONL record: {exc}")
