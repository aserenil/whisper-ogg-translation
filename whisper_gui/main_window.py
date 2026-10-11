from __future__ import annotations

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
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .audio_formats import FILE_DIALOG_FILTER, validate_path
from .queue_model import QueueModel, QueueStatus
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

        self.queue_list = QListWidget()
        self.queue_list.currentRowChanged.connect(self._on_selection_changed)

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start_batch)

        queue_box = QVBoxLayout()
        queue_box.addLayout(top_bar)
        queue_box.addWidget(self.queue_list)
        queue_box.addWidget(self.start_button)

        self.original_panel = QPlainTextEdit()
        self.original_panel.setReadOnly(True)
        self.english_panel = QPlainTextEdit()
        self.english_panel.setReadOnly(True)

        original_copy = QPushButton("Copy")
        original_copy.clicked.connect(lambda: self._copy(self.original_panel))
        english_copy = QPushButton("Copy")
        english_copy.clicked.connect(lambda: self._copy(self.english_panel))

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

        queue_widget = QWidget()
        queue_widget.setLayout(queue_box)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(queue_widget)
        splitter.addWidget(panels_widget)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(splitter)
        self.setCentralWidget(central)

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
        self.queue_model.add(path)
        self.queue_list.addItem(f"{path.name} — {QueueStatus.QUEUED.value}")
        self.address_bar.clear()

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

    def _on_result_ready(self, index: int, original: str, english: str) -> None:
        self.queue_model.set_result(index, original, english)
        if self.queue_list.currentRow() == index:
            self.original_panel.setPlainText(original)
            self.english_panel.setPlainText(english)

    def _on_error(self, index: int, message: str) -> None:
        self.queue_model.set_error(index, message)
        self.queue_list.item(index).setToolTip(message)

    def _on_model_load_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Model failed to load", message)

    def _on_batch_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.worker = None

    def _on_selection_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.queue_model):
            self.original_panel.clear()
            self.english_panel.clear()
            return
        item = self.queue_model[row]
        self.original_panel.setPlainText(item.original_text or "")
        self.english_panel.setPlainText(item.english_text or "")

    @staticmethod
    def _copy(panel: QPlainTextEdit) -> None:
        QGuiApplication.clipboard().setText(panel.toPlainText())

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
