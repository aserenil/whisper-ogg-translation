from whisper_gui import worker as worker_module
from whisper_gui.worker import TranscriptionWorker


class _FailingOnBadFileModel:
    def transcribe(self, path, task):
        if "bad" in path and task == "transcribe":
            raise RuntimeError("decode failed")
        if task == "transcribe":
            return {"text": "original text"}
        return {"text": "english text"}


def test_worker_continues_after_one_file_fails(qapp, tmp_path, monkeypatch):
    good_a = tmp_path / "a.ogg"
    bad = tmp_path / "bad.ogg"
    good_b = tmp_path / "b.ogg"
    for path in (good_a, bad, good_b):
        path.write_bytes(b"fake")

    monkeypatch.setattr(worker_module, "get_model", lambda: _FailingOnBadFileModel())

    items = [(0, good_a), (1, bad), (2, good_b)]
    w = TranscriptionWorker(items)

    statuses = []
    errors = []
    results = []
    w.status_changed.connect(lambda i, s: statuses.append((i, s)))
    w.error.connect(lambda i, m: errors.append((i, m)))
    w.result_ready.connect(lambda i, o, e: results.append((i, o, e)))

    w.run()

    assert errors == [(1, "decode failed")]
    assert [i for i, _, _ in results] == [0, 2]
    assert statuses == [
        (0, "Transcribing"), (0, "Translating"), (0, "Done"),
        (1, "Transcribing"), (1, "Error"),
        (2, "Transcribing"), (2, "Translating"), (2, "Done"),
    ]


def test_worker_emits_model_load_failed_and_processes_nothing(qapp, tmp_path, monkeypatch):
    def _raise():
        raise RuntimeError("CUDA not available")

    monkeypatch.setattr(worker_module, "get_model", _raise)

    path = tmp_path / "a.ogg"
    path.write_bytes(b"fake")
    w = TranscriptionWorker([(0, path)])

    failures = []
    results = []
    w.model_load_failed.connect(lambda msg: failures.append(msg))
    w.result_ready.connect(lambda i, o, e: results.append((i, o, e)))

    w.run()

    assert failures == ["CUDA not available"]
    assert results == []
