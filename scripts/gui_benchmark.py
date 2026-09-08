"""Exercise a real native GUI with 20,000 retained rows; no network or fuzzer execution."""

import argparse
import json
import time
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from fuzzrank.gui.window import MainWindow
from fuzzrank.gui.worker import AnalysisRequest
from fuzzrank.inputs import prepare_output


def run(count: int, output: Path) -> dict:
    output = prepare_output(output)
    source = output / "synthetic.jsonl"
    with source.open("w", encoding="utf-8") as stream:
        for index in range(count):
            stream.write(
                json.dumps(
                    {
                        "type": "response",
                        "method": "GET",
                        "url": f"https://fixture.example/api/item-{index:06d}",
                        "status": 403 if index % 2 else 200,
                        "content_type": "application/json",
                        "content_length": index + 100,
                    }
                )
                + "\n"
            )
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(output / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    window.show()
    ticks, measurement = [], {}
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
    timer.start(20)
    started = time.perf_counter()

    def complete():
        timer.stop()
        try:
            assert not window.last_error, window.last_error
            assert window.proxy.rowCount() == count
            assert window.view_data.report.summary["raw_discoveries"] == count
            loaded = time.perf_counter()
            window.proxy.configure(text="item-000099")
            assert window.proxy.rowCount() == 1
            searched = time.perf_counter()
            window.proxy.configure(text="", status="403")
            assert window.proxy.rowCount() == count // 2
            filtered = time.perf_counter()
            window.proxy.configure(status="")
            window.candidate_table.sortByColumn(7, Qt.SortOrder.DescendingOrder)
            assert window.proxy.index(0, 7).data() == str(count + 99)
            sorted_at = time.perf_counter()
            window.candidate_table.selectRow(count - 1)
            assert window.selected_candidate and window.reason_model.rowCount()
            selected = time.perf_counter()
            widget_count = len(window.findChildren(QWidget))
            assert widget_count < 500
            assert len(ticks) > 5
            app.processEvents()
            window.grab().save(str(output / "gui.png"))
            measurement.update(
                {
                    "observations": count,
                    "retained_rows": count,
                    "analysis_reports_and_display_seconds": round(loaded - started, 3),
                    "search_seconds": round(searched - loaded, 3),
                    "status_filter_seconds": round(filtered - searched, 3),
                    "sort_seconds": round(sorted_at - filtered, 3),
                    "selection_seconds": round(selected - sorted_at, 3),
                    "event_loop_ticks_during_analysis": len(ticks),
                    "max_event_loop_gap_seconds": round(
                        max(
                            b - a for a, b in zip([started, *ticks], [*ticks, loaded], strict=True)
                        ),
                        3,
                    ),
                    "native_widget_count": widget_count,
                    "summary": window.view_data.report.summary,
                }
            )
            (output / "measurement.json").write_text(json.dumps(measurement, indent=2))
        except Exception as exc:
            measurement["error"] = repr(exc)
        finally:
            window.close()

    window.job_finished.connect(complete)
    window.begin_analysis(AnalysisRequest(paths=[source], output=output / "investigation"))
    app.exec()
    if "error" in measurement:
        raise RuntimeError(measurement["error"])
    return measurement


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=20000, choices=range(100, 100001, 2))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.records, args.output), indent=2))
