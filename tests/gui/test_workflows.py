import json
import threading

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QDialogButtonBox, QFileDialog, QMessageBox

from fuzzrank.gui.worker import AnalysisRequest
from fuzzrank.inputs import InputLimits
from fuzzrank.service import Investigation


def test_home_to_file_dialog_to_analysis(window, qtbot, fixtures, tmp_path, monkeypatch):
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *a: ([str(fixtures / "browser.har"), str(fixtures / "ffuf.json")], ""),
    )
    qtbot.mouseClick(window.home_buttons["Analyze files"], Qt.MouseButton.LeftButton)
    assert len(window.dialogs) == 1
    dialog = window.dialogs[0]
    qtbot.waitUntil(lambda: dialog.worker is None)
    dialog.output.setText(str(tmp_path / "wizard"))
    with qtbot.waitSignal(window.job_finished, timeout=15000):
        qtbot.mouseClick(
            dialog.buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton
        )
    assert not window.last_error
    assert window.view_data.report.summary["raw_discoveries"] == 8
    assert not window.dialogs


def test_drag_local_paths_and_reject_remote_urls(window, fixtures, qtbot):
    mime = QMimeData()
    mime.setUrls([QUrl("https://outside.example/capture.har")])
    remote = QDragEnterEvent(
        QPoint(20, 20),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dragEnterEvent(remote)
    assert not remote.isAccepted()
    mime.setUrls([QUrl.fromLocalFile(str(fixtures / "browser.har"))])
    local = QDragEnterEvent(
        QPoint(20, 20),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dragEnterEvent(local)
    assert local.isAccepted()
    drop = QDropEvent(
        QPointF(20, 20),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(drop)
    assert drop.isAccepted() and len(window.dialogs) == 1
    dialog = window.dialogs[0]
    dialog.reject()
    qtbot.waitUntil(lambda: not window.dialogs)


def test_gui_explicit_baseline_and_scope(load_gui, window, write_bundle):
    body = "Shared custom missing response containing enough words for trustworthy comparison."
    source = write_bundle(
        "input.json",
        [
            {"url": "https://fixture.example/admin", "status_code": 200, "body": body},
            {"url": "https://outside.example/admin", "status_code": 403},
        ],
    )
    baseline = write_bundle(
        "baseline.json",
        [
            {"url": f"https://fixture.example/missing-{i}", "status_code": 200, "body": body}
            for i in range(2)
        ],
    )
    report = load_gui([source], baselines=[baseline], target="https://fixture.example")
    assert report.summary["out_of_scope"] == 1
    assert report.candidates[0].baseline == "match"
    assert window.baseline_model.rowCount() == 2
    assert any(s["role"] == "baseline" for s in report.sources)


@pytest.mark.parametrize("kind", ["limit", "scope", "profile", "missing"])
def test_configuration_errors_are_user_visible(window, qtbot, fixtures, tmp_path, kind):
    request = AnalysisRequest(paths=[fixtures / "ffuf.json"], output=tmp_path / "output")
    if kind == "limit":
        request.limits = InputLimits(file_bytes=10)
    elif kind == "scope":
        request.target = "file:///private"
    elif kind == "profile":
        request.profile = "nonexistent-profile"
    else:
        request.paths = [tmp_path / "missing"]
    with qtbot.waitSignal(window.job_finished):
        window.begin_analysis(request)
    assert window.last_error and not window.view_data
    boxes = window.findChildren(QMessageBox)
    assert boxes and all(b.textFormat() == Qt.TextFormat.PlainText for b in boxes)


def test_corrupt_report_error_retains_old_view(window, load_gui, fixtures, qtbot, tmp_path):
    report = load_gui([fixtures / "ffuf.json"])
    broken = tmp_path / "broken.json"
    broken.write_text('{"format":"fuzzrank-report","schema_version":99}')
    with qtbot.waitSignal(window.job_finished):
        window.start_job("open", broken)
    assert "Invalid saved report" in window.last_error
    assert window.view_data.report is report


def test_close_during_analysis_waits_for_safe_worker_exit(
    window, qtbot, fixtures, tmp_path, monkeypatch
):
    entered, release = threading.Event(), threading.Event()
    original = Investigation.refresh

    def delayed(self, *a, **k):
        entered.set()
        assert release.wait(5)
        return original(self, *a, **k)

    monkeypatch.setattr(Investigation, "refresh", delayed)
    window.begin_analysis(
        AnalysisRequest(paths=[fixtures / "ffuf.json"], output=tmp_path / "close")
    )
    qtbot.waitUntil(entered.is_set)
    window.close()
    assert window.isVisible() and window.worker.stop_event.is_set()
    release.set()
    qtbot.waitUntil(lambda: window.worker is None and not window.isVisible())
    assert not (tmp_path / "close/report.json").exists()


def test_watch_partial_update_retains_last_good_and_recovers(window, qtbot, fixtures, tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    source = incoming / "ffuf.json"
    data = (fixtures / "ffuf.json").read_bytes()
    source.write_bytes(data)
    window.begin_analysis(
        AnalysisRequest(paths=[incoming], output=tmp_path / "watch", debounce=0.05, interval=0.05),
        watching=True,
    )
    qtbot.waitUntil(lambda: window.view_data is not None, timeout=15000)
    initial = window.view_data.report
    source.write_text('{"results":')
    qtbot.waitUntil(lambda: window.view_data.report is not initial, timeout=15000)
    assert window.view_data.report.partial
    assert window.view_data.report.summary["raw_discoveries"] == 3
    source.write_bytes(data)
    qtbot.waitUntil(lambda: not window.view_data.report.partial, timeout=15000)
    window.stop_job()
    qtbot.waitUntil(lambda: window.worker is None)
    assert (tmp_path / "watch/latest.json").exists()


def test_sort_preserves_selection_and_core_order(window, load_gui, fixtures):
    report = load_gui([fixtures], target="https://fixture.example")
    selected = window.selected_candidate.id
    original = [c.id for c in report.candidates]
    window.candidate_table.sortByColumn(4, Qt.SortOrder.DescendingOrder)
    assert window.selected_candidate.id == selected
    assert [c.id for c in report.candidates] == original


def test_twenty_thousand_native_rows(window, load_gui, tmp_path):
    source = tmp_path / "large.jsonl"
    with source.open("w") as stream:
        for i in range(20000):
            stream.write(
                json.dumps(
                    {
                        "type": "response",
                        "status": 200,
                        "url": f"https://fixture.example/item-{i:06d}",
                    }
                )
                + "\n"
            )
    report = load_gui([source])
    assert len(report.candidates) == window.proxy.rowCount() == 20000
    window.proxy.configure(text="item-019999")
    assert window.proxy.rowCount() == 1
    window.proxy.configure(text="")
    window.candidate_table.sortByColumn(4, Qt.SortOrder.DescendingOrder)
    assert window.proxy.index(0, 4).data() == "/item-019999"
    window.candidate_table.selectRow(19999)
    assert window.reason_model.rowCount()
