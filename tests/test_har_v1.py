"""Browser HAR fixtures are synthetic; no imported request is ever executed."""

import base64
import copy
import hashlib
import json
import socket

import pytest

from fuzzrank.cli import main
from fuzzrank.engines import detect, parse


def document(entry, version="1.2"):
    return json.dumps({"log": {"version": version, "entries": [entry]}}).encode()


@pytest.fixture
def entry(fixtures):
    return json.loads((fixtures / "browser.har").read_text())["log"]["entries"][0]


@pytest.mark.parametrize("version", ["1.1", "1.2"])
def test_har_versions(entry, version):
    data = document(entry, version)
    assert detect(data) == "har"
    result = parse(data, "capture")
    item = result.observations[0]
    assert item.engine == "har" and item.method == "GET"
    assert item.body == entry["response"]["content"]["text"].encode()
    assert item.body_source == "har-text-utf8"
    assert "wire bytes" in item.evidence_notes[0]
    assert item.timestamp == "2026-01-01T12:00:00.000Z"
    assert item.header_items == (("Content-Type", "application/json"),)
    assert not result.rejected_records


def test_har_binary_missing_and_redirect(fixtures):
    items = parse((fixtures / "browser.har").read_bytes(), "capture").observations
    assert items[1].body is None and items[1].content_length is None
    assert items[1].body_source == "unavailable"
    assert items[2].body == b"\x00\x01\x02\x03\xff"
    assert items[2].body_source == "har-base64"
    assert items[3].location == "https://identity.example/login"
    assert items[3].body == b""


@pytest.mark.parametrize("bad", [None, [], 1, "2.0", {}])
def test_har_unsupported_version(entry, bad):
    with pytest.raises(ValueError, match="versions"):
        parse(document(entry, bad), "capture", "har")


@pytest.mark.parametrize(
    "where,key,value",
    [
        ("request", "url", "file:///local/file"),
        ("request", "method", "GET\r\nheader"),
        ("response", "status", 0),
        ("response", "headers", None),
        ("response", "headers", {}),
        ("response", "headers", [{"name": "test", "value": 2}]),
        ("response", "content", []),
        ("content", "text", 12),
        ("content", "size", -2),
        ("content", "encoding", "gzip"),
        ("content", "encoding", {}),
        ("content", "_truncated", "yes"),
    ],
)
def test_har_malformed_entry_preserves_neighbors(entry, where, key, value):
    bad = copy.deepcopy(entry)
    destination = bad["response"]["content"] if where == "content" else bad[where]
    destination[key] = value
    data = json.dumps({"log": {"entries": [entry, bad, entry]}}).encode()
    result = parse(data, "capture", "har")
    assert len(result.observations) == 2 and result.rejected_records == 1
    assert any(d["severity"] == "error" and d["record"] == 2 for d in result.diagnostics)


def test_har_invalid_base64(entry):
    entry["response"]["content"].update(encoding="base64", text="not base64!")
    result = parse(document(entry), "capture")
    assert result.rejected_records == 1
    assert "base64" in result.warnings[0]


def test_har_repeated_headers_preserve_all_values(entry):
    entry["response"]["headers"] += [
        {"name": "Set-Cookie", "value": "fixture=one"},
        {"name": "Set-Cookie", "value": "fixture=two"},
    ]
    item = parse(document(entry), "capture").observations[0]
    assert item.header_items[-2:] == (("Set-Cookie", "fixture=one"), ("Set-Cookie", "fixture=two"))


def test_har_conflicting_type_headers_rejected(entry):
    entry["response"]["headers"].append({"name": "content-type", "value": "text/html"})
    assert parse(document(entry), "capture").rejected_records == 1


def test_har_baseline_and_truncation_tags(entry):
    entry["_fuzzrank_baseline"] = True
    entry["response"]["content"]["_truncated"] = True
    item = parse(document(entry), "capture").observations[0]
    assert item.baseline and item.truncated


def test_har_offline_cli_scope_and_original_evidence(fixtures, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("HAR import attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    source, output = fixtures / "browser.har", tmp_path / "report"
    assert main(["analyze", str(source), "--output", str(output), "--quiet"]) == 0
    report = json.loads((output / "report.json").read_text())
    assert report["summary"]["requests_made"] == 0
    assert report["summary"]["out_of_scope"] == 1
    manifest = report["sources"][0]
    assert (output / manifest["archive"]).read_bytes() == source.read_bytes()
    assert manifest["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    binary = next(c for c in report["candidates"] if c["path"] == "/logo.png")
    assert base64.b64decode(binary["primary"]["body"]["data"]) == b"\x00\x01\x02\x03\xff"
    assert all(c["evidence_gaps"] and c["score_reasons"] for c in report["candidates"])
