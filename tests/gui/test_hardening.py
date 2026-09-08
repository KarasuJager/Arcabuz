from hashlib import sha256
from importlib.resources import files
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QPushButton

from fuzzrank.gui import brand
from fuzzrank.gui.models import RAW_ROLE, RowsModel
from fuzzrank.gui.presentation import compact, tooltip
from fuzzrank.gui.widgets import ElidingLabel, EvidenceTable


@pytest.mark.parametrize("size", [(1280, 640), (1280, 720), (1366, 768), (1600, 900), (1920, 1080)])
@pytest.mark.parametrize("appearance", ["dark", "light"])
def test_desktop_sizes_keep_chrome_panels_and_columns_usable(
    window, load_gui, fixtures, qtbot, size, appearance
):
    load_gui([fixtures], target="https://fixture.example")
    window.settings.setValue("appearance", appearance)
    window._apply_theme()
    window.resize(*size)
    qtbot.waitUntil(lambda: window.size() == QSize(*size))
    for view, table in [
        (1, window.candidate_table),
        (2, window.cluster_table),
        (3, window.candidate_table),
        (4, window.baseline_table),
        (5, window.source_table),
    ]:
        window.navigation.setCurrentRow(view)
        qtbot.waitUntil(
            lambda t=table: (
                t.horizontalScrollBar().maximum() == 0
                and t.viewport().height() >= 100
                and abs(
                    sum(
                        t.columnWidth(c)
                        for c in range(t.model().columnCount())
                        if not t.isColumnHidden(c)
                    )
                    - t.viewport().width()
                )
                <= 2
            )
        )
        assert table.viewport().height() >= 100
        visible_width = sum(
            table.columnWidth(c)
            for c in range(table.model().columnCount())
            if not table.isColumnHidden(c)
        )
        assert abs(visible_width - table.viewport().width()) <= 2
        for widget in [window.action_bar, window.navigation, window.statusBar(), table]:
            assert widget.isVisible()
            corner = widget.mapTo(window, QPoint(widget.width() - 1, widget.height() - 1))
            assert window.rect().contains(corner)
        if view in (1, 3):
            assert window.details.isVisible() and window.details.height() >= 210
            window.detail_tabs.setCurrentIndex(2)
            qtbot.waitUntil(lambda: window.provenance_table.horizontalScrollBar().maximum() == 0)
            window.detail_tabs.setCurrentIndex(0)
    window.navigation.setCurrentRow(0)
    assert not window.details.isVisible()
    assert (
        window.metrics["raw_discoveries"].height()
        >= window.metrics["raw_discoveries"].fontMetrics().height()
    )


def test_splitter_preserves_user_ratio_through_navigation_and_resizes(
    window, load_gui, fixtures, qtbot
):
    load_gui([fixtures / "ffuf.json"])
    window.resize(1366, 768)
    qtbot.waitUntil(lambda: window.splitter.height() > 300)
    window.splitter.setSizes([300, 260])
    window.remember_split()
    desired = window._split_ratio
    for width, height in [(1920, 1080), (1280, 720), (1600, 900), (1366, 768)]:
        window.navigation.setCurrentRow(2)
        window.resize(width, height)
        window.navigation.setCurrentRow(1)
        qtbot.waitUntil(
            lambda: abs(window.splitter.sizes()[0] / sum(window.splitter.sizes()) - desired) < 0.04
        )
    window.showMaximized()
    qtbot.waitUntil(window.isMaximized)
    window.showNormal()
    window.resize(1366, 768)
    qtbot.waitUntil(lambda: window.size() == QSize(1366, 768))
    assert window.navigation.isVisible() and window.details.isVisible()


