"""Strict compatibility parser for saved Gobuster dir result lines."""

import re
from urllib.parse import urljoin

from fuzzrank.engines.base import collect, observation

LINE = re.compile(
    r"^(?P<url>\S+)\s+\(Status:\s*(?P<status>\d{3})\)"
    r"(?:\s+\[Size:\s*(?P<size>\d+)\])?(?:\s+\[-->\s*(?P<location>[^\r\n]+)\])?\s*$"
)


def parse(data: bytes, source: str, target: str | None = None):
    if target is None:
        raise ValueError("Gobuster import requires --target to resolve relative paths")
    text = data.decode("utf-8-sig")
    rows = [{"line": line} for line in text.splitlines() if line.strip()]

    def convert(row, name, number):
        match = LINE.fullmatch(row["line"])
        if not match:
            raise ValueError("Unsupported Gobuster result line; use a saved dir output file")
        values = match.groupdict()
        return observation(
            {
                "url": urljoin(target, values["url"]),
                "status_code": int(values["status"]),
                "content_length": int(values["size"]) if values["size"] else None,
                "location": values["location"] or "",
            },
            engine="gobuster",
            source=name,
            record=number,
        )

    return collect(rows, convert, source)
