import json
import shutil
import threading
from pathlib import Path

import pytest

from fuzzrank.cli import main, prepare_output
from fuzzrank.reporting import html_report
from fuzzrank.service import Investigation
from fuzzrank.watch import publish, watch


def replace_bundle(path: Path, suffix="one"):
    path.write_text(
        json.dumps(
            {
                "format": "fuzzrank-evidence-v1",
                "observations": [
                    {
                        "url": f"https://fixture.example/{suffix}",
                        "status_code": 200,
                        "body": "Synthetic complete response evidence with enough text "
                        "to fingerprint.",
                    }
                ],
            }
        )
    )


def test_watch_real_file_updates_partial_recovery_and_removal(tmp_path, configuration):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    file = incoming / "capture.json"
    replace_bundle(file)
    original = file.read_bytes()
    output = prepare_output(tmp_path / "out")
    service = Investigation(output, *configuration, target="https://fixture.example")
    results = []

    def updated(report, manifest):
        results.append(report)
        number = manifest["generation"]
        if number == 1:
            file.write_text('{"format":"fuzzrank-evidence-v1","observations":[')
        elif number == 2:
            replace_bundle(file, "two")
        elif number == 3:
            file.unlink()

    assert (
        watch(
            service, [incoming], [], interval=0.05, debounce=0.05, max_updates=4, on_report=updated
        )
        == 4
    )
    assert results[0].candidates[0].path == "/one"
    assert results[1].partial and results[1].candidates[0].path == "/one"
    assert any(s["status"] == "stale" for s in results[1].sources)
    assert any(s["status"] == "rejected" for s in results[1].sources)
    assert not results[2].partial and results[2].candidates[0].path == "/two"
    assert results[3].candidates == [] and results[3].sources[0]["status"] == "removed"
    for number in range(1, 5):
        generation = output / "generations" / f"{number:06d}"
        assert (generation / "report.json").exists() and (generation / "report.html").exists()
        assert (generation / "snapshot.json").exists()
    latest = json.loads((output / "latest.json").read_text())
    assert latest["generation"] == 4
    assert (output / results[0].sources[0]["archive"]).read_bytes() == original
    assert all(r.metadata["evidence_root"] == "../.." for r in results)


def test_watch_debounces_updates_and_does_not_refresh_unchanged(tmp_path, configuration):
    file = tmp_path / "capture.json"
    replace_bundle(file)
    service = Investigation(prepare_output(tmp_path / "out"), *configuration)
    stop = threading.Event()
    results, errors = [], []

    def writer():
        for name in ["one", "two", "three"]:
            replace_bundle(file, name)
            if stop.wait(0.07):
                return
        stop.wait(0.5)
        stop.set()

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        assert (
            watch(
                service,
                [file],
                [],
                interval=0.05,
                debounce=0.2,
                reports="none",
                stop=stop,
                on_report=lambda r, _: results.append(r),
                on_error=errors.append,
            )
            == 1
        )
    finally:
        stop.set()
        thread.join(timeout=2)
    assert not thread.is_alive() and not errors
    assert results[0].candidates[0].path == "/three"


def test_watch_baseline_updates_recompute_scores(tmp_path, configuration):
    file, baseline = tmp_path / "capture.json", tmp_path / "baseline.json"
    replace_bundle(file)
    baseline.write_text('{"format":"fuzzrank-evidence-v1","observations":[]}')
    service = Investigation(prepare_output(tmp_path / "out"), *configuration)
    outcomes = []

    def updated(report, _):
        outcomes.append(report.candidates[0].baseline)
        if len(outcomes) == 1:
            row = json.loads(file.read_text())["observations"][0]
            rows = [{**row, "url": f"https://fixture.example/missing-{i}"} for i in range(2)]
            baseline.write_text(
                json.dumps({"format": "fuzzrank-evidence-v1", "observations": rows})
            )

    watch(
        service,
        [file],
        [baseline],
        interval=0.05,
        debounce=0.05,
        max_updates=2,
        reports="json",
        on_report=updated,
    )
    assert outcomes == ["unavailable", "match"]


