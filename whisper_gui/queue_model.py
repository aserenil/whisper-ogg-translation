from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class QueueStatus(Enum):
    QUEUED = "Queued"
    TRANSCRIBING = "Transcribing"
    TRANSLATING = "Translating"
    DONE = "Done"
    ERROR = "Error"


@dataclass
class QueueItem:
    path: Path
    status: QueueStatus = QueueStatus.QUEUED
    original_text: str | None = None
    english_text: str | None = None
    error_message: str | None = None


class QueueModel:
    def __init__(self) -> None:
        self._items: list[QueueItem] = []

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> QueueItem:
        return self._items[index]

    def add(self, path: Path) -> int:
        self._items.append(QueueItem(path=path))
        return len(self._items) - 1

    def set_status(self, index: int, status: QueueStatus) -> None:
        self._items[index].status = status

    def set_result(self, index: int, original: str, english: str) -> None:
        item = self._items[index]
        item.original_text = original
        item.english_text = english
        item.status = QueueStatus.DONE

    def set_error(self, index: int, message: str) -> None:
        item = self._items[index]
        item.error_message = message
        item.status = QueueStatus.ERROR

    def pending_items(self) -> list[tuple[int, Path]]:
        return [
            (i, item.path)
            for i, item in enumerate(self._items)
            if item.status == QueueStatus.QUEUED
        ]
