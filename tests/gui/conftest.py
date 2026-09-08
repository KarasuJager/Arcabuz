import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def window(qtbot, tmp_path):
    from PySide6.QtCore import QSettings

    from fuzzrank.gui.window import MainWindow

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = MainWindow(settings)
    qtbot.addWidget(widget)
    widget.show()
    yield widget
    if widget.worker:
        widget.stop_job()
        qtbot.waitUntil(lambda: widget.worker is None, timeout=30000)
    widget.close()


@pytest.fixture
def load_gui(window, qtbot, tmp_path):
    from fuzzrank.gui.worker import AnalysisRequest

    serial = 0

    def load(paths, **kwargs):
        nonlocal serial
        serial += 1
        request = AnalysisRequest(paths=paths, output=tmp_path / f"gui-{serial}", **kwargs)
        with qtbot.waitSignal(window.job_finished, timeout=30000):
            assert window.begin_analysis(request)
        assert not window.last_error, window.last_error
        return window.view_data.report

    return load
