"""ffuf native JSON, EJSON and JSONL imports; no scan subprocesses."""

from collections.abc import Iterable

from fuzzrank.engines.base import collect, decode_json, json_lines, observation


def parse(data: bytes, source: str, target: str | None = None):
    try:
        document = decode_json(data)
    except ValueError as exc:
        if '"results"' in data[:4096].decode("utf-8", errors="replace"):
            raise ValueError(
                "Truncated or malformed ffuf JSON envelope; cannot recover its array"
            ) from exc
        document = json_lines(data)
    default_method = "GET"
    timestamp = None
    if isinstance(document, dict) and "results" in document:
        config = document.get("config") or {}
        if not isinstance(config, dict):
            raise ValueError("ffuf config must be an object")
        default_method = config.get("method", "GET")
        timestamp = document.get("time")
        rows = document["results"]
    elif isinstance(document, dict):
        rows = [document]
    else:
        rows = document
    if not isinstance(rows, Iterable) or isinstance(rows, (str, dict)):
        raise ValueError("ffuf results must be an array")

    def convert(row, name, number):
        mapped = {
            "url": row.get("url"),
            "method": row.get("method", default_method),
            "status_code": row.get("status"),
            "content_length": row.get("length"),
            "word_count": row.get("words"),
            "line_count": row.get("lines"),
            "content_type": row.get("content-type", ""),
            "location": row.get("redirectlocation", ""),
            "timestamp": timestamp,
        }
        return observation(mapped, engine="ffuf", source=name, record=number)

    return collect(rows, convert, source)
