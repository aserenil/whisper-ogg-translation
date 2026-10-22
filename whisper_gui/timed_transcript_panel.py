from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from whisper_gui.segments import Segment, segment_at


class TimedTranscriptPanel(QWidget):
    seek_requested = Signal(int)
    line_activated = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._segments: list[Segment] = []

        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)

        self._plain_text_note = QLabel("No timing data — re-run to enable highlighting.")
        self._plain_text_edit = QPlainTextEdit()
        self._plain_text_edit.setReadOnly(True)

        plain_text_page = QWidget()
        plain_text_layout = QVBoxLayout(plain_text_page)
        plain_text_layout.addWidget(self._plain_text_note)
        plain_text_layout.addWidget(self._plain_text_edit)

        self._stack = QStackedWidget()
        self._stack.addWidget(self.list_widget)
        self._stack.addWidget(plain_text_page)

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)

    def set_segments(self, segments: list[Segment]) -> None:
        self._segments = segments
        self.list_widget.clear()
        for segment in segments:
            self.list_widget.addItem(segment.text)
        self._stack.setCurrentWidget(self.list_widget)

    def set_plain_text(self, text: str) -> None:
        self._segments = []
        self._plain_text_edit.setPlainText(text)
        self._stack.setCurrentWidget(self._plain_text_edit.parentWidget())

    def update_position(self, position_ms: int) -> None:
        if not self._segments:
            return
        index = segment_at(self._segments, position_ms)
        self.list_widget.setCurrentRow(index if index is not None else -1)

    def clear(self) -> None:
        self._segments = []
        self.list_widget.clear()

    def _on_item_clicked(self, item) -> None:
        index = self.list_widget.row(item)
        segment = self._segments[index]
        self.seek_requested.emit(segment.start_ms)
        self.line_activated.emit(segment.start_ms, segment.end_ms)
