import time
from types import SimpleNamespace

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from whisper_gui import grammar_worker as grammar_worker_module
from whisper_gui import worker as worker_module
from whisper_gui.main_window import MainWindow
from whisper_gui.media_player import MediaPlayerWidget
from whisper_gui.queue_model import QueueStatus
from whisper_gui.segments import Segment
from whisper_gui.transcription import save_transcripts


class _SlowModel:
    def transcribe(self, path, task):
        time.sleep(0.2)
        return {"text": "x", "segments": []}


class _FakeGrammarMessages:
    def create(self, **kwargs):
        return SimpleNamespace(content=[SimpleNamespace(text="# Analysis")], stop_reason="end_turn")


class _FakeGrammarClient:
    def __init__(self):
        self.messages = _FakeGrammarMessages()


class _SlowGrammarMessages:
    def create(self, **kwargs):
        time.sleep(0.2)
        return SimpleNamespace(content=[SimpleNamespace(text="# Analysis")], stop_reason="end_turn")


class _SlowGrammarClient:
    def __init__(self):
        self.messages = _SlowGrammarMessages()


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


def test_selecting_a_row_loads_existing_transcript_without_queuing(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    segs = [Segment(start_ms=0, end_ms=1000, text="hola")]
    save_transcripts(source, "hola", segs, "hello", segs)

    window = MainWindow()
    window._add_path(str(source))

    assert window.queue_model[0].status.value == "Done"
    assert window.queue_model[0].original_segments == segs
    assert window.queue_model.pending_items() == []


def test_selecting_a_row_loads_its_file_into_the_media_player(qapp, tmp_path, monkeypatch):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")

    window = MainWindow()
    loaded_paths = []
    monkeypatch.setattr(window.media_player, "load", lambda path: loaded_paths.append(path))
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)

    assert loaded_paths == [source]


def test_selecting_a_different_row_stops_the_previous_media(qapp, tmp_path, monkeypatch):
    a = tmp_path / "a.ogg"
    b = tmp_path / "b.ogg"
    a.write_bytes(b"fake")
    b.write_bytes(b"fake")

    window = MainWindow()
    load_calls = []
    monkeypatch.setattr(window.media_player, "load", lambda path: load_calls.append(path))
    window._add_path(str(a))
    window._add_path(str(b))

    window.queue_list.setCurrentRow(0)
    window.queue_list.setCurrentRow(1)

    assert load_calls == [a, b]


def test_result_ready_populates_independent_timed_panels_for_the_selected_row(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")

    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)

    # Two independent Whisper passes: different segment counts and timings.
    original_segs = [
        Segment(start_ms=0, end_ms=1000, text="hola"),
        Segment(start_ms=1000, end_ms=2000, text="mundo"),
    ]
    english_segs = [Segment(start_ms=0, end_ms=2000, text="hello world")]
    window._on_result_ready(0, "hola mundo", original_segs, "hello world", english_segs)

    assert window.original_panel.list_widget.count() == 2
    assert window.english_panel.list_widget.count() == 1
    window.media_player.position_changed.emit(1500)
    assert window.original_panel.list_widget.currentRow() == 1
    assert window.english_panel.list_widget.currentRow() == 0


def test_selecting_row_with_only_txt_falls_back_to_plain_text(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    (tmp_path / "voice.txt").write_text("hola", encoding="utf-8")
    (tmp_path / "voice.en.txt").write_text("hello", encoding="utf-8")

    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)

    assert window.original_panel.list_widget.count() == 0
    assert window.english_panel.list_widget.count() == 0


