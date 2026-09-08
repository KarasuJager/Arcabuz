import base64
import json

import pytest

from fuzzrank.engines import detect, parse
from fuzzrank.engines.base import observation


@pytest.mark.parametrize(
    "filename,engine,count",
    [
        ("ffuf.json", "ffuf", 3),
        ("ferox.jsonl", "feroxbuster", 3),
        ("gobuster.txt", "gobuster", 3),
    ],
)
def test_native_formats(fixtures, filename, engine, count):
    data = (fixtures / filename).read_bytes()
    assert detect(data) == engine
    result = parse(data, filename, target="https://fixture.example")
    assert len(result.observations) == count
    assert not result.warnings
    assert all(o.engine == engine for o in result.observations)
    assert all(o.body is None for o in result.observations)


def test_ffuf_envelope_method_preserved():
    document = {
        "config": {"method": "POST"},
        "results": [{"url": "https://fixture.example/a", "status": 200}],
    }
    assert parse(json.dumps(document).encode(), "ffuf", "ffuf").observations[0].method == "POST"


def test_native_cross_engine_metadata_dedup(fixtures, configuration):
    from fuzzrank.pipeline import analyze
    from fuzzrank.scope import Scope

    records = []
    for filename in ["ffuf.json", "ferox.jsonl", "gobuster.txt"]:
        records += parse(
            (fixtures / filename).read_bytes(), filename, target="https://fixture.example"
        ).observations
    profile, rules = configuration
    report = analyze(records, [], Scope.load("https://fixture.example"), profile, rules)
    users = next(c for c in report.candidates if c.path == "/api/users")
    assert users.engines == ["feroxbuster", "ffuf", "gobuster"]
    assert len(users.observations) == 3
    assert report.summary["raw_discoveries"] == 9
    assert report.summary["out_of_scope"] == 1
    assert report.summary["duplicates_merged"] == 3
    assert report.summary["unique_candidates"] == 5


def test_jsonl_partial_line_survives(fixtures):
    data = (fixtures / "ferox.jsonl").read_bytes() + b'\n{"type":"response", invalid'
    result = parse(data, "partial.jsonl", "feroxbuster")
    assert len(result.observations) == 3
    assert result.rejected_records == 1


@pytest.mark.parametrize("data", [b'{"results": [', b'{"results":{}}', b"null", b"12"])
def test_malformed_ffuf_does_not_fake_results(data):
    with pytest.raises(ValueError):
        parse(data, "bad.json", "ffuf")


@pytest.mark.parametrize(
    "bad",
    [
        {"status_code": 999},
        {"status_code": True},
        {"status_code": "200"},
        {"url": "file:///etc/passwd"},
        {"url": "https://user:secret@fixture.example"},
        {"content_length": -1},
        {"headers": []},
        {"body_base64": "!bad!"},
        {"body": 123},
        {"truncated": "false"},
        {"method": "GET\r\nInjected"},
        {"timestamp": {}},
        {"engine": []},
        {"content_type": []},
    ],
)
def test_record_validation_reports_errors(bad):
    row = {"url": "https://fixture.example/a", "status_code": 200, **bad}
    data = json.dumps({"format": "fuzzrank-evidence-v1", "observations": [row]}).encode()
    result = parse(data, "invalid.json")
    assert result.rejected_records == 1
    assert result.observations == []
    assert result.warnings


def test_exact_binary_evidence_roundtrip():
    body = b"\x00\xff\x10\r\n"
    row = {
        "url": "https://fixture.example/a",
        "status_code": 200,
        "body_base64": base64.b64encode(body).decode(),
    }
    record = observation(row, engine="fixture", source="fixture", record=1)
    assert record.body == body


@pytest.mark.parametrize("timestamp", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_timestamp_is_rejected(timestamp):
    with pytest.raises(ValueError, match="finite"):
        observation(
            {"url": "https://fixture.example/a", "status_code": 200, "timestamp": timestamp},
            engine="fixture",
            source="fixture",
            record=1,
        )


def test_body_limit_rejects_without_truncating_evidence():
    row = {"url": "https://fixture.example/a", "status_code": 200, "body": "a" * (1024 * 1024 + 1)}
    with pytest.raises(ValueError, match="1 MiB"):
        observation(row, engine="fixture", source="fixture", record=1)


def test_gobuster_requires_target(fixtures):
    with pytest.raises(ValueError, match="--target"):
        parse((fixtures / "gobuster.txt").read_bytes(), "gobuster", "gobuster")


def test_gobuster_banners_are_not_misparsed():
    data = b"Gobuster version 3\n/admin (Status: 403) [Size: 82]\n"
    result = parse(data, "gobuster", "gobuster", "https://fixture.example")
    assert result.rejected_records == 1
    assert len(result.observations) == 1
