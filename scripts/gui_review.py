"""Capture native investigation views for local visual review; screenshots stay local."""

import argparse
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

from fuzzrank.gui.window import MainWindow
from fuzzrank.inputs import prepare_output


def review(report: Path, output: Path):
    output = prepare_output(output)
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(output / "preferences.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    window.show()
    failed = []

    def capture():
        try:
            assert not window.last_error, window.last_error
            for row, name in enumerate(
                ["summary", "candidates", "clusters", "suppressed", "baselines", "sources"]
            ):
                window.navigation.setCurrentRow(row)
                app.processEvents()
                assert window.grab().save(str(output / (name + ".png")))
            window.navigation.setCurrentRow(1)
            window.reset_filters()
            window.candidate_table.selectRow(0)
            window.settings.setValue("appearance", "light")
            window._apply_theme()
            app.processEvents()
            assert window.grab().save(str(output / "light.png"))
            window.settings.setValue("appearance", "dark")
            window._apply_theme()
            window.show_home()
            app.processEvents()
            assert window.grab().save(str(output / "home.png"))
        except Exception as exc:
            failed.append(str(exc))
        finally:
            window.close()

    window.job_finished.connect(lambda: QTimer.singleShot(100, capture))
    window.start_job("open", report.resolve())
    app.exec()
    if failed:
        raise RuntimeError(failed[0])
    print("Eight native views captured for local review")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review(args.report, args.output)
