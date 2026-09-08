import base64
import copy
import hashlib
import json
from importlib.resources import files

import pytest
from jsonschema import Draft202012Validator, ValidationError

from fuzzrank.cli import prepare_output
from fuzzrank.doctor import version_details
from fuzzrank.pipeline import analyze
from fuzzrank.reporting import html_report, json_report
from fuzzrank.scope import Scope
from fuzzrank.service import Investigation


@pytest.fixture
def validator():
    schema = json.loads(files("fuzzrank").joinpath("schemas/report-v1.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_v1_serialization_contract_and_repeatability(fixtures, tmp_path, configuration, validator):
    output = prepare_output(tmp_path / "out")
    report = Investigation(output, *configuration).refresh([fixtures / "browser.har"], [])
    first, second = output / "one.json", output / "two.json"
    json_report.write(report, first)
    json_report.write(report, second)
    assert first.read_bytes() == second.read_bytes()
    document = json.loads(first.read_bytes())
    validator.validate(document)
    assert document == json_report.serializable(report)
    assert document["schema_version"] == 1 and document["schema_revision"] == "1.0.0"
    for candidate in document["candidates"]:
        assert sum(r["points"] for r in candidate["score_reasons"]) == candidate["score"]
        assert candidate["primary"] in candidate["observations"]
        if candidate["fingerprint"]:
            body = base64.b64decode(candidate["primary"]["body"]["data"])
            assert hashlib.sha256(body).hexdigest() == candidate["fingerprint"]["raw_sha256"]
    extended = copy.deepcopy(document)
    extended["future_field"] = {"allowed": True}
    validator.validate(extended)
    extended["candidates"][0]["score"] = 101
    with pytest.raises(ValidationError):
        validator.validate(extended)


def test_schema_accepts_partial_report_with_diagnostics(
    fixtures, tmp_path, configuration, validator
):
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    report = Investigation(prepare_output(tmp_path / "out"), *configuration).refresh(
        [fixtures / "ffuf.json", bad], []
    )
    assert report.partial
    validator.validate(json_report.serializable(report))


def test_html_filter_controls_and_cluster_provenance(make_observation, configuration, tmp_path):
    body = "Shared complete response body with enough words to be clustered safely."
    observations = [make_observation("/a", body), make_observation("/b", body)]
    report = analyze(observations, [], Scope.load("https://fixture.example"), *configuration)
    text = html_report.render(report)
    for control in ["search", "category", "status", "engine", "media", "cluster-filter", "noise"]:
        assert f'id="{control}"' in text
    assert 'data-suppressed="true"' in text and 'data-suppressed="false"' in text
    assert 'data-select-cluster="C-' in text and 'data-candidate="' in text
    assert "Evidence support:" in text and "Source / record" in text
    assert "Import diagnostics" in text and "Export metadata" in text
    output = tmp_path / "report.html"
    html_report.write(report, output)
    assert output.read_text(encoding="utf-8") == text
    for inline in [html_report.STYLE, html_report.SCRIPT]:
        digest = base64.b64encode(hashlib.sha256(inline.encode()).digest()).decode()
        assert f"sha256-{digest}" in text


def test_atomic_export_failure_preserves_previous_report(tmp_path):
    path = tmp_path / "report.json"
    path.write_bytes(b"previous completed report")

    def failing_stream():
        yield b"partial replacement"
        raise OSError("Simulated interrupted write")

    with pytest.raises(OSError):
        json_report.atomic_write_chunks(path, failing_stream())
    assert path.read_bytes() == b"previous completed report"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    "name,version",
    [
        ("ffuf", "2.1.0"),
        ("ffuf", "ffuf version: 2.1.0"),
        ("feroxbuster", "feroxbuster 2.13.1"),
        ("gobuster", "v3.8.2"),
    ],
)
def test_doctor_recognizes_version_family(name, version):
    details = version_details(name, version)
    assert details["version_check_ok"] and details["recognized_version_family"]


@pytest.mark.parametrize("version", ["", "not a version", "ERROR v2.1.0", "2.1\n0", "2.1\x1b"])
def test_doctor_malformed_version_is_diagnostic(version):
    details = version_details("ffuf", version)
    assert not details["version_check_ok"] and details["warning"]


def test_doctor_unknown_major_is_explicit():
    details = version_details("ffuf", "ffuf 99.0.0")
    assert details["version_check_ok"] and not details["recognized_version_family"]
    assert details["warning"]
