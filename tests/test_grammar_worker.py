from types import SimpleNamespace

from whisper_gui import grammar_worker as grammar_worker_module
from whisper_gui.grammar_worker import GrammarWorker


class _FakeMessages:
    def create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="# Analysis")], stop_reason="end_turn"
        )


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


def test_worker_saves_result_and_emits_it_on_success(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(grammar_worker_module, "get_client", lambda: _FakeClient())
    path = tmp_path / "voice.ogg"
    w = GrammarWorker(0, path, "hola", "hello")
    statuses, results = [], []
    w.status_changed.connect(lambda i, s: statuses.append((i, s)))
    w.result_ready.connect(lambda i, text: results.append((i, text)))

    w.run()

    assert results == [(0, "# Analysis")]
    assert statuses == [(0, "Analyzing"), (0, "Done")]
    assert (tmp_path / "voice.grammar.md").read_text(encoding="utf-8") == "# Analysis"


def test_worker_emits_error_and_saves_nothing_when_client_construction_fails(qapp, tmp_path, monkeypatch):
    def _raise():
        raise RuntimeError("missing API key")

    monkeypatch.setattr(grammar_worker_module, "get_client", _raise)
    path = tmp_path / "voice.ogg"
    w = GrammarWorker(0, path, "hola", "hello")
    errors, statuses = [], []
    w.error.connect(lambda i, m: errors.append((i, m)))
    w.status_changed.connect(lambda i, s: statuses.append((i, s)))

    w.run()

    assert errors == [(0, "missing API key")]
    assert statuses == [(0, "Analyzing"), (0, "Error")]
    assert not (tmp_path / "voice.grammar.md").exists()


def test_worker_emits_error_and_saves_nothing_when_text_is_too_long(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(grammar_worker_module, "get_client", lambda: _FakeClient())
    path = tmp_path / "voice.ogg"
    long_text = "x" * 200_000
    w = GrammarWorker(0, path, long_text, "")
    errors = []
    w.error.connect(lambda i, m: errors.append((i, m)))

    w.run()

    assert len(errors) == 1 and errors[0][0] == 0
    assert not (tmp_path / "voice.grammar.md").exists()
