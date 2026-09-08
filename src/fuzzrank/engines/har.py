"""Offline HAR 1.1/1.2 metadata and response-body import. No request replay."""

from dataclasses import replace

from fuzzrank.engines.base import collect, decode_json, observation


def parse(data: bytes, source: str, target: str | None = None):
    document = decode_json(data)
    log = document.get("log") if isinstance(document, dict) else None
    if not isinstance(log, dict) or not isinstance(log.get("entries"), list):
        raise ValueError("HAR must contain log.entries as an array")
    version = log.get("version", "1.2")
    if not isinstance(version, str) or version not in {"1.1", "1.2"}:
        raise ValueError("Supported HAR versions are 1.1 and 1.2")

    def convert(entry, name, number):
        request, response = entry.get("request"), entry.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            raise ValueError("HAR entry requires request and response objects")
        content = response.get("content", {})
        if not isinstance(content, dict):
            raise ValueError("HAR response.content must be an object")
        headers, items, notes = {}, [], []
        pairs = response.get("headers", [])
        if not isinstance(pairs, list):
            raise ValueError("HAR response.headers must be an array")
        for pair in pairs:
            if (
                not isinstance(pair, dict)
                or not isinstance(pair.get("name"), str)
                or not isinstance(pair.get("value"), str)
            ):
                raise ValueError("HAR headers must contain string name/value pairs")
            key, value = pair["name"].lower(), pair["value"]
            items.append((pair["name"], value))
            if key in headers:
                if key in {"content-type", "location"} and headers[key] != value:
                    raise ValueError(f"Conflicting HAR {key} headers")
                notes.append(f"Repeated {key} header; all values preserved in header_items")
            else:
                headers[key] = value
        size = content.get("size", response.get("bodySize"))
        if size == -1:
            size = None
        row = {
            "url": request.get("url"),
            "method": request.get("method", "GET"),
            "status_code": response.get("status"),
            "content_length": size,
            "content_type": content.get("mimeType", headers.get("content-type", "")),
            "headers": headers,
            "location": response.get("redirectURL") or headers.get("location", ""),
            "timestamp": entry.get("startedDateTime"),
            "baseline": entry.get("_fuzzrank_baseline", False),
            "truncated": content.get("_truncated", entry.get("_truncated", False)),
        }
        encoding = content.get("encoding")
        if encoding not in (None, "", "base64"):
            raise ValueError(f"Unsupported HAR content encoding: {encoding}")
        body_source = "unavailable"
        if "text" in content:
            row["body_base64" if encoding == "base64" else "body"] = content["text"]
            body_source = "har-base64" if encoding == "base64" else "har-text-utf8"
            if encoding != "base64":
                notes.append(
                    "HAR text was exported as Unicode; hashes describe its UTF-8 encoding, "
                    "not necessarily the original wire bytes"
                )
        else:
            notes.append("HAR response body was not included in the export")
        item = observation(row, engine="har", source=name, record=number)
        return replace(
            item, body_source=body_source, evidence_notes=tuple(notes), header_items=tuple(items)
        )

    return collect(log["entries"], convert, source)
