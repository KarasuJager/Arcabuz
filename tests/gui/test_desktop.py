import json
import socket
import threading
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QModelIndex, QSettings, Qt, QTimer
from PySide6.QtWidgets import QDialogButtonBox, QLabel

from fuzzrank.cli import main
from fuzzrank.gui.dialogs import AnalysisDialog, SettingsDialog
from fuzzrank.gui.models import CANDIDATE_ROLE, CandidateFilter, CandidateModel
from fuzzrank.gui.presentation import plain, present
from fuzzrank.gui.worker import AnalysisRequest
from fuzzrank.pipeline import analyze
from fuzzrank.reporting.json_report import serializable
from fuzzrank.scope import Scope
from fuzzrank.service import Investigation


def test_gui_launch_home_actions_and_shortcuts(window):
    assert window.isVisible()
    assert window.root_stack.currentIndex() == 0
    assert len(window.home_buttons) == 6
    assert not window.navigation.isEnabled()
    assert window.open_action.shortcut().toString() == "Ctrl+O"
    assert window.export_action.shortcut().toString() == "Ctrl+E"
    assert not window.export_action.isEnabled()


def test_gui_demo_populates_all_views(window, qtbot, tmp_path):
    with qtbot.waitSignal(window.job_finished, timeout=30000):
        window.open_demo(output=tmp_path / "demo")
    assert not window.last_error
    report = window.view_data.report
    assert report.summary["raw_discoveries"] == 35
    assert report.summary["noise_suppressed"] == 22
    assert window.proxy.rowCount() == 13
    assert window.cluster_model.rowCount() == 13
    assert window.baseline_model.rowCount() == 12
    assert window.source_model.rowCount() == 1
    assert window.selected_candidate.path == "/admin/export"
    assert window.reason_model.rowCount() == len(window.selected_candidate.score_reasons)
    assert "baseline" in window.evidence_detail.toPlainText().lower()
    window.navigation.setCurrentRow(0)
    assert window.metrics["raw_discoveries"].text() == "35"
    window.navigation.setCurrentRow(3)
    assert window.proxy.rowCount() == 22
    assert window.noise_filter.isVisible()
    window.noise_filter.setCurrentIndex(window.noise_filter.findData("static"))
    assert window.proxy.rowCount() == 2
    window.navigation.setCurrentRow(2)
    row = next(i for i, row in enumerate(window.cluster_model.rows) if row[2] == 20)
    window.open_cluster(window.cluster_model.index(row, 0))
    assert window.proxy.rowCount() == 20
    assert "Includes suppressed" in window.match_count.text()
    window.navigation.setCurrentRow(4)
    assert "Two distinct" in window.baseline_note.text()
    assert len(window.baseline_model.rows[0][5]) == 64


@pytest.mark.parametrize("filename", ["ffuf.json", "ferox.jsonl", "browser.har", "gobuster.txt"])
def test_file_and_har_workflows(load_gui, fixtures, filename):
    report = load_gui([fixtures / filename], target="https://fixture.example")
    assert report.candidates and not report.partial
    assert report.summary["requests_made"] == 0
    assert all(c.score_reasons for c in report.candidates)


def test_directory_workflow_and_source_models(window, load_gui, fixtures):
    report = load_gui([fixtures], target="https://fixture.example")
    assert report.summary["raw_discoveries"] == 22
    assert report.summary["duplicates_merged"] == 14
    assert window.source_model.rowCount() == 8
    item = next(c for c in report.candidates if c.path == "/api/users")
    assert item.engines == ["feroxbuster", "ffuf", "gobuster", "har"]
    assert "unavailable" in window.baseline_note.text()


def test_import_configuration_detects_formats(qtbot, window, fixtures, tmp_path):
    dialog = AnalysisDialog(
        [fixtures / "ffuf.json", fixtures / "browser.har"], window.settings, parent=window
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.worker is None)
    assert {row[1] for row in dialog.source_model.rows} == {"ffuf", "har"}
    dialog.profile.setCurrentText("api")
    dialog.target.setText("https://fixture.example")
    dialog.output.setText(str(tmp_path / "configured"))
    request = dialog.request()
    assert request.profile == "api" and request.target == "https://fixture.example"
    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    dialog.close()


