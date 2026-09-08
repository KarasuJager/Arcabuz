"""Native presentation and application orchestration; all analysis lives in shared services."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QModelIndex, QSettings, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fuzzrank import __version__
from fuzzrank.gui import brand, theme
from fuzzrank.gui.dialogs import AnalysisDialog, SettingsDialog, label
from fuzzrank.gui.models import CANDIDATE_ROLE, CandidateFilter, CandidateModel, RowsModel
from fuzzrank.gui.presentation import ViewData, plain, tooltip
from fuzzrank.gui.widgets import ElidingLabel, EvidenceTable, PageStack
from fuzzrank.gui.worker import AnalysisRequest, Worker

FILE_FILTER = "Evidence (*.json *.jsonl *.ndjson *.ejson *.har *.txt *.log);;All files (*)"


def text_panel():
    widget = QPlainTextEdit()
    widget.setReadOnly(True)
    return widget


def table(model):
    return EvidenceTable(model)


class MainWindow(QMainWindow):
    report_loaded = Signal(object)
    export_finished = Signal(str)
    job_finished = Signal()

    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        self.settings = settings or QSettings(
            QSettings.Format.IniFormat, QSettings.Scope.UserScope, "FuzzRank", "desktop"
        )
        self._sanitize_settings()
        self.worker = None
        self.view_data: ViewData | None = None
        self.selected_candidate = None
        self.pending_close = False
        self.last_error = self.technical_error = ""
        self.dialogs = []
        self._split_ratio = 0.62
        self._restoring_split = False
        self.setWindowTitle(f"FuzzRank {__version__} — Evidence triage")
        self.setWindowIcon(brand.icon())
        self.resize(1366, 860)
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)
        self._toolbar()
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(10, 6, 12, 8)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.addItems(
            ["Summary", "Candidates", "Clusters", "Suppressed / noise", "Baselines", "Sources"]
        )
        self.navigation.setMinimumWidth(156)
        self.navigation.setMaximumWidth(184)
        self.navigation.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.navigation.setEnabled(False)
        layout.addWidget(self.navigation)
        self.root_stack = PageStack()
        layout.addWidget(self.root_stack, 1)
        self.setCentralWidget(root)
        self.root_stack.addWidget(self._home())
        self.root_stack.addWidget(self._workspace())
        self.navigation.currentRowChanged.connect(self.navigate)
        self.status = ElidingLabel("Ready · local evidence only")
        self.statusBar().addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(150)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self._apply_theme()

    def _sanitize_settings(self):
        for key, allowed, default in [
            ("appearance", {"dark", "light"}, "dark"),
            ("profile", {"generic", "web", "api"}, "generic"),
        ]:
            if self.settings.value(key, default) not in allowed:
                self.settings.setValue(key, default)
        try:
            value = float(self.settings.value("debounce", 0.75))
            if not 0.05 <= value <= 30:
                raise ValueError
        except (ValueError, TypeError):
            self.settings.setValue("debounce", 0.75)

    def _action(self, text, callback, shortcut=None):
        action = QAction(text, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _toolbar(self):
        bar = QToolBar("Investigation actions")
        self.action_bar = bar
        bar.setMovable(False)
        self.addToolBar(bar)
        bar.addWidget(brand.badge(26))
        bar.addWidget(label("FuzzRank", "brand"))
        bar.addSeparator()
        self.open_action = self._action("Analyze files", self.choose_files, "Ctrl+O")
        self.folder_action = self._action("Analyze folder", self.choose_folder)
        self.report_action = self._action("Open report", self.choose_report)
        self.watch_action = self._action("Watch directory", self.choose_watch)
        self.stop_action = self._action("Stop", self.stop_job)
        self.stop_action.setEnabled(False)
        self.export_action = self._action("Export…", self.choose_export, "Ctrl+E")
        self.export_action.setEnabled(False)
        self.demo_action = self._action("Demo", self.open_demo)
        self.settings_action = self._action("Preferences", self.preferences)
        self.home_action = self._action("Home", self.show_home)
        for action in (
            self.open_action,
            self.folder_action,
            self.report_action,
            self.watch_action,
            self.stop_action,
            self.export_action,
        ):
            bar.addAction(action)
        bar.addSeparator()
        bar.addAction(self.settings_action)
        menu = self.menuBar().addMenu("&Investigation")
        for action in (
            self.open_action,
            self.folder_action,
            self.report_action,
            self.watch_action,
            self.demo_action,
            self.home_action,
            self.export_action,
        ):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self._action("Quit", self.close, "Ctrl+Q"))
        self.addAction(self._action("Search candidates", self.focus_search, "Ctrl+F"))

    def _home(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 18, 28, 18)
        layout.addStretch()
        identity = QHBoxLayout()
        identity.addWidget(brand.badge(88))
        identity.addWidget(label("FuzzRank\nDeterministic evidence triage", "brand"))
        identity.addStretch()
        layout.addLayout(identity)
        layout.addWidget(label("Evidence in. A focused review queue out.", "heading"))
        layout.addWidget(
            label(
                "Import authorized fuzzing results and captured responses. "
                "Review deterministic priorities, noise and original provenance.",
                "subtitle",
            )
        )
        buttons = QGridLayout()
        actions = [
            ("Analyze files", self.choose_files),
            ("Analyze folder", self.choose_folder),
            ("Import HAR", self.choose_har),
            ("Open saved JSON report", self.choose_report),
            ("Watch directory", self.choose_watch),
            ("Open demo", self.open_demo),
        ]
        self.home_buttons = {}
        for index, (text, callback) in enumerate(actions):
            button = QPushButton(text)
            button.setMinimumHeight(48)
            button.clicked.connect(callback)
            buttons.addWidget(button, index // 2, index % 2)
            self.home_buttons[text] = button
        layout.addSpacing(12)
        layout.addLayout(buttons)
        layout.addSpacing(12)
        layout.addWidget(
            label("Drop local files or folders here to configure an investigation.", "subtitle")
        )
        layout.addWidget(
            label(
                "Scores indicate manual investigation priority. "
                "FuzzRank does not claim that a candidate is vulnerable.",
                "subtitle",
            )
        )
        layout.addStretch()
        return page

    def _workspace(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 0, 0, 0)
        self.investigation_title = ElidingLabel("Investigation", "heading")
        self.investigation_meta = ElidingLabel("", "subtitle")
        layout.addWidget(self.investigation_title)
        layout.addWidget(self.investigation_meta)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.pages = PageStack()
        self.pages.addWidget(self._summary_page())
        self.pages.addWidget(self._candidates_page())
        self.pages.addWidget(self._clusters_page())
        self.pages.addWidget(self._baselines_page())
        self.pages.addWidget(self._sources_page())
        self.splitter.addWidget(self.pages)
        self.details = self._details()
        self.details.setMinimumHeight(210)
        self.splitter.addWidget(self.details)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(7)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.splitterMoved.connect(self.remember_split)
        layout.addWidget(self.splitter, 1)
        return page

    def _summary_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        cards = QGridLayout()
        self.metrics = {}
        keys = [
            ("raw_discoveries", "Imported discoveries"),
            ("noise_suppressed", "Suppressed endpoints"),
            ("unique_candidates", "Retained candidates"),
            ("inspect_now", "Inspect now"),
            ("high", "High"),
            ("medium", "Medium"),
            ("low", "Low"),
            ("clusters", "Clusters"),
            ("sources", "Source files"),
        ]
        for index, (key, title) in enumerate(keys):
            box = QFrame()
            box.setObjectName("metric")
            inner = QVBoxLayout(box)
            value = label("—", "metricValue")
            inner.addWidget(value)
            inner.addWidget(label(title, "metricLabel"))
            cards.addWidget(box, index // 3, index % 3)
            self.metrics[key] = value
        layout.addLayout(cards)
        self.summary_notes = text_panel()
        layout.addWidget(self.summary_notes, 1)
        review = QPushButton("Review highest-priority candidates")
        review.clicked.connect(lambda: self.navigation.setCurrentRow(1))
        layout.addWidget(review, alignment=Qt.AlignmentFlag.AlignLeft)
        return page

    def _candidates_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search paths, hosts, engines or scoring reasons…")
        self.search.setAccessibleName("Search candidates")
        self.band, self.status_filter, self.engine, self.media = (QComboBox() for _ in range(4))
        self.filter_combos = [self.band, self.status_filter, self.engine, self.media]
        for title, widget in [
            ("Priority", self.band),
            ("Status", self.status_filter),
            ("Engine", self.engine),
            ("Content type", self.media),
        ]:
            filters.addWidget(label(title))
            widget.setAccessibleName(title)
            widget.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            widget.setMinimumContentsLength(5)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            filters.addWidget(widget, 2 if widget is self.media else 1)
            widget.currentIndexChanged.connect(
                lambda _, w=widget: w.setToolTip(tooltip(w.currentData() or "All values"))
            )
        self.cluster_filter = QLineEdit()
        self.cluster_filter.setPlaceholderText("Cluster ID (optional)")
        self.cluster_filter.setAccessibleName("Cluster filter")
        self.cluster_filter.setMaximumWidth(195)
        self.cluster_filter.textChanged.connect(
            lambda value: self.cluster_filter.setToolTip(
                tooltip(value or "Filter by full cluster ID")
            )
        )
        self.noise_filter = QComboBox()
        self.noise_filter.setAccessibleName("Noise reason")
        for text, data in [
            ("Suppressed endpoints", "suppressed"),
            ("Baseline / wildcard match", "baseline"),
            ("Duplicate responses", "duplicate"),
            ("Static-asset penalty", "static"),
            ("Any negative rule", "negative"),
        ]:
            self.noise_filter.addItem(text, data)
        self.noise_filter.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.noise_filter.setMinimumContentsLength(12)
        filters.addWidget(self.noise_filter, 1)
        self.noise_filter.hide()
        reset = QPushButton("Reset filters")
        reset.clicked.connect(self.reset_filters)
        search_row = QHBoxLayout()
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.cluster_filter)
        search_row.addWidget(reset)
        self.columns_button = QToolButton()
        self.columns_button.setText("Columns")
        self.columns_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        search_row.addWidget(self.columns_button)
        layout.addLayout(search_row)
        layout.addLayout(filters)
        self.match_count = ElidingLabel("")
        layout.addWidget(self.match_count)
        self.candidate_model = CandidateModel(self)
        self.proxy = CandidateFilter(self)
        self.proxy.setSourceModel(self.candidate_model)
        self.candidate_table = table(self.proxy)
        self.candidate_table.setMinimumHeight(135)
        self.candidate_table.setObjectName("candidates")
        self.candidate_table.setSortingEnabled(True)
        self.candidate_table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        self.candidate_table.configure_columns(
            {
                0: (55, 0),
                1: (100, 0),
                2: (63, 0),
                3: (56, 0),
                4: (150, 5),
                5: (130, 2),
                6: (100, 2),
                7: (66, 0),
                8: (110, 0),
                9: (80, 1),
                10: (90, 0),
            },
            hidden=(5, 8, 10),
        )
        self.columns_button.setMenu(self.candidate_table.columns_menu())
        layout.addWidget(self.candidate_table, 1)
        self.filter_timer = QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(160)
        self.filter_timer.timeout.connect(self.apply_filters)
        self.search.textChanged.connect(lambda: self.filter_timer.start())
        self.cluster_filter.textChanged.connect(lambda: self.filter_timer.start())
        for combo in self.filter_combos + [self.noise_filter]:
            combo.currentIndexChanged.connect(self.apply_filters)
        self.candidate_table.selectionModel().currentRowChanged.connect(self.select_candidate)
        return page

    def _clusters_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label("Response clusters", "heading"))
        layout.addWidget(
            label(
                "Repeated missing-path responses can reveal wildcard or custom-404 noise. "
                "Open members to inspect every endpoint, including suppressed evidence.",
                "subtitle",
            )
        )
        self.cluster_model = RowsModel(
            (
                "Cluster",
                "Discoveries",
                "Endpoints",
                "Representative",
                "Statuses",
                "Content types",
                "Size range",
                "Engines",
                "Core assessment",
                "Suppression rationale",
            ),
            parent=self,
            formats={0: "id", 5: "media"},
        )
        self.cluster_table = table(self.cluster_model)
        self.cluster_table.configure_columns(
            {
                0: (110, 0),
                1: (85, 0),
                2: (78, 0),
                3: (160, 3),
                4: (85, 0),
                5: (120, 1),
                6: (78, 0),
                7: (95, 0),
                8: (180, 2),
                9: (200, 2),
            },
            hidden=(5, 7, 9),
        )
        self.cluster_table.horizontalHeader().moveSection(8, 3)
        layout.addWidget(self.cluster_table, 1)
        self.cluster_detail = text_panel()
        self.cluster_detail.setMaximumHeight(125)
        layout.addWidget(self.cluster_detail)
        self.cluster_table.selectionModel().currentRowChanged.connect(self.select_cluster)
        members = QPushButton("Open selected cluster members")
        members.clicked.connect(lambda: self.open_cluster(self.cluster_table.currentIndex()))
        self.cluster_table.doubleClicked.connect(self.open_cluster)
        layout.addWidget(members, alignment=Qt.AlignmentFlag.AlignLeft)
        return page

    def _baselines_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label("Baseline evidence", "heading"))
        self.baseline_note = label("", "subtitle")
        layout.addWidget(self.baseline_note)
        self.baseline_model = RowsModel(
            (
                "Method",
                "Status",
                "URL",
                "Content type",
                "Bytes",
                "Raw SHA-256",
                "Normalized SHA-256",
                "Redirect",
                "Body support",
                "Source",
            ),
            parent=self,
            formats={3: "media", 5: "hash", 6: "hash", 9: "id"},
        )
        self.baseline_table = table(self.baseline_model)
        self.baseline_table.configure_columns(
            {
                0: (63, 0),
                1: (56, 0),
                2: (220, 4),
                3: (100, 1),
                4: (66, 0),
                5: (125, 1),
                6: (140, 1),
                7: (150, 2),
                8: (100, 0),
                9: (130, 1),
            },
            hidden=(0, 7, 9),
        )
        layout.addWidget(self.baseline_table)
        return page

    def _sources_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label("Source evidence & import diagnostics", "heading"))
        self.source_model = RowsModel(
            (
                "Filename",
                "Format",
                "State",
                "Records",
                "Engines",
                "Errors",
                "Source ID",
                "Archive SHA-256",
            ),
            parent=self,
            formats={0: "filename", 6: "id", 7: "hash"},
        )
        self.source_table = table(self.source_model)
        self.source_table.configure_columns(
            {
                0: (175, 3),
                1: (85, 0),
                2: (85, 0),
                3: (70, 0),
                4: (95, 2),
                5: (55, 0),
                6: (125, 1),
                7: (125, 1),
            }
        )
        layout.addWidget(self.source_table, 2)
        self.diagnostics = text_panel()
        layout.addWidget(self.diagnostics, 1)
        self.source_table.selectionModel().currentRowChanged.connect(self.select_source)
        return page

    def _details(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 3, 0, 0)
        layout.setSpacing(3)
        self.detail_title = ElidingLabel("Select a candidate to inspect its evidence")
        layout.addWidget(self.detail_title)
        url_row = QHBoxLayout()
        self.full_url = QLineEdit()
        self.full_url.setReadOnly(True)
        self.full_url.setAccessibleName("Selected candidate URL")
        self.copy_button = QPushButton("Copy URL")
        self.copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(self.full_url.text())
        )
        url_row.addWidget(self.full_url, 1)
        url_row.addWidget(self.copy_button)
        layout.addLayout(url_row)
        self.detail_tabs = QTabWidget()
        self.reason_model = RowsModel(("Points", "Rule", "Explanation"), parent=self)
        self.reason_table = table(self.reason_model)
        self.reason_table.setWordWrap(True)
        self.reason_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.reason_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.reason_table.configure_columns({0: (66, 0), 1: (170, 1), 2: (240, 5)}, hidden=(1,))
        self.score_page = QWidget()
        score_layout = QVBoxLayout(self.score_page)
        score_layout.setContentsMargins(0, 0, 0, 0)
        score_layout.setSpacing(2)
        self.score_note = ElidingLabel("")
        score_layout.addWidget(self.score_note)
        score_layout.addWidget(self.reason_table, 1)
        self.detail_tabs.addTab(self.score_page, "Why this score")
        self.evidence_detail = text_panel()
        self.detail_tabs.addTab(self.evidence_detail, "Response / baseline")
        self.provenance_model = RowsModel(
            (
                "Engine",
                "Status",
                "Content type",
                "Bytes",
                "Source",
                "Record",
                "Captured",
                "Body support",
            ),
            parent=self,
            formats={2: "media", 4: "id", 6: "time"},
        )
        self.provenance_table = table(self.provenance_model)
        self.provenance_table.configure_columns(
            {
                0: (85, 1),
                1: (56, 0),
                2: (105, 2),
                3: (66, 0),
                4: (180, 3),
                5: (60, 0),
                6: (150, 1),
                7: (100, 0),
            }
        )
        self.detail_tabs.addTab(self.provenance_table, "Provenance")
        layout.addWidget(self.detail_tabs, 1)
        return container

    def _apply_theme(self):
        dark = self.settings.value("appearance", "dark") == "dark"
        theme.apply(QApplication.instance(), dark)
        self.candidate_model.dark = dark
        self.candidate_table.viewport().update()

    def navigate(self, row):
        if row < 0:
            return
        self.root_stack.setCurrentIndex(1)
        self.pages.setCurrentIndex([0, 1, 2, 1, 3, 4][row])
        self.details.setVisible(row in (1, 3))
        self.noise_filter.setVisible(row == 3)
        if row in (1, 3):
            self.proxy.configure(mode="noise" if row == 3 else "retained")
            self.apply_filters()
            QTimer.singleShot(0, self.restore_split)

    def remember_split(self, *_):
        if not self._restoring_split and self.details.isVisible():
            sizes = self.splitter.sizes()
            self._split_ratio = sizes[0] / max(1, sum(sizes))

    def restore_split(self):
        if not self.details.isVisible():
            return
        self._restoring_split = True
        available = self.splitter.height() - self.splitter.handleWidth()
        self.splitter.setSizes(
            [round(available * self._split_ratio), round(available * (1 - self._split_ratio))]
        )
        self._restoring_split = False

    def select_cluster(self, index, previous=None):
        if not index.isValid():
            self.cluster_detail.clear()
            return
        row = self.cluster_model.rows[index.row()]
        self.cluster_detail.setPlainText(
            f"{row[8]}\n{row[2]} endpoints · {row[1]} discoveries · "
            f"Representative: {row[3]}\nSuppression: {row[9]}\n"
            f"Full cluster ID: {row[0]}\nContent types: {row[5]} · Engines: {row[7]}"
        )

    def focus_search(self):
        if self.view_data:
            self.navigation.setCurrentRow(1)
            self.search.setFocus()
            self.search.selectAll()

    def show_home(self):
        if self.worker is None:
            self.root_stack.setCurrentIndex(0)

    def reset_filters(self):
        widgets = [self.search, self.cluster_filter, self.noise_filter, *self.filter_combos]
        blockers = [QSignalBlocker(widget) for widget in widgets]
        self.search.clear()
        self.cluster_filter.clear()
        for combo in self.filter_combos + [self.noise_filter]:
            combo.setCurrentIndex(0)
        del blockers
        self.proxy.configure(mode="noise" if self.navigation.currentRow() == 3 else "retained")
        self.apply_filters()

    def apply_filters(self):
        self.proxy.configure(
            text=self.search.text(),
            band=self.band.currentData() or "",
            status=self.status_filter.currentData() or "",
            engine=self.engine.currentData() or "",
            content_type=self.media.currentData() or "",
            cluster=self.cluster_filter.text().strip(),
            noise=self.noise_filter.currentData(),
        )
        self.match_count.setText(
            f"{self.proxy.rowCount():,} shown · "
            f"{len(self.candidate_model.records):,} total endpoints · "
            "Filtering does not alter scores or evidence"
        )

    def open_cluster(self, index):
        if not index.isValid():
            return
        cluster_id = self.cluster_model.rows[index.row()][0]
        self.navigation.setCurrentRow(1)
        self.reset_filters()
        self.proxy.configure(mode="all")
        self.cluster_filter.setText(cluster_id)
        self.apply_filters()
        self.match_count.setText(self.match_count.text() + " · Includes suppressed members")
        if self.proxy.rowCount():
            self.candidate_table.selectRow(0)

    def select_candidate(self, index, previous=None):
        if not index.isValid():
            self.selected_candidate = None
            self.full_url.clear()
            self.reason_model.replace([])
            self.provenance_model.replace([])
            self.evidence_detail.clear()
            self.score_note.clear()
            self.detail_title.setText("Select a candidate to inspect its evidence")
            return
        candidate = index.data(CANDIDATE_ROLE)
        if candidate is None:
            return
        self.selected_candidate = candidate
        self.full_url.setText(plain(candidate.url))
        self.detail_title.setText(
            f"Priority {candidate.score} / 100 · {candidate.category} · "
            f"{plain(candidate.method)} {plain(candidate.path)}"
        )
        self.reason_model.replace(
            [(f"{r.points:+}", r.rule_id, r.reason) for r in candidate.score_reasons]
        )
        total = sum(r.points for r in candidate.score_reasons if r.rule_id != "score_cap")
        cap = (
            f"Rule total {total:+}; limited to {candidate.score} / 100. "
            if total != candidate.score
            else ""
        )
        self.score_note.setText(
            cap + "Each rule shown once. Investigation priority, not a vulnerability finding."
        )
        item, fp = candidate.primary, candidate.fingerprint
        similarity = candidate.baseline_similarity
        evidence = [
            f"Method: {candidate.method}",
            f"Path: {candidate.path}",
            f"Status: {item.status_code}",
            f"Content type: {item.content_type or 'Unknown'}",
            "Response size: "
            + (
                f"{item.content_length} bytes" if item.content_length is not None else "Unavailable"
            ),
            f"Redirect: {item.location or 'None'}",
            f"Cluster: {candidate.response_cluster} ({candidate.cluster_size} endpoints)",
            f"Baseline: {candidate.baseline}; similarity: "
            f"{similarity if similarity is not None else 'Unavailable'}",
            f"Evidence support: {candidate.evidence_quality}",
            *candidate.evidence_gaps,
            f"Suppression: {candidate.suppression_reason or 'Retained'}",
            f"Conflicting observations: {candidate.evidence_conflict}",
        ]
        if fp:
            evidence += [
                f"Title: {fp.title or 'Unavailable'}",
                f"Raw SHA-256: {fp.raw_sha256}",
                f"Normalized SHA-256: {fp.normalized_sha256}",
                f"Normalization: {fp.normalization}",
            ]
        else:
            evidence.append("Response body unavailable; no fingerprint can be inferred.")
        evidence += sorted({note for o in candidate.observations for note in o.evidence_notes})
        self.evidence_detail.setPlainText("\n".join(plain(line) for line in evidence))
        names = {s["id"]: s.get("original_path", s["id"]) for s in self.view_data.report.sources}
        self.provenance_model.replace(
            [
                (
                    o.engine,
                    o.status_code,
                    o.content_type or "Unknown",
                    o.content_length if o.content_length is not None else -1,
                    names.get(o.source, o.source),
                    o.record,
                    o.timestamp or "Unknown",
                    "Missing" if o.body is None else "Incomplete" if o.truncated else "Available",
                )
                for o in candidate.observations
            ]
        )

    def select_source(self, index, previous=None):
        if self.view_data is None:
            return
        report = self.view_data.report
        entries = report.import_diagnostics
        if index.isValid():
            row = self.source_model.rows[index.row()]
            entries = [d for d in entries if d["source"] in (row[0], row[6])]
        lines = [
            f"{len(entries)} diagnostics. Showing up to 500; complete details are in JSON.",
            *report.warnings[:30],
        ]
        lines += [
            f"{d['severity']} · {d['source']} · record {d.get('record', '—')}: {d['message']}"
            for d in entries[:500]
        ]
        self.diagnostics.setPlainText("\n".join(plain(line) for line in lines))

    def accept_report(self, data):
        if self.worker is not None and self.worker.stop_event.is_set():
            return
        selected_id = self.selected_candidate.id if self.selected_candidate else None
        self.view_data = data
        report = data.report
        self.candidate_model.set_records(data.candidates)
        # A Qt model reset does not emit currentRowChanged. Never retain details
        # from a previous snapshot while the new table has no current selection.
        self.select_candidate(QModelIndex())
        self.cluster_model.replace(data.clusters)
        if self.cluster_model.rowCount():
            self.cluster_table.selectRow(0)
        self.baseline_model.replace(data.baselines)
        self.source_model.replace(data.sources)
        for combo, values in zip(
            self.filter_combos,
            [
                ["INSPECT NOW", "HIGH", "MEDIUM", "LOW"],
                sorted({s for row in data.candidates for s in row.statuses}),
                sorted({e for row in data.candidates for e in row.engines}),
                sorted({t for row in data.candidates for t in row.types}),
            ],
            strict=True,
        ):
            previous = combo.currentData()
            blocker = QSignalBlocker(combo)
            combo.clear()
            combo.addItem("All", "")
            for value in values:
                combo.addItem(plain(value), value)
            match = combo.findData(previous)
            combo.setCurrentIndex(max(0, match))
            del blocker
        for key, widget in self.metrics.items():
            count = (
                len(report.clusters)
                if key == "clusters"
                else len(data.sources)
                if key == "sources"
                else report.summary[key]
            )
            widget.setText(f"{count:,}")
        self.investigation_title.setText(plain(report.target))
        self.investigation_meta.setText(
            f"Profile: {plain(report.profile)} · "
            f"{'PARTIAL / review diagnostics' if report.partial else 'Complete'} · "
            f"Updated {datetime.now().strftime('%H:%M:%S')}"
        )
        all_engines = ", ".join(sorted({e for row in data.candidates for e in row.engines}))
        self.summary_notes.setPlainText(
            "\n".join(
                [
                    f"Scope: {', '.join(report.scope)}",
                    f"Engines / sources: {all_engines}",
                    f"Repeated observations merged: {report.summary['duplicates_merged']}; "
                    f"out of scope: {report.summary['out_of_scope']}",
                    "Imported discoveries count captured results, "
                    "not all requests made by external tools.",
                    "Requests made by FuzzRank: "
                    f"{report.summary.get('requests_made', 'Not recorded')}. "
                    "Offline imports make no requests; the demo uses its owned loopback server.",
                    f"Investigation saved to: {data.directory}",
                    *[plain(w) for w in report.warnings[:6]],
                ]
            )
        )
        self.baseline_note.setText(
            f"{len(report.baselines)} baseline observations. Two distinct agreeing missing paths "
            "are required for comparison. Missing or incomplete bodies cannot establish a baseline."
            if report.baselines
            else "No baseline evidence supplied. Body/baseline support may be "
            "unavailable; scores do not imply confidence that an endpoint is vulnerable."
        )
        self.navigation.setEnabled(True)
        self.root_stack.setCurrentIndex(1)
        if self.navigation.currentRow() < 0:
            self.navigation.setCurrentRow(1)
        self.apply_filters()
        selected_row = 0
        if selected_id:
            for row in range(self.proxy.rowCount()):
                if self.proxy.index(row, 0).data(CANDIDATE_ROLE).id == selected_id:
                    selected_row = row
                    break
        if self.proxy.rowCount():
            self.candidate_table.selectRow(selected_row)
        self.select_candidate(self.candidate_table.currentIndex())
        self.select_source(self.source_table.currentIndex())
        self.export_action.setEnabled(self.worker is None)
        suffix = " · changed: " + ", ".join(data.changed) if data.changed else ""
        if self.worker and self.worker.operation == "watch":
            self.status.setText(
                "WATCHING: " + ", ".join(map(str, self.worker.payload.paths)) + suffix
            )
        else:
            self.status.setText("Investigation ready · " + str(data.directory))
        self.report_loaded.emit(report)

    def set_busy(self, busy):
        for action in (
            self.open_action,
            self.folder_action,
            self.report_action,
            self.watch_action,
            self.demo_action,
            self.home_action,
            self.settings_action,
        ):
            action.setEnabled(not busy)
        for button in self.home_buttons.values():
            button.setEnabled(not busy)
        self.export_action.setEnabled(not busy and self.view_data is not None)
        self.stop_action.setEnabled(busy)
        self.stop_action.setText(
            "Stop Watching" if busy and self.worker.operation == "watch" else "Cancel"
        )
        self.progress.setVisible(busy)

    def start_job(self, operation, payload):
        if self.worker is not None:
            return False
        self.last_error = self.technical_error = ""
        self.worker = Worker(operation, payload, self)
        self.worker.ready.connect(self.job_ready)
        self.worker.progress.connect(self.status.setText)
        self.worker.failed.connect(self.show_error)
        self.worker.cancelled.connect(
            lambda: self.status.setText(
                "Stopped · previous view and completed evidence files preserved"
            )
        )
        self.worker.finished.connect(self.finish_job)
        self.set_busy(True)
        self.status.setText("Starting " + operation + "…")
        self.worker.start()
        return True

    def begin_analysis(self, request, watching=False):
        return self.start_job("watch" if watching else "analyze", request)

    def job_ready(self, result):
        if self.worker.stop_event.is_set():
            return
        if isinstance(result, ViewData):
            self.accept_report(result)
        elif isinstance(result, Path):
            self.status.setText("Exported: " + str(result))
            self.export_finished.emit(str(result))

    def finish_job(self):
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)
        self.job_finished.emit()
        if self.pending_close:
            self.close()

    def stop_job(self):
        if self.worker:
            self.worker.stop()
            self.stop_action.setEnabled(False)
            self.status.setText(
                "Stopping after the current safe stage; completed evidence is retained…"
            )

    def show_error(self, message, technical):
        self.last_error, self.technical_error = message, technical
        self.status.setText("Error: " + plain(message))
        box = QMessageBox(self)
        box.setWindowTitle("FuzzRank could not complete this operation")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(message)
        box.setInformativeText(
            "Your previous investigation and completed evidence files are retained."
        )
        box.setDetailedText(technical)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.open()

    def configure(self, paths, watching=False):
        if self.worker is not None:
            return
        dialog = AnalysisDialog(paths, self.settings, watching, self)
        self.dialogs.append(dialog)
        dialog.accepted.connect(lambda: self.begin_analysis(dialog.request(), watching))
        dialog.finished.connect(lambda: self.dialogs.remove(dialog))
        dialog.open()

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Analyze saved evidence", "", FILE_FILTER)
        if paths:
            self.configure([Path(path) for path in paths])

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Analyze an evidence folder")
        if path:
            self.configure([Path(path)])

    def choose_har(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Import browser HAR", "", "HAR files (*.har)")
        if paths:
            self.configure([Path(path) for path in paths])

    def choose_watch(self):
        path = QFileDialog.getExistingDirectory(self, "Watch a local evidence folder")
        if path:
            self.configure([Path(path)], watching=True)

    def choose_report(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open a FuzzRank JSON report", "", "JSON reports (*.json)"
        )
        if path:
            self.start_job("open", Path(path).resolve())

    def open_demo(self, checked=False, output=None):
        self.start_job(
            "demo",
            AnalysisRequest(profile=self.settings.value("profile", "generic"), output=output),
        )

    def export_report(self, path, kind):
        if self.view_data is not None:
            return self.start_job(
                "export", (self.view_data.report, self.view_data.directory, Path(path), kind)
            )
        return False

    def choose_export(self):
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Export investigation report",
            "report.json",
            "JSON report (*.json);;HTML report (*.html)",
        )
        if path:
            kind = "html" if "HTML" in selected else "json"
            destination = Path(path)
            if not destination.suffix:
                destination = destination.with_suffix("." + kind)
            self.export_report(destination, kind)

    def preferences(self):
        dialog = SettingsDialog(self.settings, self)
        dialog.accepted.connect(self._apply_theme)
        dialog.open()

    def dragEnterEvent(self, event):
        if (
            self.worker is None
            and event.mimeData().hasUrls()
            and all(url.isLocalFile() for url in event.mimeData().urls())
        ):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths and self.worker is None:
            self.configure(paths)
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.worker is not None:
            self.pending_close = True
            self.stop_job()
            event.ignore()
            return
        if any(dialog.worker is not None for dialog in self.dialogs):
            for dialog in self.dialogs:
                dialog.reject()
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        self.settings.sync()
        super().closeEvent(event)
