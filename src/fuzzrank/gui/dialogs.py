"""Native import configuration and lightweight local preferences."""

from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fuzzrank.gui.models import RowsModel
from fuzzrank.gui.worker import AnalysisRequest, Worker
from fuzzrank.inputs import InputLimits


def label(text, name=""):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setWordWrap(True)
    if name:
        item.setObjectName(name)
    return item


def path_row(edit, choose):
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    button = QPushButton("Browse…")
    button.clicked.connect(choose)
    layout.addWidget(edit, 1)
    layout.addWidget(button)
    return container


class AnalysisDialog(QDialog):
    def __init__(self, paths, settings, watching=False, parent=None):
        super().__init__(parent)
        self.paths, self.baselines, self.settings = list(paths), [], settings
        self.watching, self.worker, self.pending_reject = watching, None, False
        self.setWindowTitle("Watch local evidence" if watching else "Analyze evidence")
        self.resize(850, 710)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Configure investigation", "heading"))
        layout.addWidget(
            label(
                "Source formats are detected locally. Original evidence is preserved.", "subtitle"
            )
        )
        self.source_model = RowsModel(
            ("Filename", "Detected format", "Bytes", "Diagnostic"), parent=self
        )
        self.table = QTableView()
        self.table.setModel(self.source_model)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 210)
        self.table.setColumnWidth(1, 130)
        self.table.setMaximumHeight(180)
        layout.addWidget(self.table)
        form = QFormLayout()
        self.profile = QComboBox()
        self.profile.addItems(["generic", "web", "api"])
        self.profile.setEditable(True)
        self.profile.setCurrentText(settings.value("profile", "generic"))
        form.addRow("Profile / profile YAML", path_row(self.profile, self.choose_profile))
        self.target = QLineEdit()
        self.target.setPlaceholderText(
            "Optional exact origin; required for relative Gobuster paths"
        )
        form.addRow("Target scope", self.target)
        self.scope = QLineEdit()
        self.scope.setPlaceholderText("Optional file of additional exact origins")
        form.addRow("Scope file", path_row(self.scope, self.choose_scope))
        self.baseline_label = QLineEdit("None — comparisons may be unavailable")
        self.baseline_label.setReadOnly(True)
        form.addRow("Baseline evidence", path_row(self.baseline_label, self.choose_baselines))
        self.output = QLineEdit(
            str(Path("results") / datetime.now(UTC).strftime("gui-%Y%m%dT%H%M%S.%fZ"))
        )
        form.addRow("New output directory", path_row(self.output, self.choose_output))
        self.recursive = QCheckBox("Include nested evidence folders")
        self.recursive.toggled.connect(self.preview)
        form.addRow("", self.recursive)
        limits_widget = QWidget()
        limits_layout = QHBoxLayout(limits_widget)
        limits_layout.setContentsMargins(0, 0, 0, 0)
        self.file_limit, self.total_limit, self.record_limit = QSpinBox(), QSpinBox(), QSpinBox()
        for spin, low, high, value, text in [
            (self.file_limit, 1, 256, 64, " MiB / file"),
            (self.total_limit, 1, 512, 128, " MiB total"),
            (self.record_limit, 1, 100000, 100000, " observations"),
        ]:
            spin.setRange(low, high)
            spin.setValue(value)
            spin.setSuffix(text)
            limits_layout.addWidget(spin)
        form.addRow("Input limits", limits_widget)
        self.debounce = QDoubleSpinBox()
        self.debounce.setRange(0.05, 30)
        self.debounce.setValue(float(settings.value("debounce", 0.75)))
        self.debounce.setSuffix(" seconds")
        if watching:
            form.addRow("Watch debounce", self.debounce)
        layout.addLayout(form)
        self.message = label("Detecting input formats…")
        layout.addWidget(self.message)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Start Watching" if watching else "Start Analysis"
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.preview()

    def request(self):
        return AnalysisRequest(
            paths=self.paths,
            baselines=list(self.baselines),
            profile=self.profile.currentText(),
            target=self.target.text().strip() or None,
            scope_file=Path(self.scope.text()) if self.scope.text().strip() else None,
            output=Path(self.output.text()) if self.output.text().strip() else None,
            recursive=self.recursive.isChecked(),
            debounce=self.debounce.value(),
            limits=InputLimits(
                file_bytes=self.file_limit.value() * 1024**2,
                total_bytes=self.total_limit.value() * 1024**2,
                records=self.record_limit.value(),
            ),
        )

    def preview(self):
        if self.worker is not None:
            return
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.recursive.setEnabled(False)
        self.worker = Worker("preview", self.request(), self)
        self.worker.ready.connect(self.preview_ready)
        self.worker.failed.connect(lambda message, _: self.message.setText(message))
        self.worker.finished.connect(self.preview_finished)
        self.worker.start()

    def preview_ready(self, rows):
        self.source_model.replace(rows)
        formats = sorted({row[1] for row in rows if row[1] != "Unknown"})
        self.message.setText(
            f"{len(rows)} files · Formats: {', '.join(formats) or 'none detected'}. "
            "Import diagnostics will retain any rejected inputs."
        )

    def preview_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self.recursive.setEnabled(True)
        if self.pending_reject:
            super().reject()

    def reject(self):
        if self.worker is not None:
            self.pending_reject = True
            self.worker.stop()
            self.message.setText("Finishing the current file read…")
        else:
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            event.ignore()
            self.reject()
        else:
            super().closeEvent(event)

    def choose_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Profile YAML", "", "YAML (*.yaml *.yml)")
        if path:
            self.profile.setCurrentText(path)

    def choose_scope(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Scope file", "", "Text files (*.txt);;All files (*)"
        )
        if path:
            self.scope.setText(path)

    def choose_baselines(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Known missing-path evidence",
            "",
            "Evidence (*.json *.jsonl *.ndjson *.har *.ejson *.txt)",
        )
        if paths:
            self.baselines = [Path(path) for path in paths]
            self.baseline_label.setText(", ".join(path.name for path in self.baselines))

    def choose_output(self):
        parent = QFileDialog.getExistingDirectory(self, "Parent folder for a new investigation")
        if parent:
            self.output.setText(
                str(Path(parent) / datetime.now(UTC).strftime("fuzzrank-%Y%m%dT%H%M%S.%fZ"))
            )


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FuzzRank preferences")
        self.settings = settings
        layout = QFormLayout(self)
        self.appearance = QComboBox()
        self.appearance.addItems(["dark", "light"])
        self.appearance.setCurrentText(settings.value("appearance", "dark"))
        self.profile = QComboBox()
        self.profile.addItems(["generic", "web", "api"])
        self.profile.setCurrentText(settings.value("profile", "generic"))
        self.debounce = QDoubleSpinBox()
        self.debounce.setRange(0.05, 30)
        self.debounce.setValue(float(settings.value("debounce", 0.75)))
        layout.addRow("Appearance", self.appearance)
        layout.addRow("Default profile", self.profile)
        layout.addRow("Watch debounce (seconds)", self.debounce)
        layout.addRow(
            label(
                "Preferences stay local. Evidence paths and recent investigations are not stored."
            )
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self):
        self.settings.setValue("appearance", self.appearance.currentText())
        self.settings.setValue("profile", self.profile.currentText())
        self.settings.setValue("debounce", self.debounce.value())
        self.settings.sync()
        super().accept()
