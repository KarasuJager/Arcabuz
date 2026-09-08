"""Regression checks for malformed exports and bounded offline imports."""

import json

import pytest

from fuzzrank.cli import main
from fuzzrank.engines import parse
from fuzzrank.engines.base import decode_json


@pytest.mark.parametrize(
    "data",
    [
        b'{"status":200,"status":403}',
        b'{"results":[{"url":"https://fixture.example/a","url":"https://fixture.example/b"}]}',
        b'{"headers":{"content-type":"text/html","content-type":"application/json"}}',
        b'{"config":{},"config":{"method":"POST"}}',
    ],
)
def test_duplicate_json_keys_are_not_silently_replaced(data):
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        decode_json(data)


@pytest.mark.parametrize("engine", ["ffuf", "feroxbuster"])
def test_jsonl_rejects_ambiguous_line_and_retains_good_lines(engine):
    row = {"url": "https://fixture.example/a", "status": 200, "length": 40}
    if engine == "feroxbuster":
        row.update(type="response", content_length=40)
    valid = json.dumps(row).encode()
    ambiguous = valid.replace(b'"status": 200', b'"status": 200,"status": 403')
    result = parse(valid + b"\n" + ambiguous + b"\n" + valid, "capture.jsonl", engine)
    assert len(result.observations) == 2
    assert result.rejected_records == 1
    assert all(item.status_code == 200 for item in result.observations)


def test_duplicate_keys_inside_captured_body_are_preserved():
    body = '{"item":1,"item":2}'
    document = {
        "format": "fuzzrank-evidence-v1",
        "observations": [{"url": "https://fixture.example/a", "status_code": 200, "body": body}],
    }
    result = parse(json.dumps(document).encode(), "capture.json")
    assert result.observations[0].body == body.encode()
    assert result.rejected_records == 0


def test_ambiguous_input_archived_and_other_inputs_survive(fixtures, tmp_path):
    path = tmp_path / "ambiguous.json"
    data = b'{"results":[],"results":[{"url":"https://fixture.example/a","status":200}]}'
    path.write_bytes(data)
    output = tmp_path / "analysis"
    assert (
        main(
            ["analyze", str(path), str(fixtures / "ffuf.json"), "--output", str(output), "--quiet"]
        )
        == 3
    )
    report = json.loads((output / "report.json").read_text())
    assert report["partial"] and report["summary"]["raw_discoveries"] == 3
    assert (output / report["sources"][0]["archive"]).read_bytes() == data


def test_combined_byte_limit_preserves_reports_and_all_sources(fixtures, tmp_path, monkeypatch):
    first = fixtures / "ffuf.json"
    second = fixtures / "ferox.jsonl"
    monkeypatch.setattr("fuzzrank.cli.MAX_TOTAL_INPUT_BYTES", first.stat().st_size)
    output = tmp_path / "limited"
    assert main(["analyze", str(first), str(second), "--output", str(output), "--quiet"]) == 3
    report = json.loads((output / "report.json").read_text())
    assert report["summary"]["raw_discoveries"] == 3
    assert report["partial"] and len(report["sources"]) == 2
    assert any("Combined input byte limit exceeded" in warning for warning in report["warnings"])
    assert (output / report["sources"][1]["archive"]).read_bytes() == second.read_bytes()
    assert (output / "report.html").exists()


def test_baselines_count_toward_combined_byte_limit(fixtures, tmp_path, write_bundle, monkeypatch):
    first = fixtures / "ffuf.json"
    baseline = write_bundle(
        "baseline.json",
        [{"url": "https://fixture.example/missing", "status_code": 404, "body": "Missing"}],
    )
    monkeypatch.setattr("fuzzrank.cli.MAX_TOTAL_INPUT_BYTES", first.stat().st_size)
    output = tmp_path / "limited"
    assert (
        main(
            ["analyze", str(first), "--baseline", str(baseline), "--output", str(output), "--quiet"]
        )
        == 3
    )
    report = json.loads((output / "report.json").read_text())
    assert report["baselines"] == []
    assert report["sources"][1]["role"] == "baseline"


def test_limit_before_any_valid_input_is_clean_error(fixtures, tmp_path, monkeypatch):
    monkeypatch.setattr("fuzzrank.cli.MAX_TOTAL_INPUT_BYTES", 1)
    output = tmp_path / "limited"
    assert main(["analyze", str(fixtures / "ffuf.json"), "--output", str(output), "--quiet"]) == 1
    assert (output / "sources.json").exists()
    assert not (output / "report.json").exists()
