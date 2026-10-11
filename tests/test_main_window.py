import time

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from whisper_gui import worker as worker_module
from whisper_gui.main_window import MainWindow


class _SlowModel:
    def transcribe(self, path, task):
        time.sleep(0.2)
        return {"text": "x"}


def test_close_event_stops_running_worker_before_accepting(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(worker_module, "get_model", lambda: _SlowModel())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)

    window = MainWindow()
    a = tmp_path / "a.ogg"
    b = tmp_path / "b.ogg"
    a.write_bytes(b"fake")
    b.write_bytes(b"fake")
    window.queue_model.add(a)
    window.queue_model.add(b)
    window._start_batch()

    for _ in range(100):
        if window.worker is not None and window.worker.isRunning():
            break
        time.sleep(0.01)
    assert window.worker is not None
    assert window.worker.isRunning()

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted()
    assert window.worker.isRunning() is False