def test_clicking_retranscribe_requeues_the_selected_done_row(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    (tmp_path / "voice.txt").write_text("hola", encoding="utf-8")
    (tmp_path / "voice.en.txt").write_text("hello", encoding="utf-8")

    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    assert window.queue_model[0].status == QueueStatus.DONE

    window._on_retranscribe_clicked()

    assert window.queue_model[0].status == QueueStatus.QUEUED
    assert window.queue_model.pending_items() == [(0, source)]
    assert window.queue_list.item(0).text() == f"{source.name} — Queued"


def test_retranscribe_noops_when_no_row_selected(qapp, tmp_path):
    window = MainWindow()
    window._on_retranscribe_clicked()


def test_clicking_sort_toggles_name_order_ascending_then_descending(qapp, tmp_path):
    banana = tmp_path / "banana.ogg"
    apple = tmp_path / "apple.ogg"
    banana.write_bytes(b"fake")
    apple.write_bytes(b"fake")

    window = MainWindow()
    window._add_path(str(banana))
    window._add_path(str(apple))

    window._on_sort_clicked()
    assert [window.queue_list.item(i).text().split(" — ")[0] for i in range(2)] == [
        "apple.ogg", "banana.ogg",
    ]

    window._on_sort_clicked()
    assert [window.queue_list.item(i).text().split(" — ")[0] for i in range(2)] == [
        "banana.ogg", "apple.ogg",
    ]


def test_sorting_preserves_selection_by_file_not_row_index(qapp, tmp_path):
    banana = tmp_path / "banana.ogg"
    apple = tmp_path / "apple.ogg"
    banana.write_bytes(b"fake")
    apple.write_bytes(b"fake")

    window = MainWindow()
    window._add_path(str(banana))
    window._add_path(str(apple))
    window.queue_list.setCurrentRow(0)

    window._on_sort_clicked()

    assert window.queue_list.currentRow() == 1
    assert window.queue_model[window.queue_list.currentRow()].path == banana


def test_sort_click_while_batch_running_does_not_reorder(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(worker_module, "get_model", lambda: _SlowModel())

    banana = tmp_path / "banana.ogg"
    apple = tmp_path / "apple.ogg"
    banana.write_bytes(b"fake")
    apple.write_bytes(b"fake")

    window = MainWindow()
    window._add_path(str(banana))
    window._add_path(str(apple))
    window._start_batch()

    for _ in range(100):
        if window.worker is not None and window.worker.isRunning():
            break
        time.sleep(0.01)
    assert window.worker.isRunning()

    window._on_sort_clicked()

    assert window.queue_model[0].path == banana
    assert window.queue_model[1].path == apple

    window.worker.request_stop()
    window.worker.wait()


def test_add_path_still_adds_row_when_existing_transcript_load_raises(qapp, tmp_path, monkeypatch):
    import whisper_gui.main_window as main_window_module

    def _raise(path):
        raise RuntimeError("corrupt srt")

    monkeypatch.setattr(main_window_module, "load_existing_transcripts", _raise)

    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")

    window = MainWindow()
    window._add_path(str(source))

    assert len(window.queue_model) == 1
    assert window.queue_list.count() == 1
    assert window.queue_model[0].status == window.queue_model[0].status.QUEUED


def test_clicking_original_line_sets_repeat_target_on_player(qapp, tmp_path, monkeypatch):
    # `line_activated.connect(self.media_player.set_repeat_target)` in MainWindow.__init__
    # captures a bound method at connect time, so patching the instance *after*
    # construction would not be seen by that connection — patch the class first.
    targets = []
    monkeypatch.setattr(
        MediaPlayerWidget, "set_repeat_target",
        lambda self, s, e: targets.append((s, e)),
    )

    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")

    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)

    segs = [Segment(start_ms=0, end_ms=1000, text="hola")]
    window._on_result_ready(0, "hola", segs, "hello", segs)

    window.original_panel._on_item_clicked(window.original_panel.list_widget.item(0))

    assert targets == [(0, 1000)]


def test_main_window_has_a_grammar_tab_beside_the_transcript_tab(qapp, tmp_path):
    window = MainWindow()
    assert window.content_tabs.count() == 2
    assert window.content_tabs.tabText(0) == "Transcript"
    assert window.content_tabs.tabText(1) == "Grammar"


def test_analyze_disabled_for_a_row_that_is_not_done(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    assert window.grammar_panel.analyze_button.isEnabled() is False


def test_clicking_analyze_noops_for_a_row_that_is_not_done(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_analyze_clicked()
    assert window.grammar_worker is None


def test_clicking_analyze_on_a_done_row_runs_the_worker_and_updates_model_and_panel(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(grammar_worker_module, "get_client", lambda: _FakeGrammarClient())
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])

    window._on_analyze_clicked()
    assert window.grammar_worker is not None
    window.grammar_worker.wait()
    qapp.processEvents()

    assert window.queue_model[0].grammar_text == "# Analysis"
    assert "Analysis" in window.grammar_panel.result_view.toPlainText()


def test_declining_the_reanalyze_confirmation_does_not_start_a_worker(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])
    window.queue_model.set_grammar(0, "# Old analysis")

    window._on_analyze_clicked()

    assert window.grammar_worker is None


def test_accepting_the_reanalyze_confirmation_starts_a_new_worker(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(grammar_worker_module, "get_client", lambda: _FakeGrammarClient())
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])
    window.queue_model.set_grammar(0, "# Old analysis")

    window._on_analyze_clicked()

    assert window.grammar_worker is not None
    window.grammar_worker.wait()