def test_columns_can_be_shown_copied_and_returned_to_fit(window, load_gui, fixtures, qtbot):
    load_gui([fixtures / "ffuf.json"])
    table = window.candidate_table
    assert table.isColumnHidden(8)
    table.toggle_column(8, True)
    index = window.proxy.index(0, 8)
    table.setCurrentIndex(index)
    table.copy_cell()
    assert QApplication.clipboard().text() == index.data(RAW_ROLE)
    assert len(index.data()) < len(index.data(RAW_ROLE))
    assert index.data(RAW_ROLE) in index.data(Qt.ItemDataRole.ToolTipRole)
    table.toggle_column(8, False)
    qtbot.waitUntil(lambda: table.horizontalScrollBar().maximum() == 0)
    table.copy_row()
    assert index.data(RAW_ROLE) in QApplication.clipboard().text()
    table.show_row()
    dialog = table.findChild(QDialog)
    assert index.data(RAW_ROLE) in dialog.findChild(QPlainTextEdit).toPlainText()
    dialog.close()


def test_manual_column_resize_remains_respected_until_fit(window, load_gui, fixtures, qtbot):
    load_gui([fixtures / "ffuf.json"])
    table = window.candidate_table
    header = table.horizontalHeader()
    edge = header.sectionViewportPosition(4) + header.sectionSize(4) - 1
    qtbot.mousePress(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(edge, 10))
    qtbot.mouseMove(header.viewport(), QPoint(edge + 60, 10))
    qtbot.mouseRelease(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(edge + 60, 10))
    assert not table._automatic
    chosen = table.columnWidth(4)
    window.resize(1600, 900)
    qtbot.waitUntil(lambda: window.width() == 1600)
    assert table.columnWidth(4) == chosen
    table.reset_widths()
    qtbot.waitUntil(lambda: table.horizontalScrollBar().maximum() == 0)


def test_compact_values_keep_safe_full_tooltips_and_copy(qtbot):
    malicious = '<img src="https://outside.example/pixel">&value'
    digest = "0123456789abcdef" * 4
    timestamp = "2026-09-09T00:00:12.123456+02:00"
    model = RowsModel(
        ("Hash", "Type", "Captured", "Evidence"),
        [(digest, "application/json; charset=utf-8", timestamp, malicious)],
        formats={0: "hash", 1: "media", 2: "time"},
    )
    table = EvidenceTable(model)
    qtbot.addWidget(table)
    assert model.index(0, 0).data() == "01234567…abcdef"
    assert model.index(0, 1).data() == "application/json"
    assert model.index(0, 2).data() == "2026-09-09 00:00:12"
    assert "&lt;img" in model.index(0, 3).data(Qt.ItemDataRole.ToolTipRole)
    assert "<img src=" not in tooltip(malicious)
    table.setCurrentIndex(model.index(0, 3))
    table.copy_cell()
    assert QApplication.clipboard().text() == malicious
    assert "View full row" in tooltip("x" * 10000)
    assert compact("Unknown", "id") == "Unknown"
    assert compact("captures/session/ffuf.json", "filename") == "ffuf.json"
    assert compact(r"captures\session\browser.har", "filename") == "browser.har"


def test_dynamic_long_labels_do_not_change_window_constraints(window, load_gui, fixtures, qtbot):
    load_gui([fixtures / "ffuf.json"])
    window.resize(1280, 720)
    text = "https://fixture.example/" + "long-evidence-" * 2000
    for widget in [window.investigation_title, window.detail_title, window.status]:
        widget.setText(text)
        assert widget.text() == text
    window.engine.addItem("e" * 2000, "e" * 2000)
    window.media.addItem("x" * 2000, "x" * 2000)
    qtbot.waitUntil(lambda: window.size() == QSize(1280, 720))
    assert window.candidate_table.viewport().height() >= 100
    window.status.clear()
    assert window.status.text() == ""
    assert isinstance(window.status, ElidingLabel)