def test_watch_scope_does_not_drift_with_replacement(tmp_path, configuration):
    file = tmp_path / "capture.json"
    replace_bundle(file)
    service = Investigation(prepare_output(tmp_path / "out"), *configuration)
    reports = []

    def updated(report, _):
        reports.append(report)
        if len(reports) == 1:
            file.write_text(file.read_text().replace("fixture.example", "other.example"))

    watch(
        service,
        [file],
        [],
        interval=0.05,
        debounce=0.05,
        max_updates=2,
        reports="none",
        on_report=updated,
    )
    assert reports[1].target == "https://fixture.example/"
    assert not reports[1].candidates and len(reports[1].excluded) == 1


def test_watch_preserves_good_file_if_neighbor_malformed(fixtures, tmp_path, configuration):
    good, partial = tmp_path / "good.json", tmp_path / "partial.jsonl"
    shutil.copyfile(fixtures / "ffuf.json", good)
    partial.write_text('{"url":"https://fixture.example/extra","length":1,"status":200}\n{')
    service = Investigation(prepare_output(tmp_path / "out"), *configuration)
    reports = []
    watch(
        service,
        [good, partial],
        [],
        interval=0.05,
        debounce=0.05,
        max_updates=1,
        on_report=lambda r, _: reports.append(r),
    )
    assert reports[0].partial and reports[0].summary["raw_discoveries"] == 4
    assert reports[0].summary["rejected_records"] == 1


def test_failed_publish_does_not_replace_completed_pointer(tmp_path, configuration, monkeypatch):
    file = tmp_path / "capture.json"
    replace_bundle(file)
    output = prepare_output(tmp_path / "out")
    report = Investigation(output, *configuration).refresh([file], [])
    publish(report, output, 1)
    before = (output / "latest.json").read_bytes()

    def failed(*args):
        raise OSError("Simulated full disk")

    monkeypatch.setattr(html_report, "write", failed)
    with pytest.raises(OSError, match="full disk"):
        publish(report, output, 2)
    assert (output / "latest.json").read_bytes() == before
    assert (output / "generations/000001/report.html").exists()


@pytest.mark.parametrize("reports", ["both", "json", "html", "none"])
def test_watch_cli_report_selection(fixtures, tmp_path, reports):
    output = tmp_path / reports
    assert (
        main(
            [
                "watch",
                str(fixtures / "ffuf.json"),
                "--max-updates",
                "1",
                "--poll-interval",
                ".05",
                "--debounce",
                ".05",
                "--reports",
                reports,
                "--output",
                str(output),
                "--quiet",
            ]
        )
        == 0
    )
    generation = output / "generations/000001"
    assert (generation / "report.json").exists() == (reports in {"both", "json"})
    assert (generation / "report.html").exists() == (reports in {"both", "html"})
    assert (output / "latest.json").exists() and (output / "sources.json").exists()


def test_cli_watch_interrupt_returns_130_preserving_snapshot(fixtures, tmp_path, monkeypatch):
    actual_publish = publish

    def interrupted_after_publish(*args, **kwargs):
        actual_publish(*args, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr("fuzzrank.watch.publish", interrupted_after_publish)
    output = tmp_path / "out"
    assert (
        main(
            [
                "watch",
                str(fixtures / "ffuf.json"),
                "--output",
                str(output),
                "--debounce",
                ".05",
                "--poll-interval",
                ".05",
                "--quiet",
            ]
        )
        == 130
    )
    assert (output / "latest.json").exists()
    assert (output / "generations/000001/report.json").exists()


@pytest.mark.parametrize(
    "option,value",
    [
        ("interval", 0),
        ("debounce", 0),
        ("max_updates", 0),
        ("reports", "csv"),
    ],
)
def test_watch_invalid_controls(tmp_path, configuration, option, value):
    service = Investigation(prepare_output(tmp_path / "out"), *configuration)
    with pytest.raises(ValueError):
        watch(service, [], [], **{option: value})


def test_invalid_first_input_waits_and_reports_error_once(tmp_path, configuration):
    file = tmp_path / "capture.json"
    file.write_text("{")
    service = Investigation(prepare_output(tmp_path / "out"), *configuration)
    stop, errors = threading.Event(), []
    timer = threading.Timer(0.3, stop.set)
    timer.start()
    try:
        assert (
            watch(
                service, [file], [], interval=0.05, debounce=0.05, stop=stop, on_error=errors.append
            )
            == 0
        )
    finally:
        timer.cancel()
        timer.join()
    assert len(errors) == 1
