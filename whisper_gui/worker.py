from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .transcription import get_model, save_transcripts, transcribe_original, translate_to_english


class TranscriptionWorker(QThread):
    status_changed = Signal(int, str)
    result_ready = Signal(int, str, object, str, object)
    error = Signal(int, str)
    model_load_failed = Signal(str)

    def __init__(self, items: list[tuple[int, Path]], parent=None):
        super().__init__(parent)
        self.items = items
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            model = get_model()
        except Exception as exc:
            self.model_load_failed.emit(str(exc))
            return

        for index, path in self.items:
            if self._stop_requested:
                break
            self.status_changed.emit(index, "Transcribing")
            try:
                original, original_segments = transcribe_original(model, path)
                self.status_changed.emit(index, "Translating")
                english, english_segments = translate_to_english(model, path)
                save_transcripts(path, original, original_segments, english, english_segments)
            except Exception as exc:
                self.error.emit(index, str(exc))
                self.status_changed.emit(index, "Error")
                continue
            self.result_ready.emit(index, original, original_segments, english, english_segments)
            self.status_changed.emit(index, "Done")
