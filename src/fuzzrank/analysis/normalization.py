"""Narrow normalization: labeled volatile fields only; no global UUID removal."""

from __future__ import annotations

import json
import re

VERSION = "labeled-volatile-v1"
TOKEN_KEYS = frozenset(
    {"request_id", "requestid", "correlation_id", "trace_id", "nonce", "csrf_token", "csrf_nonce"}
)
TIME_KEYS = frozenset({"timestamp", "generated_at", "request_time"})
TOKEN = re.compile(r"[a-zA-Z0-9_+/=\-]{16,256}\Z")
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z")
LABELED = re.compile(
    r"""(?P<label>\b(?:request[_-]?id|correlation_id|trace_id|nonce|csrf_token|csrf_nonce)"""
    r"""\s*[=:]\s*["']?)(?P<value>[A-Za-z0-9_+/=\-]{16,256})(?=["'\s<>]|$)""",
    re.IGNORECASE,
)
LABELED_TIME = re.compile(
    r"""(?P<label>\b(?:timestamp|generated_at|request_time)\s*[=:]\s*["']?)"""
    r"""\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"""
    r"""(?=["'\s<>]|$)""",
    re.IGNORECASE,
)


def _clean_json(value: object, key: str = "") -> object:
    if isinstance(value, dict):
        return {k: _clean_json(v, k.lower()) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_json(v) for v in value]
    if isinstance(value, str):
        if key in TOKEN_KEYS and TOKEN.fullmatch(value):
            return "<volatile-token>"
        if key in TIME_KEYS and ISO.fullmatch(value):
            return "<volatile-time>"
    return value


def normalize(body: bytes, content_type: str) -> tuple[bytes, str | None]:
    media = content_type.split(";", 1)[0].strip().lower()
    textual = media.startswith("text/") or media.endswith(("json", "+json", "xml", "+xml"))
    if not textual:
        return body, None
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return body, None
    if media.endswith(("json", "+json")):
        try:
            # Avoid silently collapsing duplicate object keys or changing number precision.
            def pairs(items: list[tuple]) -> dict:
                result = {}
                for key, value in items:
                    if key in result:
                        raise ValueError("duplicate JSON key")
                    result[key] = value
                return result

            def unsupported_number(value: str) -> None:
                raise ValueError("Preserve floating point and nonstandard number evidence verbatim")

            value = json.loads(
                text,
                object_pairs_hook=pairs,
                parse_float=unsupported_number,
                parse_constant=unsupported_number,
            )
            normalized = json.dumps(
                _clean_json(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")
            )
            return normalized.encode("utf-8"), normalized
        except (ValueError, RecursionError):
            return body, text
    text = LABELED.sub(lambda m: m["label"] + "<volatile-token>", text)
    text = LABELED_TIME.sub(lambda m: m["label"] + "<volatile-time>", text)
    return text.encode("utf-8"), text
