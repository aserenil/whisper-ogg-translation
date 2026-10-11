from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .transcription import get_model, save_transcripts, transcribe_original, translate_to_english


class TranscriptionWorker(QThread):
    status_changed = Signal(int, str)
    result_ready = Signal(int, str, str)
    error = Signal(int, str)
    model_load_failed = Signal(str)

    def __init__(self, items: list[tuple[int, Path]], parent=None):
        super().__init__(parent)
        self.items = items

    def run(self) -> None:
        try:
            model = get_model()
        except Exception as exc:
            self.model_load_failed.emit(str(exc))
            return

        for index, path in self.items:
            self.status_changed.emit(index, "Transcribing")
            try:
                original = transcribe_original(model, path)
                self.status_changed.emit(index, "Translating")
                english = translate_to_english(model, path)
                save_transcripts(path, original, english)
            except Exception as exc:
                self.error.emit(index, str(exc))
                self.status_changed.emit(index, "Error")
                continue
            self.result_ready.emit(index, original, english)
            self.status_changed.emit(index, "Done")
