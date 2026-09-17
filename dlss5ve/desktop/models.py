from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Property, Qt, Signal, Slot


@dataclass
class BatchEntry:
    index: int
    input_path: str
    output_path: str = ""
    state: str = "Queued"
    progress: float = 0.0
    detail: str = ""
    elapsed_seconds: float = 0.0
    input_dimensions: str = ""
    output_dimensions: str = ""
    thumbnail_url: str = ""
    selected: bool = False

    @property
    def file_name(self) -> str:
        return Path(self.input_path).name


class BatchListModel(QAbstractListModel):
    """QML list model used by all desktop batch queues."""

    countChanged = Signal()
    selectedIndexChanged = Signal()

    FileNameRole = Qt.ItemDataRole.UserRole + 1
    InputPathRole = Qt.ItemDataRole.UserRole + 2
    OutputPathRole = Qt.ItemDataRole.UserRole + 3
    StateRole = Qt.ItemDataRole.UserRole + 4
    ProgressRole = Qt.ItemDataRole.UserRole + 5
    DetailRole = Qt.ItemDataRole.UserRole + 6
    ElapsedSecondsRole = Qt.ItemDataRole.UserRole + 7
    InputDimensionsRole = Qt.ItemDataRole.UserRole + 8
    OutputDimensionsRole = Qt.ItemDataRole.UserRole + 9
    ThumbnailUrlRole = Qt.ItemDataRole.UserRole + 10
    IndexRole = Qt.ItemDataRole.UserRole + 11
    SelectedRole = Qt.ItemDataRole.UserRole + 12

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._entries: list[BatchEntry] = []
        self._selected_index = -1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._entries)

    @Property(int, notify=selectedIndexChanged)
    def selectedIndex(self) -> int:
        return self._selected_index

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._entries)):
            return None
        entry = self._entries[index.row()]
        mapping = {
            self.FileNameRole: entry.file_name,
            self.InputPathRole: entry.input_path,
            self.OutputPathRole: entry.output_path,
            self.StateRole: entry.state,
            self.ProgressRole: entry.progress,
            self.DetailRole: entry.detail,
            self.ElapsedSecondsRole: entry.elapsed_seconds,
            self.InputDimensionsRole: entry.input_dimensions,
            self.OutputDimensionsRole: entry.output_dimensions,
            self.ThumbnailUrlRole: entry.thumbnail_url,
            self.IndexRole: entry.index,
            self.SelectedRole: entry.selected,
        }
        return mapping.get(role)

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.FileNameRole: QByteArray(b"fileName"),
            self.InputPathRole: QByteArray(b"inputPath"),
            self.OutputPathRole: QByteArray(b"outputPath"),
            self.StateRole: QByteArray(b"state"),
            self.ProgressRole: QByteArray(b"progress"),
            self.DetailRole: QByteArray(b"detail"),
            self.ElapsedSecondsRole: QByteArray(b"elapsedSeconds"),
            self.InputDimensionsRole: QByteArray(b"inputDimensions"),
            self.OutputDimensionsRole: QByteArray(b"outputDimensions"),
            self.ThumbnailUrlRole: QByteArray(b"thumbnailUrl"),
            self.IndexRole: QByteArray(b"itemIndex"),
            self.SelectedRole: QByteArray(b"selected"),
        }

    @Slot(list)
    def set_items(self, paths: list[str]) -> None:
        self.beginResetModel()
        self._entries = [BatchEntry(index=i, input_path=p) for i, p in enumerate(paths) if p and Path(p).is_file()]
        self._selected_index = 0 if self._entries else -1
        if self._selected_index >= 0:
            self._entries[0].selected = True
        self.endResetModel()
        self.countChanged.emit()
        self.selectedIndexChanged.emit()

    @Slot(list)
    def add_items(self, paths: list[str]) -> None:
        existing_paths = {str(Path(e.input_path).resolve()).lower() for e in self._entries}
        new_paths: list[str] = []
        for p in paths:
            if not p or not Path(p).is_file():
                continue
            key = str(Path(p).resolve()).lower()
            if key not in existing_paths:
                existing_paths.add(key)
                new_paths.append(p)
        if not new_paths:
            return
        start = len(self._entries)
        self.beginInsertRows(QModelIndex(), start, start + len(new_paths) - 1)
        for i, path in enumerate(new_paths):
            self._entries.append(BatchEntry(index=start + i, input_path=path))
        self.endInsertRows()
        self.countChanged.emit()
        if self._selected_index < 0:
            self.select(0)

    @Slot(int)
    def select(self, row: int) -> None:
        if not (0 <= row < len(self._entries)):
            return
        old = self._selected_index
        if old == row:
            return
        self._selected_index = row
        if 0 <= old < len(self._entries):
            self._entries[old].selected = False
            idx = self.index(old)
            self.dataChanged.emit(idx, idx, [self.SelectedRole])
        self._entries[row].selected = True
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [self.SelectedRole])
        self.selectedIndexChanged.emit()

    @Slot(int)
    def remove_item(self, row: int) -> None:
        if not (0 <= row < len(self._entries)):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        self._entries.pop(row)
        for i, e in enumerate(self._entries):
            e.index = i
        self.endRemoveRows()
        if not self._entries:
            new_selected = -1
        elif self._selected_index == row:
            new_selected = min(row, len(self._entries) - 1)
        elif self._selected_index > row:
            new_selected = self._selected_index - 1
        else:
            new_selected = self._selected_index
        for e in self._entries:
            e.selected = False
        self._selected_index = new_selected
        if new_selected >= 0:
            self._entries[new_selected].selected = True
            idx = self.index(new_selected)
            self.dataChanged.emit(idx, idx, [self.SelectedRole])
        self.countChanged.emit()
        self.selectedIndexChanged.emit()

    @Slot()
    def clear(self) -> None:
        if not self._entries:
            return
        self.beginResetModel()
        self._entries.clear()
        self._selected_index = -1
        self.endResetModel()
        self.countChanged.emit()
        self.selectedIndexChanged.emit()

    def get_paths(self) -> list[str]:
        return [e.input_path for e in self._entries]

    def selected_path(self) -> str | None:
        if 0 <= self._selected_index < len(self._entries):
            return self._entries[self._selected_index].input_path
        return None

    def update_metadata(self, row: int, *, input_dimensions: str | None = None,
                        output_dimensions: str | None = None, thumbnail_url: str | None = None) -> None:
        if not (0 <= row < len(self._entries)):
            return
        entry = self._entries[row]
        roles: list[int] = []
        if input_dimensions is not None:
            entry.input_dimensions = input_dimensions
            roles.append(self.InputDimensionsRole)
        if output_dimensions is not None:
            entry.output_dimensions = output_dimensions
            roles.append(self.OutputDimensionsRole)
        if thumbnail_url is not None:
            entry.thumbnail_url = thumbnail_url
            roles.append(self.ThumbnailUrlRole)
        if roles:
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, roles)

    def update_item_progress(self, index: int, state: str, progress: float, detail: str = "",
                             output_path: str = "", elapsed_seconds: float = 0.0) -> None:
        if not (0 <= index < len(self._entries)):
            return
        state_aliases = {"Processing": "Running", "Complete": "Completed", "Canceled": "Cancelled"}
        state = state_aliases.get(state, state)
        entry = self._entries[index]
        entry.state = state
        entry.progress = max(0.0, min(1.0, float(progress)))
        if detail:
            entry.detail = detail
        if output_path:
            entry.output_path = output_path
        if elapsed_seconds >= 0:
            entry.elapsed_seconds = elapsed_seconds
        idx = self.index(index)
        self.dataChanged.emit(idx, idx, [self.StateRole, self.ProgressRole, self.DetailRole,
                                         self.OutputPathRole, self.ElapsedSecondsRole])


    @Slot()
    def clear_completed(self) -> None:
        remove = [i for i, e in enumerate(self._entries) if e.state in {"Completed", "CompletedWithWarnings", "Cancelled"}]
        if not remove:
            return
        keep = [e.input_path for i, e in enumerate(self._entries) if i not in set(remove)]
        self.set_items(keep)

    @Slot()
    def retry_failed(self) -> None:
        changed = False
        for row, entry in enumerate(self._entries):
            if entry.state in {"Failed", "Cancelled"}:
                entry.state = "Queued"
                entry.progress = 0.0
                entry.detail = ""
                entry.output_path = ""
                entry.elapsed_seconds = 0.0
                idx = self.index(row)
                self.dataChanged.emit(idx, idx, [self.StateRole, self.ProgressRole, self.DetailRole, self.OutputPathRole, self.ElapsedSecondsRole])
                changed = True
        if changed and self._selected_index < 0 and self._entries:
            self.select(0)

    def reset_all_states(self) -> None:
        if not self._entries:
            return
        for e in self._entries:
            e.state = "Queued"
            e.progress = 0.0
            e.detail = ""
            e.output_path = ""
            e.elapsed_seconds = 0.0
        self.dataChanged.emit(self.index(0), self.index(len(self._entries) - 1),
                              [self.StateRole, self.ProgressRole, self.DetailRole,
                               self.OutputPathRole, self.ElapsedSecondsRole])