def test_gui_core_parity_calls_exact_investigation_service(
    load_gui, fixtures, tmp_path, monkeypatch
):
    calls = []
    original = Investigation.refresh

    def recorded(self, *args, **kwargs):
        calls.append(threading.current_thread().ident)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Investigation, "refresh", recorded)
    inputs = [fixtures / "ffuf.json", fixtures / "browser.har", fixtures / "ferox.jsonl"]
    output = tmp_path / "cli"
    assert (
        main(
            [
                "analyze",
                *map(str, inputs),
                "--profile",
                "api",
                "--target",
                "https://fixture.example",
                "--output",
                str(output),
                "--quiet",
            ]
        )
        == 0
    )
    gui = load_gui(inputs, profile="api", target="https://fixture.example")
    cli = json.loads((output / "report.json").read_text())
    assert serializable(gui)["candidates"] == cli["candidates"]
    assert gui.summary == cli["summary"] and gui.configuration == cli["configuration"]
    assert len(calls) == 2 and calls[0] != calls[1]


def test_candidate_sort_search_and_filters(window, load_gui, fixtures, qtbot):
    load_gui([fixtures], target="https://fixture.example")
    scores = [
        window.proxy.index(row, 0).data(CANDIDATE_ROLE).score
        for row in range(window.proxy.rowCount())
    ]
    assert scores == sorted(scores, reverse=True)
    window.candidate_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    scores = [
        window.proxy.index(row, 0).data(CANDIDATE_ROLE).score
        for row in range(window.proxy.rowCount())
    ]
    assert scores == sorted(scores)
    window.search.setText("swagger")
    qtbot.waitUntil(lambda: window.proxy.rowCount() == 1)
    window.reset_filters()
    window.status_filter.setCurrentIndex(window.status_filter.findData("403"))
    assert window.proxy.rowCount() == 1
    window.engine.setCurrentIndex(window.engine.findData("har"))
    assert window.proxy.rowCount() == 1
    window.media.setCurrentIndex(window.media.findData("application/json"))
    assert window.proxy.rowCount() == 0
    window.reset_filters()
    window.band.setCurrentIndex(window.band.findData("MEDIUM"))
    assert window.proxy.rowCount() == 3


def test_selection_exact_explanations_and_provenance(window, load_gui, fixtures):
    load_gui([fixtures], target="https://fixture.example")
    window.candidate_table.selectRow(0)
    candidate = window.selected_candidate
    assert window.full_url.text() == candidate.url
    assert sum(int(row[0]) for row in window.reason_model.rows) == candidate.score
    assert window.reason_model.rows == [
        (f"{r.points:+}", r.rule_id, r.reason) for r in candidate.score_reasons
    ]
    assert window.provenance_model.rowCount() == len(candidate.observations)
    window.select_candidate(QModelIndex())
    assert not window.full_url.text() and window.reason_model.rowCount() == 0


@pytest.mark.parametrize("kind", ["json", "html"])
def test_gui_export_same_v1_formats(window, load_gui, fixtures, qtbot, tmp_path, kind):
    report = load_gui([fixtures / "browser.har"])
    destination = tmp_path / ("export." + kind)
    with qtbot.waitSignal(window.job_finished):
        assert window.export_report(destination, kind)
    assert not window.last_error and destination.exists()
    if kind == "json":
        document = json.loads(destination.read_text())
        assert document["candidates"] == serializable(report)["candidates"]
        root = Path(document["metadata"]["evidence_root"])
        source = destination.parent / root / document["sources"][0]["archive"]
        assert source.read_bytes() == (fixtures / "browser.har").read_bytes()
    else:
        assert "Content-Security-Policy" in destination.read_text()
    assert "Exported:" in window.status.text()


def test_malformed_input_preserves_previous_view(window, load_gui, fixtures, tmp_path, qtbot):
    previous = load_gui([fixtures / "ffuf.json"])
    bad = tmp_path / "bad.har"
    bad.write_text('{"log":')
    with qtbot.waitSignal(window.job_finished):
        window.begin_analysis(AnalysisRequest(paths=[bad], output=tmp_path / "bad-output"))
    assert window.last_error and window.view_data.report is previous
    assert (tmp_path / "bad-output/sources.json").exists()


def test_partial_input_diagnostics_visible(window, load_gui, fixtures, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"results":[],"results":[]}')
    report = load_gui([bad, fixtures / "ffuf.json"])
    assert report.partial
    assert "PARTIAL" in window.investigation_meta.text()
    window.navigation.setCurrentRow(5)
    assert "bad.json" in window.diagnostics.toPlainText()
    assert "Unrecognized input" in window.diagnostics.toPlainText()
    assert any(s["status"] == "rejected" for s in report.sources)


def test_export_error_leaves_investigation(window, load_gui, fixtures, tmp_path, qtbot):
    report = load_gui([fixtures / "ffuf.json"])
    with qtbot.waitSignal(window.job_finished):
        window.export_report(tmp_path / "missing" / "report.json", "json")
    assert window.last_error and window.view_data.report is report


