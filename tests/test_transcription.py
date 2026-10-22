from whisper_gui.segments import Segment
from whisper_gui.transcription import (
    load_existing_transcripts,
    output_paths,
    output_srt_paths,
    save_transcripts,
    transcribe_original,
    translate_to_english,
)


class _FakeWhisperModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, path, task):
        self.calls.append((path, task))
        if task == "transcribe":
            return {
                "text": " hola mundo ",
                "segments": [{"start": 0.0, "end": 1.2, "text": " hola mundo "}],
            }
        return {
            "text": " hello world ",
            "segments": [{"start": 0.0, "end": 1.2, "text": " hello world "}],
        }


def test_transcribe_original_returns_text_and_segments(tmp_path):
    model = _FakeWhisperModel()
    path = tmp_path / "voice.ogg"
    text, segments = transcribe_original(model, path)
    assert text == "hola mundo"
    assert segments == [Segment(start_ms=0, end_ms=1200, text="hola mundo")]
    assert model.calls == [(str(path), "transcribe")]


def test_translate_to_english_returns_text_and_segments(tmp_path):
    model = _FakeWhisperModel()
    path = tmp_path / "voice.ogg"
    text, segments = translate_to_english(model, path)
    assert text == "hello world"
    assert segments == [Segment(start_ms=0, end_ms=1200, text="hello world")]


def test_output_paths_handles_filenames_with_spaces_and_multiple_dots(tmp_path):
    source = tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.ogg"
    original_path, english_path = output_paths(source)
    assert original_path == tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.txt"
    assert english_path == tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.en.txt"


def test_output_srt_paths_mirrors_output_paths_naming(tmp_path):
    source = tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.ogg"
    original_srt, english_srt = output_srt_paths(source)
    assert original_srt == tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.srt"
    assert english_srt == tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.en.srt"


def test_save_transcripts_writes_text_and_srt_files(tmp_path):
    source = tmp_path / "voice.ogg"
    original_segs = [Segment(start_ms=0, end_ms=1200, text="hola")]
    english_segs = [Segment(start_ms=0, end_ms=1200, text="hello")]
    original_txt, english_txt, original_srt, english_srt = save_transcripts(
        source, "hola", original_segs, "hello", english_segs
    )
    assert original_txt.read_text(encoding="utf-8") == "hola"
    assert english_txt.read_text(encoding="utf-8") == "hello"
    assert "hola" in original_srt.read_text(encoding="utf-8")
    assert "hello" in english_srt.read_text(encoding="utf-8")


def test_save_transcripts_backs_up_all_four_existing_files(tmp_path):
    source = tmp_path / "voice.ogg"
    for name, content in [
        ("voice.txt", "old txt"), ("voice.en.txt", "old en txt"),
        ("voice.srt", "old srt"), ("voice.en.srt", "old en srt"),
    ]:
        (tmp_path / name).write_text(content, encoding="utf-8")

    segs = [Segment(start_ms=0, end_ms=1200, text="hola")]
    save_transcripts(source, "hola", segs, "hello", segs)

    assert (tmp_path / "voice.txt.bak").read_text(encoding="utf-8") == "old txt"
    assert (tmp_path / "voice.en.txt.bak").read_text(encoding="utf-8") == "old en txt"
    assert (tmp_path / "voice.srt.bak").read_text(encoding="utf-8") == "old srt"
    assert (tmp_path / "voice.en.srt.bak").read_text(encoding="utf-8") == "old en srt"


def test_load_existing_transcripts_returns_none_when_txt_missing(tmp_path):
    assert load_existing_transcripts(tmp_path / "voice.ogg") is None


def test_load_existing_transcripts_loads_text_and_segments_when_srt_present(tmp_path):
    source = tmp_path / "voice.ogg"
    segs = [Segment(start_ms=0, end_ms=1200, text="hola")]
    save_transcripts(source, "hola", segs, "hello", segs)

    loaded = load_existing_transcripts(source)
    assert loaded.original_text == "hola"
    assert loaded.english_text == "hello"
    assert loaded.original_segments == segs
    assert loaded.english_segments == segs


def test_load_existing_transcripts_empty_segments_when_srt_missing(tmp_path):
    source = tmp_path / "voice.ogg"
    (tmp_path / "voice.txt").write_text("hola", encoding="utf-8")
    (tmp_path / "voice.en.txt").write_text("hello", encoding="utf-8")

    loaded = load_existing_transcripts(source)
    assert loaded.original_text == "hola"
    assert loaded.original_segments == []
    assert loaded.english_segments == []


def test_load_existing_transcripts_empty_segments_when_srt_is_undecodable(tmp_path):
    source = tmp_path / "voice.ogg"
    (tmp_path / "voice.txt").write_text("hola", encoding="utf-8")
    (tmp_path / "voice.en.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "voice.srt").write_bytes(b"\xff\xfe\x00\x01not utf-8")

    loaded = load_existing_transcripts(source)
    assert loaded.original_segments == []
