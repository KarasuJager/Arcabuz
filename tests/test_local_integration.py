import json
import socket

from fuzzrank.cli import main
from fuzzrank.demo import ROUTES, collect_demo


def test_local_http_end_to_end(tmp_path, monkeypatch):
    original_connect = socket.socket.connect
    connections = []

    def local_only(sock, address):
        assert address[0] == "127.0.0.1"
        connections.append(address)
        return original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local_only)
    output = tmp_path / "demo"
    assert main(["demo", "--output", str(output), "--quiet"]) == 0
    report = json.loads((output / "report.json").read_text())
    assert report["summary"]["requests_made"] == len(ROUTES) + 12 == 47
    assert len(connections) == 47
    assert report["summary"]["raw_discoveries"] == 35
    assert report["summary"]["noise_suppressed"] == 22
    assert report["summary"]["unique_candidates"] == 13
    candidates = {c["path"]: c for c in report["candidates"]}
    assert candidates["/swagger.json"]["score"] >= 90
    assert candidates["/admin/export"]["score"] >= 90
    assert candidates["/api/users"]["score"] > candidates["/assets/app.js"]["score"]
    assert candidates["/admin"]["score"] > candidates["/missing-0"]["score"]
    assert candidates["/missing-0"]["baseline"] == "match"
    assert candidates["/normal/missing"]["baseline"] == "match"
    assert candidates["/wild/one"]["baseline"] == "match"
    assert candidates["/spa/one"]["baseline"] == "match"
    assert candidates["/redirect"]["primary"]["status_code"] == 302
    assert candidates["/redirect"]["signals"]["external_redirect"]
    assert len({address for address in connections}) == 1
    assert all(
        sum(r["points"] for r in c["score_reasons"]) == c["score"] for c in report["candidates"]
    )
    assert (output / "report.html").stat().st_size > 10000
    # Closed fixture must be shut down after the command returns.
    with socket.socket() as sock:
        assert sock.connect_ex(connections[0]) != 0
    # Reanalysis of the exact captures must preserve all scores and suppression decisions.
    again = tmp_path / "again"
    assert (
        main(
            [
                "analyze",
                str(output / "demo-evidence.json"),
                "--baseline",
                str(output / "demo-baseline.json"),
                "--output",
                str(again),
                "--quiet",
            ]
        )
        == 0
    )
    imported = json.loads((again / "report.json").read_text())
    assert [(c["id"], c["score"], c["suppressed"]) for c in imported["candidates"]] == [
        (c["id"], c["score"], c["suppressed"]) for c in report["candidates"]
    ]


def test_request_budget_counts_baselines(tmp_path):
    output = tmp_path / "limited"
    assert main(["demo", "--max-requests", "15", "--output", str(output), "--quiet"]) == 3
    report = json.loads((output / "report.json").read_text())
    assert report["partial"]
    assert report["summary"]["requests_made"] == 15
    assert report["summary"]["raw_discoveries"] == 3
    assert len(report["baselines"]) == 12


def test_interruption_preserves_completed_responses(tmp_path, monkeypatch):
    from fuzzrank import demo

    actual = demo._request

    def interrupted(server, path, number):
        if number == 15:
            raise KeyboardInterrupt
        return actual(server, path, number)

    monkeypatch.setattr(demo, "_request", interrupted)
    _, observations, baselines, warnings, partial, _ = collect_demo(tmp_path)
    assert partial and len(observations) == 2 and len(baselines) == 12
    assert any("Interrupted" in text for text in warnings)
    assert len(json.loads((tmp_path / "demo-evidence.json").read_text())["observations"]) == 2


def test_connection_error_preserves_completed_responses(tmp_path, monkeypatch):
    from fuzzrank import demo

    actual = demo._request

    def failed(server, path, number):
        if number == 14:
            raise OSError("fixture connection error")
        return actual(server, path, number)

    monkeypatch.setattr(demo, "_request", failed)
    _, observations, _, warnings, partial, requests = collect_demo(tmp_path)
    assert partial and requests == 47 and len(observations) == 34
    assert any("connection error" in text for text in warnings)