def test_analysis_cancellation_is_responsive_and_preserves_state(
    window, load_gui, fixtures, tmp_path, qtbot, monkeypatch
):
    previous = load_gui([fixtures / "ffuf.json"])
    entered, release = threading.Event(), threading.Event()
    original = Investigation.refresh

    def delayed(self, *args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Investigation, "refresh", delayed)
    heartbeat = []
    timer = QTimer()
    timer.timeout.connect(lambda: heartbeat.append(1))
    timer.start(10)
    window.begin_analysis(
        AnalysisRequest(paths=[fixtures / "browser.har"], output=tmp_path / "cancel")
    )
    qtbot.waitUntil(entered.is_set)
    window.stop_job()
    qtbot.waitUntil(lambda: len(heartbeat) >= 3)
    release.set()
    qtbot.waitUntil(lambda: window.worker is None)
    timer.stop()
    assert window.view_data.report is previous
    assert not (tmp_path / "cancel/report.json").exists()
    assert list((tmp_path / "cancel/evidence").iterdir())


def test_watch_gui_updates_and_stops(window, qtbot, fixtures, tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    source = incoming / "ffuf.json"
    source.write_bytes((fixtures / "ffuf.json").read_bytes())
    request = AnalysisRequest(
        paths=[incoming], output=tmp_path / "watch", interval=0.05, debounce=0.05
    )
    window.begin_analysis(request, watching=True)
    qtbot.waitUntil(lambda: window.view_data is not None, timeout=15000)
    assert "WATCHING:" in window.status.text()
    initial = window.view_data.report
    (incoming / "browser.har").write_bytes((fixtures / "browser.har").read_bytes())
    qtbot.waitUntil(lambda: window.view_data.report is not initial, timeout=15000)
    assert "browser.har" in window.view_data.changed
    assert window.view_data.report.summary["raw_discoveries"] == 8
    window.stop_job()
    qtbot.waitUntil(lambda: window.worker is None)
    assert (tmp_path / "watch/latest.json").exists()
    assert len(list((tmp_path / "watch/generations").iterdir())) >= 2


def test_saved_report_open_roundtrip(window, load_gui, fixtures, qtbot):
    original = load_gui([fixtures / "browser.har"])
    path = window.view_data.directory / "report.json"
    with qtbot.waitSignal(window.job_finished, timeout=30000):
        window.start_job("open", path)
    assert not window.last_error
    assert serializable(window.view_data.report) == serializable(original)


def test_native_widgets_do_not_interpret_evidence(
    window, make_observation, configuration, tmp_path
):
    malicious = '<img src="https://outside.example/pixel"><b>admin</b>'
    row = make_observation("/admin", malicious, location=malicious)
    report = analyze([row], [], Scope.load("https://fixture.example"), *configuration)
    window.accept_report(present(report, tmp_path))
    assert malicious in window.evidence_detail.toPlainText()
    assert all(
        item.textFormat() == Qt.TextFormat.PlainText
        for item in window.findChildren(QLabel)
        if item.objectName() in {"heading", "subtitle", "metricValue", "metricLabel"}
    )
    assert plain("abc\x1b\u202edef") == "abc  def"


def test_settings_are_local_validated_and_reused(window, qtbot):
    dialog = SettingsDialog(window.settings, window)
    qtbot.addWidget(dialog)
    dialog.appearance.setCurrentText("light")
    dialog.profile.setCurrentText("api")
    dialog.debounce.setValue(1.25)
    dialog.accept()
    settings = QSettings(window.settings.fileName(), QSettings.Format.IniFormat)
    assert settings.value("appearance") == "light"
    assert settings.value("profile") == "api"
    assert float(settings.value("debounce")) == 1.25
    assert not any("path" in key.lower() for key in settings.allKeys())
    window._apply_theme()
    assert not window.candidate_model.dark


def test_corrupt_preferences_fall_back(window):
    window.settings.setValue("debounce", "not a number")
    window.settings.setValue("profile", "unsupported")
    window.settings.setValue("appearance", "<b>dark</b>")
    window._sanitize_settings()
    assert window.settings.value("profile") == "generic"
    assert float(window.settings.value("debounce")) == 0.75


def test_gui_analysis_never_opens_network(load_gui, fixtures, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline GUI attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    report = load_gui([fixtures / "browser.har"])
    assert report.summary["requests_made"] == 0


def test_models_handle_empty_and_invalid_indices():
    model = CandidateModel()
    proxy = CandidateFilter()
    proxy.setSourceModel(model)
    assert model.rowCount() == 0 and proxy.rowCount() == 0
    assert model.data(QModelIndex()) is None