def test_logo_resource_is_approved_original_and_native_icon_loads(window, monkeypatch, qtbot):
    original = Path(__file__).parents[2] / "docs/assets/fuzzrank-logo.png"
    packaged = files("fuzzrank.gui").joinpath("assets/fuzzrank-logo.png").read_bytes()
    assert sha256(packaged).digest() == sha256(original.read_bytes()).digest()
    assert not window.windowIcon().isNull()
    assert not brand.artwork().isNull() and not brand.mark().isNull()
    monkeypatch.setattr(brand, "artwork", QPixmap)
    assert brand.icon().isNull()
    badge = brand.badge()
    qtbot.addWidget(badge)
    assert badge.text() == "FR"


def test_labels_and_capped_score_display_do_not_duplicate_activations(window, qtbot, tmp_path):
    with qtbot.waitSignal(window.job_finished, timeout=30000):
        window.open_demo(output=tmp_path / "demo")
    candidate = window.selected_candidate
    assert candidate.score == 100
    assert len({r.rule_id for r in candidate.score_reasons}) == len(candidate.score_reasons)
    assert sum(int(row[0]) for row in window.reason_model.rows) == candidate.score
    assert "Rule total +110; limited to 100 / 100" in window.score_note.text()
    assert window.detail_tabs.tabText(1) == "Response / baseline"
    assert "Requests made by FuzzRank: 47" in window.summary_notes.toPlainText()
    window.navigation.setCurrentRow(2)
    assert window.cluster_model.rows[0][2] == 20
    assert "Probable wildcard/custom-404 response" in window.cluster_detail.toPlainText()
    assert "20 endpoints" in window.cluster_detail.toPlainText()


def test_cluster_members_button_and_double_click(window, load_gui, fixtures, qtbot):
    load_gui([fixtures / "ffuf.json"])
    for via_button in (True, False):
        window.navigation.setCurrentRow(2)
        index = window.cluster_model.index(0, 3)
        window.cluster_table.setCurrentIndex(index)
        expected = window.cluster_model.rows[0][0]
        if via_button:
            button = next(
                b
                for b in window.findChildren(QPushButton)
                if b.text() == "Open selected cluster members"
            )
            qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        else:
            point = window.cluster_table.visualRect(index).center()
            qtbot.mouseClick(window.cluster_table.viewport(), Qt.MouseButton.LeftButton, pos=point)
            qtbot.mouseDClick(window.cluster_table.viewport(), Qt.MouseButton.LeftButton, pos=point)
        qtbot.waitUntil(lambda: window.navigation.currentRow() == 1)
        assert window.cluster_filter.text() == expected
        assert window.proxy.rowCount() > 0


def test_columns_menu_syncs_after_another_menu_changes_visibility(window, load_gui, fixtures):
    load_gui([fixtures / "ffuf.json"])
    menu = window.columns_button.menu()
    action = menu.actions()[8]
    assert not action.isChecked()
    window.candidate_table.toggle_column(8, True)
    menu.aboutToShow.emit()
    assert action.isChecked()


def test_report_refresh_replaces_stale_details_and_preserves_current_identity(
    window, load_gui, fixtures, qtbot, tmp_path
):
    with qtbot.waitSignal(window.job_finished, timeout=30000):
        window.open_demo(output=tmp_path / "demo")
    old = window.selected_candidate
    report = load_gui([fixtures / "ffuf.json"])
    assert window.selected_candidate in report.candidates
    assert window.selected_candidate.id != old.id
    assert window.full_url.text() == window.selected_candidate.url
    identity = window.selected_candidate.id
    report = load_gui([fixtures / "ffuf.json", fixtures / "browser.har"])
    assert window.selected_candidate.id == identity
    assert any(window.selected_candidate is c for c in report.candidates)
    assert window.reason_model.rows == [
        (f"{r.points:+}", r.rule_id, r.reason) for r in window.selected_candidate.score_reasons
    ]
    window.search.setText("no-such-visible-result")
    window.apply_filters()
    report = load_gui([fixtures / "ffuf.json"])
    assert window.proxy.rowCount() == 0
    assert window.selected_candidate is None
    assert window.full_url.text() == "" and window.reason_model.rowCount() == 0
