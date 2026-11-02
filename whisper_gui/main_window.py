from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .audio_formats import FILE_DIALOG_FILTER, validate_path
from .media_player import MediaPlayerWidget
from .queue_model import QueueItem, QueueModel, QueueStatus
from .timed_transcript_panel import TimedTranscriptPanel
from .transcription import load_existing_transcripts
from .worker import TranscriptionWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Whisper Dual-Language Transcriber")

        self.queue_model = QueueModel()
        self.worker: TranscriptionWorker | None = None

        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Type or paste an audio file path...")
        self.address_bar.returnPressed.connect(self._add_from_address_bar)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_files)

        add_button = QPushButton("Add to Queue")
        add_button.clicked.connect(self._add_from_address_bar)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self.address_bar)
        top_bar.addWidget(browse_button)
        top_bar.addWidget(add_button)

        self._sort_descending = False
        self.sort_button = QPushButton("Sort: Name A→Z")
        self.sort_button.clicked.connect(self._on_sort_clicked)

        self.queue_list = QListWidget()
        self.queue_list.currentRowChanged.connect(self._on_selection_changed)

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start_batch)

        self.retranscribe_button = QPushButton("Re-transcribe selected")
        self.retranscribe_button.clicked.connect(self._on_retranscribe_clicked)

        queue_box = QVBoxLayout()
        queue_box.addLayout(top_bar)
        queue_box.addWidget(self.sort_button)
        queue_box.addWidget(self.queue_list)
        queue_box.addWidget(self.retranscribe_button)
        queue_box.addWidget(self.start_button)

        sidebar_widget = QWidget()
        sidebar_widget.setLayout(queue_box)

        self.media_player = MediaPlayerWidget()

        self.original_panel = TimedTranscriptPanel()
        self.english_panel = TimedTranscriptPanel()

        original_copy = QPushButton("Copy")
        original_copy.clicked.connect(
            lambda: self._copy_current(lambda item: item.original_text)
        )
        english_copy = QPushButton("Copy")
        english_copy.clicked.connect(
            lambda: self._copy_current(lambda item: item.english_text)
        )

        original_header = QHBoxLayout()
        original_header.addWidget(QLabel("Original language"))
        original_header.addWidget(original_copy)
        original_box = QVBoxLayout()
        original_box.addLayout(original_header)
        original_box.addWidget(self.original_panel)

        english_header = QHBoxLayout()
        english_header.addWidget(QLabel("English"))
        english_header.addWidget(english_copy)
        english_box = QVBoxLayout()
        english_box.addLayout(english_header)
        english_box.addWidget(self.english_panel)

        original_widget = QWidget()
        original_widget.setLayout(original_box)
        english_widget = QWidget()
        english_widget.setLayout(english_box)

        panels_widget = QWidget()
        panels_layout = QHBoxLayout(panels_widget)
        panels_layout.addWidget(original_widget)
        panels_layout.addWidget(english_widget)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(self.media_player)
        right_splitter.addWidget(panels_widget)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(sidebar_widget)
        main_splitter.addWidget(right_splitter)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(main_splitter)
        self.setCentralWidget(central)

        self.media_player.position_changed.connect(self.original_panel.update_position)
        self.media_player.position_changed.connect(self.english_panel.update_position)
        self.original_panel.seek_requested.connect(self.media_player.seek)
        self.english_panel.seek_requested.connect(self.media_player.seek)
        self.original_panel.line_activated.connect(self.media_player.set_repeat_target)

    def _add_from_address_bar(self) -> None:
        self._add_path(self.address_bar.text())

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select audio files", "", FILE_DIALOG_FILTER
        )
        for raw_path in paths:
            self._add_path(raw_path)

    def _add_path(self, raw_path: str) -> None:
        try:
            path = validate_path(raw_path)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot add file", str(exc))
            return
        index = self.queue_model.add(path)

        try:
            loaded = load_existing_transcripts(path)
        except Exception:
            loaded = None

        if loaded is not None:
            self.queue_model.set_result(
                index,
                loaded.original_text,
                loaded.original_segments,
                loaded.english_text,
                loaded.english_segments,
            )
            self.queue_list.addItem(f"{path.name} — {QueueStatus.DONE.value}")
        else:
            self.queue_list.addItem(f"{path.name} — {QueueStatus.QUEUED.value}")

        self.address_bar.clear()

    def _on_sort_clicked(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(
                self,
                "Cannot sort",
                "Cannot reorder the queue while transcription is running.",
            )
            return

        current_row = self.queue_list.currentRow()
        selected_path = self.queue_model[current_row].path if current_row >= 0 else None

        self.queue_model.sort_by_name(descending=self._sort_descending)
        self._sort_descending = not self._sort_descending
        self.sort_button.setText(
            "Sort: Name Z→A" if self._sort_descending else "Sort: Name A→Z"
        )

        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        for i in range(len(self.queue_model)):
            item = self.queue_model[i]
            self.queue_list.addItem(f"{item.path.name} — {item.status.value}")
        if selected_path is not None:
            for i in range(len(self.queue_model)):
                if self.queue_model[i].path == selected_path:
                    self.queue_list.setCurrentRow(i)
                    break
        self.queue_list.blockSignals(False)

    def _on_retranscribe_clicked(self) -> None:
        row = self.queue_list.currentRow()
        if row < 0:
            return
        self.queue_model.set_status(row, QueueStatus.QUEUED)
        path = self.queue_model[row].path
        self.queue_list.item(row).setText(f"{path.name} — {QueueStatus.QUEUED.value}")

    def _start_batch(self) -> None:
        pending = self.queue_model.pending_items()
        if not pending:
            QMessageBox.information(self, "Nothing to do", "No queued files to process.")
            return
        self.start_button.setEnabled(False)
        self.worker = TranscriptionWorker(pending)
        self.worker.status_changed.connect(self._on_status_changed)
        self.worker.result_ready.connect(self._on_result_ready)
        self.worker.error.connect(self._on_error)
        self.worker.model_load_failed.connect(self._on_model_load_failed)
        self.worker.finished.connect(self._on_batch_finished)
        self.worker.start()

    def _on_status_changed(self, index: int, status: str) -> None:
        self.queue_model.set_status(index, QueueStatus(status))
        item = self.queue_list.item(index)
        path = self.queue_model[index].path
        item.setText(f"{path.name} — {status}")

    def _on_result_ready(
        self, index: int, original: str, original_segments, english: str, english_segments
    ) -> None:
        self.queue_model.set_result(index, original, original_segments, english, english_segments)
        if self.queue_list.currentRow() == index:
            self._populate_panels(self.queue_model[index])

    def _on_error(self, index: int, message: str) -> None:
        self.queue_model.set_error(index, message)
        self.queue_list.item(index).setToolTip(message)

    def _on_model_load_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Model failed to load", message)

    def _on_batch_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.worker = None

    def _populate_panels(self, item: QueueItem) -> None:
        if item.original_segments:
            self.original_panel.set_segments(item.original_segments)
        else:
            self.original_panel.set_plain_text(item.original_text or "")

        if item.english_segments:
            self.english_panel.set_segments(item.english_segments)
        else:
            self.english_panel.set_plain_text(item.english_text or "")

    def _on_selection_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.queue_model):
            self.original_panel.clear()
            self.english_panel.clear()
            self.media_player.stop()
            return
        item = self.queue_model[row]
        self._populate_panels(item)
        self.media_player.load(item.path)

    def _copy_current(self, getter: Callable[[QueueItem], str | None]) -> None:
        row = self.queue_list.currentRow()
        if row < 0:
            return
        QGuiApplication.clipboard().setText(getter(self.queue_model[row]) or "")

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            response = QMessageBox.question(
                self,
                "Transcription in progress",
                "A batch is still running. Quit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.request_stop()
            self.worker.wait()
        event.accept()
