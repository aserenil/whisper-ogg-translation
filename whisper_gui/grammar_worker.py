from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .grammar_analysis import analyze, get_client, save_analysis


class GrammarWorker(QThread):
    status_changed = Signal(int, str)
    result_ready = Signal(int, str)
    error = Signal(int, str)

    def __init__(self, index: int, path: Path, original_text: str, english_text: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.path = path
        self.original_text = original_text
        self.english_text = english_text

    def run(self) -> None:
        self.status_changed.emit(self.index, "Analyzing")
        try:
            client = get_client()
            result = analyze(client, self.original_text, self.english_text)
            save_analysis(self.path, result)
        except Exception as exc:
            self.error.emit(self.index, str(exc))
            self.status_changed.emit(self.index, "Error")
            return
        self.result_ready.emit(self.index, result)
        self.status_changed.emit(self.index, "Done")
