from fuzzrank.engines import evidence, feroxbuster, ffuf, gobuster, har
from fuzzrank.engines.base import decode_json, json_lines

ADAPTERS = {
    "ffuf": ffuf.parse,
    "feroxbuster": feroxbuster.parse,
    "gobuster": gobuster.parse,
    "evidence": evidence.parse,
    "har": har.parse,
}


def detect(data: bytes) -> str:
    try:
        document = decode_json(data)
    except ValueError:
        document = next((x for x in json_lines(data) if isinstance(x, dict)), None)
    if isinstance(document, list):
        document = next((x for x in document if isinstance(x, dict)), None)
    if isinstance(document, dict):
        if isinstance(document.get("log"), dict) and "entries" in document["log"]:
            return "har"
        if document.get("format") == "fuzzrank-evidence-v1":
            return "evidence"
        if "results" in document or ("url" in document and "length" in document):
            return "ffuf"
        if "type" in document:
            return "feroxbuster"
    if any(gobuster.LINE.fullmatch(line) for line in data.decode("utf-8-sig").splitlines()):
        return "gobuster"
    raise ValueError(
        "Unrecognized input; use --format ffuf, feroxbuster, gobuster, har, or evidence"
    )


def parse(data: bytes, source: str, format_name: str = "auto", target: str | None = None):
    name = detect(data) if format_name == "auto" else format_name
    return ADAPTERS[name](data, source, target)
