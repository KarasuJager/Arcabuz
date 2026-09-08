"""Drive a visible native Qt walkthrough and capture real windows for visual inspection.

This is not a pixel-diff test. Review the captured windows separately before claiming
visual approval. Only the owned demo and local fixture files are used.
"""

import argparse
import faulthandler
import json
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from fuzzrank.gui.window import MainWindow
from fuzzrank.gui.worker import AnalysisRequest
from fuzzrank.inputs import prepare_output
from fuzzrank.reporting.json_report import serializable


def review(output: Path):
    output = prepare_output(output)
    trace = (output / "trace.log").open("w")
    faulthandler.dump_traceback_later(90, file=trace)
    app = QApplication([])
    settings = QSettings(str(output / "preferences.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    window.resize(1280, 720)
    window.show()
    captures, operations, failures = [], [], []
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures"

    def capture(name):
        assert not window.last_error, window.last_error
        assert window.grab().save(str(output / (name + ".png")))
        metrics = {
            "name": name,
            "client_size": [window.width(), window.height()],
            "maximized": window.isMaximized(),
            "device_pixel_ratio": window.devicePixelRatioF(),
        }
        captures.append(metrics)
        for key, widget in {
            "sidebar": window.navigation,
            "toolbar": window.action_bar,
            "footer": window.statusBar(),
        }.items():
            assert widget.isVisible(), key
            assert window.rect().contains(
                widget.mapTo(window, QPoint(widget.width() - 1, widget.height() - 1))
            )
        if window.navigation.currentRow() in (1, 3) and window.root_stack.currentIndex() == 1:
            assert window.selected_candidate in window.view_data.report.candidates
            assert window.full_url.text() == window.selected_candidate.url
            metrics["candidate_viewport"] = [
                window.candidate_table.viewport().width(),
                window.candidate_table.viewport().height(),
            ]
            metrics["detail_height"] = window.details.height()
            metrics["horizontal_scroll_max"] = (
                window.candidate_table.horizontalScrollBar().maximum()
            )
            assert window.details.isVisible()
            assert window.candidate_table.viewport().height() >= 100, metrics
            assert metrics["horizontal_scroll_max"] == 0, metrics

    def walkthrough():
        yield lambda: window.isVisible()
        capture("01-home")
        window.open_demo(output=output / "demo")
        yield lambda: window.worker is None
        assert window.view_data.report.summary["raw_discoveries"] == 35
        assert window.view_data.report.summary["noise_suppressed"] == 22
        operations.append("Owned loopback demo loaded; 35 discoveries, 22 suppressed, 13 retained")
        expected = serializable(window.view_data.report)["candidates"]
        for width, height in [(1280, 720), (1366, 768), (1600, 900), (1920, 1080)]:
            window.resize(width, height)
            window.restore_split()
            yield lambda: True
            assert [window.width(), window.height()] == [width, height]
            capture(f"02-candidates-{width}x{height}")
        for cycle in range(3):
            window.showMaximized()
            yield window.isMaximized
            yield lambda: window.candidate_table.horizontalScrollBar().maximum() == 0
            capture(f"03-maximized-{cycle}")
            window.showNormal()
            window.resize(1366, 768)
            yield lambda: not window.isMaximized()
        capture("04-restored-after-resizes")
        window.search.setText("swagger")
        yield lambda: window.proxy.rowCount() == 1
        capture("05-filtered")
        window.reset_filters()
        window.candidate_table.selectRow(0)
        window.detail_tabs.setCurrentIndex(1)
        yield lambda: True
        capture("06-response-baseline")
        window.detail_tabs.setCurrentIndex(0)
        window.splitter.setSizes([240, 370])
        window.remember_split()
        yield lambda: True
        capture("07-score-explanations")
        operations.append(
            "Search, reset, top candidate metadata and unchanged score activations reviewed"
        )
        window.navigation.setCurrentRow(0)
        yield lambda: True
        capture("08-summary")
        window.navigation.setCurrentRow(2)
        yield lambda: True
        assert window.cluster_model.rows[0][2] == 20
        capture("09-clusters")
        members = next(
            button
            for button in window.findChildren(QPushButton)
            if button.text() == "Open selected cluster members"
        )
        QTest.mouseClick(members, Qt.MouseButton.LeftButton)
        yield lambda: window.navigation.currentRow() == 1
        assert window.proxy.rowCount() == 20
        capture("10-cluster-members")
        window.reset_filters()
        window.navigation.setCurrentRow(3)
        window.candidate_table.selectRow(0)
        yield lambda: True
        capture("11-suppressed")
        window.navigation.setCurrentRow(4)
        yield lambda: True
        capture("12-baselines")
        window.navigation.setCurrentRow(5)
        yield lambda: True
        capture("13-sources")
        operations.append(
            "Summary, largest cluster, open-members button, suppressed, baselines and sources"
        )
        window.settings.setValue("appearance", "light")
        window._apply_theme()
        window.navigation.setCurrentRow(1)
        window.candidate_table.selectRow(0)
        window.detail_tabs.setCurrentIndex(2)
        yield lambda: True
        capture("14-light-provenance")
        window.navigation.setCurrentRow(4)
        yield lambda: True
        capture("15-light-baselines")
        window.settings.setValue("appearance", "dark")
        window._apply_theme()
        window.navigation.setCurrentRow(1)
        window.detail_tabs.setCurrentIndex(0)
        window.export_report(output / "export.json", "json")
        yield lambda: window.worker is None
        assert json.loads((output / "export.json").read_text())["candidates"] == expected
        window.export_report(output / "export.html", "html")
        yield lambda: window.worker is None
        assert "Content-Security-Policy" in (output / "export.html").read_text(encoding="utf-8")
        window.start_job("open", output / "export.json")
        yield lambda: window.worker is None
        assert serializable(window.view_data.report)["candidates"] == expected
        capture("16-reopened-export")
        operations.append(
            "Light/dark switching; JSON and HTML export; JSON reopen with complete candidate parity"
        )
        incoming = output / "incoming"
        incoming.mkdir()
        (incoming / "ffuf.json").write_bytes((fixture / "ffuf.json").read_bytes())
        previous = window.view_data.report
        window.begin_analysis(
            AnalysisRequest(
                paths=[incoming], output=output / "watch", interval=0.05, debounce=0.05
            ),
            watching=True,
        )
        yield lambda: window.view_data.report is not previous
        capture("17-watching")
        previous = window.view_data.report
        (incoming / "browser.har").write_bytes((fixture / "browser.har").read_bytes())
        yield lambda: window.view_data.report is not previous
        assert window.view_data.report.summary["raw_discoveries"] == 8
        capture("18-watch-updated")
        window.stop_action.trigger()
        yield lambda: window.worker is None
        yield lambda: True  # Let viewport/scrollbar layout settle after the last model update.
        capture("19-watch-stopped")
        operations.append(
            "Watch start, stable fixture update 3 to 8 observations, stop via toolbar action"
        )

    iterator = walkthrough()
    condition, deadline = lambda: True, time.monotonic() + 45
    timer = QTimer()

    def tick():
        nonlocal condition, deadline
        try:
            if time.monotonic() > deadline:
                raise TimeoutError("Native walkthrough step did not complete")
            if not condition():
                return
            condition = next(iterator)
            deadline = time.monotonic() + 45
        except (StopIteration, Exception) as error:
            if not isinstance(error, StopIteration):
                failures.append(traceback.format_exc())
            timer.stop()
            available = app.primaryScreen().availableGeometry()
            result = {
                "captures": captures,
                "operations": operations,
                "failures": failures,
                "available_screen": [available.width(), available.height()],
            }
            (output / "review.json").write_text(json.dumps(result, indent=2))
            window.close()

    timer.timeout.connect(tick)
    timer.start(200)
    app.exec()
    faulthandler.cancel_dump_traceback_later()
    trace.close()
    if failures:
        raise RuntimeError(failures[0])
    print(
        f"Native walkthrough completed: {len(captures)} captures. Visual inspection still required."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review(args.output)