def test_grammar_error_shows_in_status_line_and_nothing_is_saved(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])

    window._on_grammar_error(0, "rate limit exceeded")

    assert window.grammar_panel.status_label.text() == "rate limit exceeded"
    assert window.queue_model[0].grammar_text is None


def test_close_event_waits_for_a_running_grammar_worker_before_accepting(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(grammar_worker_module, "get_client", lambda: _SlowGrammarClient())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])

    window._on_analyze_clicked()
    for _ in range(100):
        if window.grammar_worker is not None and window.grammar_worker.isRunning():
            break
        time.sleep(0.01)
    assert window.grammar_worker.isRunning()

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted()
    assert window.grammar_worker.isRunning() is False


def test_add_path_loads_existing_grammar_analysis(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    (tmp_path / "voice.txt").write_text("hola", encoding="utf-8")
    (tmp_path / "voice.en.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "voice.grammar.md").write_text("# Analysis", encoding="utf-8")

    window = MainWindow()
    window._add_path(str(source))

    assert window.queue_model[0].grammar_text == "# Analysis"


def test_add_path_still_adds_row_when_existing_grammar_file_load_raises(qapp, tmp_path, monkeypatch):
    import whisper_gui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module, "load_existing_analysis",
        lambda path: (_ for _ in ()).throw(RuntimeError("corrupt")),
    )
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")

    window = MainWindow()
    window._add_path(str(source))

    assert len(window.queue_model) == 1
    assert window.queue_model[0].grammar_text is None


def test_grammar_worker_finishing_does_not_clear_an_error_still_shown_for_that_row(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])

    window._on_grammar_error(0, "rate limit exceeded")
    window._on_grammar_finished()

    assert window.grammar_panel.status_label.text() == "rate limit exceeded"


def test_sort_click_while_grammar_analysis_running_does_not_reorder(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(grammar_worker_module, "get_client", lambda: _SlowGrammarClient())

    banana = tmp_path / "banana.ogg"
    apple = tmp_path / "apple.ogg"
    banana.write_bytes(b"fake")
    apple.write_bytes(b"fake")

    window = MainWindow()
    window._add_path(str(banana))
    window._add_path(str(apple))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])

    window._on_analyze_clicked()
    for _ in range(100):
        if window.grammar_worker is not None and window.grammar_worker.isRunning():
            break
        time.sleep(0.01)
    assert window.grammar_worker.isRunning()

    window._on_sort_clicked()

    assert window.queue_model[0].path == banana
    assert window.queue_model[1].path == apple

    window.grammar_worker.wait()


def test_status_changed_to_done_enables_analyze_for_the_selected_row(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    assert window.grammar_panel.analyze_button.isEnabled() is False

    window._on_status_changed(0, "Done")

    assert window.grammar_panel.analyze_button.isEnabled() is True


def test_retranscribe_disables_analyze_for_the_selected_row(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    (tmp_path / "voice.txt").write_text("hola", encoding="utf-8")
    (tmp_path / "voice.en.txt").write_text("hello", encoding="utf-8")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    assert window.grammar_panel.analyze_button.isEnabled() is True

    window._on_retranscribe_clicked()

    assert window.grammar_panel.analyze_button.isEnabled() is False
