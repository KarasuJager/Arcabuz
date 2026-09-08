"""Native responsive presentation helpers; imported values are always treated as text."""

from PySide6.QtCore import QEvent, QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QLayout,
    QMenu,
    QPlainTextEdit,
    QSizePolicy,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
)

from fuzzrank.gui.models import RAW_ROLE
from fuzzrank.gui.presentation import plain, tooltip


class ElidingLabel(QLabel):
    """A single-line label whose text never dictates the window's minimum width."""

    def __init__(self, text="", name="", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        if name:
            self.setObjectName(name)
        self.setText(text)

    def text(self):
        return self._full

    def clear(self):
        self.setText("")

    def setText(self, text):
        self._full = plain(text)
        self.setToolTip(tooltip(text))
        self.setAccessibleName(self._full)
        self._elide()

    def _elide(self):
        super().setText(
            self.fontMetrics().elidedText(
                self._full, Qt.TextElideMode.ElideMiddle, max(0, self.contentsRect().width())
            )
        )

    def sizeHint(self):
        return QSize(240, self.fontMetrics().height() + 4)

    def minimumSizeHint(self):
        return QSize(0, self.sizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


class PageStack(QStackedWidget):
    """Only the visible page contributes sizing constraints, not every hidden view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.currentChanged.connect(lambda _: self.updateGeometry())

    def sizeHint(self):
        return self.currentWidget().sizeHint() if self.currentWidget() else QSize(400, 300)

    def minimumSizeHint(self):
        height = self.currentWidget().minimumSizeHint().height() if self.currentWidget() else 0
        return QSize(0, max(0, height))


class EvidenceTable(QTableView):
    """Fit useful columns in available space; full data stays copyable and inspectable."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._columns = {}
        self._fitting = False
        self._automatic = True
        self._header_dragging = False
        self.setModel(model)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(0, 100)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setShowGrid(False)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(27)
        header = self.horizontalHeader()
        header.setMinimumSectionSize(40)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.sectionResized.connect(self._section_resized)
        header.installEventFilter(self)
        header.viewport().installEventFilter(self)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_menu)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._cell_menu)
        self.copy_action = QAction("Copy full cell value", self)
        self.copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        self.copy_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.copy_action.triggered.connect(self.copy_cell)
        self.addAction(self.copy_action)
        self.row_action = QAction("View full row…", self)
        self.row_action.triggered.connect(self.show_row)
        self.addAction(self.row_action)
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit_columns)
        model.modelReset.connect(lambda: self.fit_timer.start(0))

    def eventFilter(self, watched, event):
        if watched in (self.horizontalHeader(), self.horizontalHeader().viewport()):
            if event.type() == QEvent.Type.MouseButtonPress:
                self._header_dragging = True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._header_dragging = False
        return super().eventFilter(watched, event)

    def configure_columns(self, columns, hidden=()):
        """column -> (minimum readable width, share of extra width)."""
        self._columns = dict(columns)
        self._fitting = True
        for column in range(self.model().columnCount()):
            self.setColumnHidden(column, column in hidden)
        self._fitting = False
        self.fit_columns()

    def _section_resized(self, *_):
        if not self._fitting and self._header_dragging:
            self._automatic = False  # Respect a deliberate user drag until Fit columns.

    def fit_columns(self):
        if not self._columns or not self._automatic or self._fitting:
            return
        visible = [c for c in self._columns if not self.isColumnHidden(c)]
        base = sum(self._columns[c][0] for c in visible)
        extra = max(0, self.viewport().width() - base)
        weight = sum(self._columns[c][1] for c in visible) or 1
        self._fitting = True
        remaining = extra
        expandable = [c for c in visible if self._columns[c][1]]
        for column in visible:
            minimum, share = self._columns[column]
            increment = extra * share // weight
            if expandable and column == expandable[-1]:
                increment = remaining
            remaining -= increment
            self.setColumnWidth(column, minimum + increment)
        self._fitting = False

    def reset_widths(self):
        self._automatic = True
        self.fit_columns()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_columns()
        self.fit_timer.start(0)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_timer.start(0)

    def columns_menu(self):
        menu = QMenu(self)
        column_actions = []
        for column in range(self.model().columnCount()):
            title = self.model().headerData(column, Qt.Orientation.Horizontal)
            action = menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(not self.isColumnHidden(column))
            action.toggled.connect(lambda checked, c=column: self.toggle_column(c, checked))
            column_actions.append(action)

        def synchronize():
            for column, action in enumerate(column_actions):
                blocker = QSignalBlocker(action)
                action.setChecked(not self.isColumnHidden(column))
                del blocker

        menu.aboutToShow.connect(synchronize)
        menu.addSeparator()
        menu.addAction("Fit columns to window", self.reset_widths)
        return menu

    def toggle_column(self, column, visible):
        self._fitting = True
        self.setColumnHidden(column, not visible)
        self._fitting = False
        self.reset_widths()

    def _header_menu(self, point):
        menu = self.columns_menu()
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.popup(self.horizontalHeader().mapToGlobal(point))

    def _cell_menu(self, point):
        index = self.indexAt(point)
        if index.isValid():
            self.setCurrentIndex(index)
        menu = QMenu(self)
        menu.addAction(self.copy_action)
        menu.addAction("Copy full row with headings", self.copy_row)
        menu.addAction(self.row_action)
        columns = self.columns_menu()
        columns.setTitle("Columns")
        menu.addMenu(columns)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.popup(self.viewport().mapToGlobal(point))

    def copy_cell(self):
        index = self.currentIndex()
        if index.isValid():
            QApplication.clipboard().setText(str(index.data(RAW_ROLE)))

    def row_text(self):
        index = self.currentIndex()
        if not index.isValid():
            return ""
        return "\n".join(
            f"{self.model().headerData(c, Qt.Orientation.Horizontal)}: "
            f"{self.model().index(index.row(), c).data(RAW_ROLE)}"
            for c in range(self.model().columnCount())
        )

    def copy_row(self):
        if text := self.row_text():
            QApplication.clipboard().setText(text)

    def show_row(self):
        if not (text := self.row_text()):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Full evidence values")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.resize(760, 460)
        layout = QVBoxLayout(dialog)
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(text)
        layout.addWidget(details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.open()
