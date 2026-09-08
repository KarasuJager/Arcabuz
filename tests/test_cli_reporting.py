import hashlib
import json
import socket
import subprocess
from io import StringIO

import pytest
from rich.console import Console

from fuzzrank.cli import main, prepare_output
from fuzzrank.doctor import inspect
from fuzzrank.pipeline import analyze
from fuzzrank.reporting.console import print_report, safe
from fuzzrank.reporting.html_report import render
from fuzzrank.reporting.json_report import serializable
from fuzzrank.scope import Scope


@pytest.mark.parametrize(
    "arguments", [["--help"], ["--version"], ["analyze", "--help"], ["demo", "--help"]]
)
def test_help_and_version(arguments):
    with pytest.raises(SystemExit) as result:
        main(arguments)
    assert result.value.code == 0


def test_cli_import_is_offline_and_archives_sources(fixtures, tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Offline analysis attempted a socket connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    output = tmp_path / "report"
    files = [fixtures / "ffuf.json", fixtures / "ferox.jsonl"]
    status = main(
        [
            "analyze",
            *map(str, files),
            "--target",
            "https://fixture.example",
            "--output",
            str(output),
            "--quiet",
        ]
    )
    assert status == 0
    report = json.loads((output / "report.json").read_text())
    assert report["summary"]["duplicates_merged"] == 1
    assert report["summary"]["requests_made"] == 0
    for source in report["sources"]:
        data = (output / source["archive"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == source["sha256"]
    assert (output / "report.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    assert all(c["score_reasons"] for c in report["candidates"])


def test_malformed_input_preserves_other_results(fixtures, tmp_path):
    malformed = tmp_path / "bad.json"
    malformed.write_text('{"results":[')
    output = tmp_path / "partial"
    status = main(
        ["analyze", str(malformed), str(fixtures / "ffuf.json"), "--output", str(output), "--quiet"]
    )
    assert status == 3
    report = json.loads((output / "report.json").read_text())
    assert report["partial"]
    assert report["summary"]["raw_discoveries"] == 3
    assert len(report["sources"]) == 2


def test_no_good_input_clean_error(tmp_path):
    malformed = tmp_path / "bad.json"
    malformed.write_text("not JSON")
    output = tmp_path / "bad-report"
    assert main(["analyze", str(malformed), "--output", str(output)]) == 1
    assert (output / "sources.json").exists()


def test_existing_output_not_overwritten(tmp_path):
    file = tmp_path / "important.txt"
    file.write_text("keep this")
    with pytest.raises(ValueError, match="not empty"):
        prepare_output(tmp_path)
    assert file.read_text() == "keep this"


def test_doctor_missing_engines_is_success(monkeypatch):
    monkeypatch.setattr("fuzzrank.doctor.shutil.which", lambda _: None)
    data = inspect()
    assert data["supported_runtime"]
    assert all(not value["installed"] for value in data["engines"].values())
    assert main(["doctor", "--json"]) == 0


def test_doctor_json_does_not_wrap_strings(monkeypatch, capsys):
    monkeypatch.setattr("fuzzrank.doctor.shutil.which", lambda _: None)
    monkeypatch.setattr(
        "fuzzrank.doctor.sys.executable", "C:/" + "long-directory/" * 30 + "python.exe"
    )
    assert main(["doctor", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["executable"]) > 300


def test_doctor_timeout_cleans_child(monkeypatch):
    class Child:
        returncode = None
        killed = False

        def communicate(self, timeout=None):
            if timeout:
                raise subprocess.TimeoutExpired("fixture", timeout)
            return b"", b""

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    children = []

    def create(*args, **kwargs):
        child = Child()
        children.append(child)
        return child

    monkeypatch.setattr("fuzzrank.doctor.shutil.which", lambda _: "/fixture/binary")
    monkeypatch.setattr("fuzzrank.doctor.subprocess.Popen", create)
    data = inspect()
    assert all(c.killed for c in children)
    assert all("warning" in value for value in data["engines"].values())


def test_html_escapes_untrusted_metadata(make_observation, configuration):
    profile, rules = configuration
    malicious = '</summary><script>alert(1)</script><img src="https://outside.example/pixel">'
    row = make_observation(
        "/admin",
        "<title>&lt;script&gt;evil&lt;/script&gt;</title>",
        content_type="text/html",
        location=malicious,
    )
    report = analyze([row], [], Scope.load("https://fixture.example"), profile, rules)
    document = render(report)
    assert malicious not in document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document
    assert "Content-Security-Policy" in document
    assert "connect-src &#x27;none&#x27;" in document
    assert document.count("<script>") == 1
    assert "<img" not in document
    assert "Scoring configuration" in document


def test_json_preserves_suppressed_evidence(make_observation, configuration):
    profile, rules = configuration
    body = "<html><p>This identical response is long enough to be clustered.</p></html>"
    rows = [make_observation("/a", body), make_observation("/b", body)]
    data = serializable(analyze(rows, [], Scope.load("https://fixture.example"), profile, rules))
    assert len(data["candidates"]) == 2
    suppressed = next(c for c in data["candidates"] if c["suppressed"])
    assert suppressed["observations"][0]["body"]["encoding"] == "base64"
    assert suppressed["fingerprint"]["raw_sha256"] == hashlib.sha256(body.encode()).hexdigest()


def test_terminal_strings_not_rich_markup(make_observation, configuration):
    profile, rules = configuration
    report = analyze(
        [make_observation("/[bold]admin")],
        [],
        Scope.load("https://fixture.example"),
        profile,
        rules,
    )
    stream = StringIO()
    print_report(report, Console(file=stream, width=140, color_system=None))
    assert "[bold]admin" in stream.getvalue()
    assert "\x1b" not in safe("hello\x1b[31m")
