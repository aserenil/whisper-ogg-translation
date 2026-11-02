from whisper_gui.segments import Segment
from whisper_gui.queue_model import QueueModel, QueueStatus


def test_add_appends_item_with_queued_status(tmp_path):
    model = QueueModel()
    path = tmp_path / "voice.ogg"
    index = model.add(path)
    assert index == 0
    assert len(model) == 1
    assert model[0].status == QueueStatus.QUEUED
    assert model[0].path == path
    assert model[0].original_segments == []
    assert model[0].english_segments == []


def test_set_status_updates_existing_item(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "voice.ogg")
    model.set_status(0, QueueStatus.TRANSCRIBING)
    assert model[0].status == QueueStatus.TRANSCRIBING


def test_set_result_stores_segments(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "voice.ogg")
    original_segs = [Segment(start_ms=0, end_ms=1000, text="hola")]
    english_segs = [Segment(start_ms=0, end_ms=1000, text="hello")]
    model.set_result(0, "hola", original_segs, "hello", english_segs)
    assert model[0].original_segments == original_segs
    assert model[0].english_segments == english_segs


def test_set_result_stores_texts_and_marks_done(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "voice.ogg")
    model.set_result(0, "hola", [], "hello", [])
    assert model[0].original_text == "hola"
    assert model[0].english_text == "hello"
    assert model[0].status == QueueStatus.DONE


def test_set_error_stores_message_and_marks_error(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "voice.ogg")
    model.set_error(0, "decode failed")
    assert model[0].error_message == "decode failed"
    assert model[0].status == QueueStatus.ERROR


def test_pending_items_returns_only_queued_items_with_original_index(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "a.ogg")
    model.add(tmp_path / "b.ogg")
    model.add(tmp_path / "c.ogg")
    model.set_result(0, "a", [], "a-en", [])
    model.set_error(1, "boom")
    pending = model.pending_items()
    assert pending == [(2, model[2].path)]


def test_sort_by_name_orders_items_ascending_case_insensitively(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "Banana.ogg")
    model.add(tmp_path / "apple.ogg")
    model.add(tmp_path / "Cherry.ogg")
    model.sort_by_name()
    assert [model[i].path.name for i in range(len(model))] == [
        "apple.ogg", "Banana.ogg", "Cherry.ogg",
    ]


def test_sort_by_name_descending_reverses_the_order(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "Banana.ogg")
    model.add(tmp_path / "apple.ogg")
    model.add(tmp_path / "Cherry.ogg")
    model.sort_by_name(descending=True)
    assert [model[i].path.name for i in range(len(model))] == [
        "Cherry.ogg", "Banana.ogg", "apple.ogg",
    ]


def test_sort_by_name_preserves_item_data(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "b.ogg")
    model.add(tmp_path / "a.ogg")
    model.set_result(0, "hola", [], "hello", [])
    model.sort_by_name()
    assert model[0].path.name == "a.ogg"
    assert model[0].status == QueueStatus.QUEUED
    assert model[1].path.name == "b.ogg"
    assert model[1].original_text == "hola"
    assert model[1].status == QueueStatus.DONE
