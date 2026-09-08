"""Native feroxbuster NDJSON; non-response event records are preserved in the archive."""

from fuzzrank.engines.base import collect, decode_json, json_lines, observation


def parse(data: bytes, source: str, target: str | None = None):
    try:
        document = decode_json(data)
        rows = document if isinstance(document, list) else [document]
    except ValueError:
        rows = json_lines(data)

    def convert(row, name, number):
        if row.get("type") != "response":
            if row.get("type") in {"configuration", "statistics", "log", "scan", "error"}:
                return None
            raise ValueError("Expected a feroxbuster response event")
        mapped = {**row, "status_code": row.get("status")}
        # Native feroxbuster reports may have discarded their text before serialization.
        # Never fabricate a body, or use original_url as the response URL after a redirect.
        return observation(mapped, engine="feroxbuster", source=name, record=number)

    return collect(rows, convert, source)
