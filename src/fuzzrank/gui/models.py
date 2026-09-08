"""Native model/view tables. Filtering changes the view, never the shared Report."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from fuzzrank.gui.presentation import compact, tooltip

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
CANDIDATE_ROLE = Qt.ItemDataRole.UserRole + 2
RAW_ROLE = Qt.ItemDataRole.UserRole + 3
HEADERS = (
    "Score",
    "Band",
    "Method",
    "Status",
    "Path",
    "Host",
    "Content type",
    "Bytes",
    "Cluster",
    "Found by",
    "State",
)
ROOT_INDEX = QModelIndex()
BAND_COLORS = {"INSPECT NOW": "#efb6a1", "HIGH": "#e7cc8b", "MEDIUM": "#9cc6ed", "LOW": "#a6b3c3"}


class RowsModel(QAbstractTableModel):
    def __init__(self, headers, rows=(), parent=None, formats=None):
        super().__init__(parent)
        self.headers, self.rows = tuple(headers), list(rows)
        self.formats = formats or {}

    def replace(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=ROOT_INDEX):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=ROOT_INDEX):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        value = self.rows[index.row()][index.column()]
        if role in (SORT_ROLE, RAW_ROLE):
            return value
        if role == Qt.ItemDataRole.ToolTipRole:
            return tooltip(value)
        if role == Qt.ItemDataRole.DisplayRole:
            return compact(value, self.formats.get(index.column(), ""))
        if role == Qt.ItemDataRole.TextAlignmentRole and isinstance(value, int):
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None


class CandidateModel(RowsModel):
    def __init__(self, parent=None):
        super().__init__(HEADERS, parent=parent, formats={6: "media", 8: "id"})
        self.records = []
        self.dark = True
        self.sort_column = 0
        self.sort_order = Qt.SortOrder.DescendingOrder

    def set_records(self, records):
        self.records = sorted(
            records,
            key=lambda row: row.values[self.sort_column],
            reverse=self.sort_order == Qt.SortOrder.DescendingOrder,
        )
        self.replace([row.values for row in self.records])

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if not 0 <= column < len(HEADERS):
            return
        self.sort_column, self.sort_order = column, order
        if not self.records:
            return
        # Sort cached scalar values in one Python pass. Qt's default comparison loop
        # would cross the Python/C++ boundary hundreds of thousands of times.
        self.layoutAboutToBeChanged.emit()
        persistent = self.persistentIndexList()
        selected = [
            (self.records[index.row()].candidate.id, index.column()) for index in persistent
        ]
        self.records = sorted(
            self.records,
            key=lambda row: row.values[column],
            reverse=order == Qt.SortOrder.DescendingOrder,
        )
        self.rows = [row.values for row in self.records]
        locations = {row.candidate.id: index for index, row in enumerate(self.records)}
        self.changePersistentIndexList(
            persistent, [self.index(locations[identity], col) for identity, col in selected]
        )
        self.layoutChanged.emit()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records):
            return None
        candidate = self.records[index.row()].candidate
        if role == CANDIDATE_ROLE:
            return candidate
        if role == Qt.ItemDataRole.ForegroundRole and index.column() in (0, 1):
            if self.dark:
                return QColor(BAND_COLORS.get(candidate.category, "#a6b3c3"))
            return QColor(
                {
                    "INSPECT NOW": "#8c3426",
                    "HIGH": "#745300",
                    "MEDIUM": "#225981",
                    "LOW": "#495869",
                }.get(candidate.category, "#495869")
            )
        return super().data(index, role)


class CandidateFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        self.text = self.band = self.status = self.engine = self.content_type = self.cluster = ""
        self.mode, self.noise = "retained", "suppressed"
        self.setDynamicSortFilter(True)

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if self.sourceModel() is not None:
            self.sourceModel().sort(column, order)
        super().sort(-1)  # Keep the source's efficiently sorted order through filtering.

    def configure(self, **values):
        modern = hasattr(self, "beginFilterChange") and hasattr(self, "endFilterChange")
        if modern:
            self.beginFilterChange()
        for key, value in values.items():
            setattr(self, key, value.casefold().strip() if key == "text" else value)
        if modern:
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:  # Qt 6.8 compatibility.
            self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        item = self.sourceModel().records[row]
        candidate = item.candidate
        if self.mode == "retained" and candidate.suppressed:
            return False
        if self.mode == "noise":
            rules = {r.rule_id for r in candidate.score_reasons if r.points < 0}
            checks = {
                "suppressed": candidate.suppressed,
                "baseline": candidate.baseline == "match",
                "duplicate": "duplicate_response" in rules,
                "static": "static_asset" in rules,
                "negative": bool(rules - {"score_cap"}),
            }
            if not checks.get(self.noise, False):
                return False
        return (
            (not self.text or self.text in item.search)
            and (not self.band or candidate.category == self.band)
            and (not self.status or self.status in item.statuses)
            and (not self.engine or self.engine in item.engines)
            and (not self.content_type or self.content_type in item.types)
            and (not self.cluster or candidate.response_cluster == self.cluster)
        )
