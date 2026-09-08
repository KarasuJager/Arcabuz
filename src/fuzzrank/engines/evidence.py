"""Portable evidence bundle input; body_base64 preserves exact response bytes."""

from fuzzrank.engines.base import collect, decode_json, observation


def parse(data: bytes, source: str, target: str | None = None):
    document = decode_json(data)
    if not isinstance(document, dict) or document.get("format") != "fuzzrank-evidence-v1":
        raise ValueError("Expected format: fuzzrank-evidence-v1")
    rows = document.get("observations")
    if not isinstance(rows, list):
        raise ValueError("Evidence observations must be an array")

    def convert(row, name, number):
        return observation(row, engine=row.get("engine", "evidence"), source=name, record=number)

    return collect(rows, convert, source)
