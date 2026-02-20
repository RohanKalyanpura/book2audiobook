from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from book2audiobook import Chapter, JobRecord


class ChapterTableModel(QAbstractTableModel):
    HEADERS = ["Include", "Chapter Name", "Start Preview"]

    def __init__(self, chapters: list[Chapter]):
        super().__init__()
        self.chapters = chapters

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.chapters)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        chapter = self.chapters[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            if col == 1:
                return chapter.title
            if col == 2:
                return chapter.preview
        if role == Qt.CheckStateRole and col == 0:
            return Qt.CheckState.Checked if chapter.include else Qt.CheckState.Unchecked
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            return base | Qt.ItemIsUserCheckable
        if index.column() == 1:
            return base | Qt.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False
        chapter = self.chapters[index.row()]
        if index.column() == 0 and role in (Qt.CheckStateRole, Qt.EditRole):
            chapter.include = self._to_bool_check_state(value)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True
        if index.column() == 1 and role == Qt.EditRole:
            chapter.title = str(value)
            self.dataChanged.emit(index, index)
            return True
        return False

    @staticmethod
    def _to_bool_check_state(value: Any) -> bool:
        if isinstance(value, bool):
            return value

        raw = value
        # PySide/PyQt can hand us nested enum wrappers where `.value` is another
        # enum, so unwrap a few levels without forcing `int()` conversions.
        for _ in range(4):
            if raw == Qt.CheckState.Checked or raw == Qt.Checked:
                return True
            if raw == Qt.CheckState.Unchecked or raw == Qt.Unchecked:
                return False
            if not hasattr(raw, "value"):
                break
            next_raw = getattr(raw, "value")
            if next_raw is raw:
                break
            raw = next_raw

        if isinstance(raw, (int, float)):
            return raw != 0

        text = str(raw).strip().lower()
        if text in {"true", "1", "2", "checked", "qt.checkstate.checked", "checkstate.checked"}:
            return True
        if text in {"false", "0", "unchecked", "qt.checkstate.unchecked", "checkstate.unchecked"}:
            return False
        return bool(raw)

    def move_row(self, source: int, offset: int) -> None:
        target = source + offset
        if source < 0 or source >= len(self.chapters) or target < 0 or target >= len(self.chapters):
            return
        self.beginResetModel()
        self.chapters[source], self.chapters[target] = self.chapters[target], self.chapters[source]
        for idx, chapter in enumerate(self.chapters):
            chapter.order_index = idx
        self.endResetModel()

    def combine_rows(self, rows: list[int]) -> int | None:
        clean_rows = sorted({row for row in rows if 0 <= row < len(self.chapters)})
        if len(clean_rows) < 2:
            return None

        first = clean_rows[0]
        merged = [self.chapters[row] for row in clean_rows]

        self.beginResetModel()
        base = self.chapters[first]
        base.title = f"Combined: {merged[0].title} - {merged[-1].title}"
        base.text = "\n\n".join(ch.text for ch in merged)
        base.preview = base.text[:180]
        base.include = any(ch.include for ch in merged)

        for row in reversed(clean_rows[1:]):
            del self.chapters[row]

        for idx, chapter in enumerate(self.chapters):
            chapter.order_index = idx
        self.endResetModel()
        return first


class JobTableModel(QAbstractTableModel):
    HEADERS = ["Job ID", "Book", "Status", "Progress", "Updated"]

    def __init__(self, jobs: list[JobRecord]):
        super().__init__()
        self.jobs = jobs

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.jobs)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        job = self.jobs[index.row()]
        values = [job.job_id, job.book_id, job.status, f"{job.progress * 100:.1f}%", job.updated_at]
        return values[index.column()]

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)
