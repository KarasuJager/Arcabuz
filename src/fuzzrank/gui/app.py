"""Optional desktop entry point; importing it does not make Qt a CLI requirement."""

import argparse
import os
import sys
from pathlib import Path

from fuzzrank import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="fuzzrank-gui", description="Native offline evidence triage"
    )
    parser.add_argument("--version", action="version", version=f"FuzzRank {__version__}")
    parser.add_argument("--demo", action="store_true", help="Open the built-in local demonstration")
    parser.add_argument("--open-report", type=Path, help="Open a saved FuzzRank JSON report")
    parser.add_argument("--settings", type=Path, help="Use a local preferences INI file")
    parser.add_argument("--output", type=Path, help="New investigation output directory for --demo")
    parser.add_argument(
        "--quit-after-load",
        action="store_true",
        help="Exit after a completed startup load (smoke tests)",
    )
    parser.add_argument(
        "--screenshot", type=Path, help="Save a window screenshot after startup load"
    )
    args = parser.parse_args(argv)
    if args.demo and args.open_report:
        parser.error("Choose either --demo or --open-report")
    if (args.quit_after_load or args.screenshot) and not (args.demo or args.open_report):
        parser.error("Startup load options require --demo or --open-report")
    try:
        from PySide6.QtCore import QSettings, QTimer
        from PySide6.QtWidgets import QApplication

        from fuzzrank.gui.window import MainWindow
    except ImportError:
        message = (
            "Desktop dependencies are unavailable. Install with: "
            'python -m pip install "fuzzrank[gui]"'
        )
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        elif os.name == "nt":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "FuzzRank", 0x10)
        return 1
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("FuzzRank")
    settings = QSettings(str(args.settings), QSettings.Format.IniFormat) if args.settings else None
    window = MainWindow(settings)
    window.show()
    startup_failed = False

    def loaded():
        nonlocal startup_failed
        if args.screenshot:
            try:
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(args.screenshot)):
                    raise OSError("Screenshot could not be written")
            except OSError:
                startup_failed = True
        if args.quit_after_load:
            window.close()

    if args.quit_after_load or args.screenshot:

        def finished():
            nonlocal startup_failed
            if window.last_error:
                startup_failed = True
                window.close()
            else:
                QTimer.singleShot(100, loaded)

        window.job_finished.connect(finished)
    if args.demo:
        QTimer.singleShot(0, lambda: window.open_demo(output=args.output))
    elif args.open_report:
        QTimer.singleShot(0, lambda: window.start_job("open", args.open_report.resolve()))
    code = app.exec()
    return 1 if startup_failed else code
