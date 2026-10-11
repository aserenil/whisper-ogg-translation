from whisper_gui.transcription import (
    output_paths,
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
            return {"text": " hola mundo "}
        return {"text": " hello world "}


def test_transcribe_original_strips_text_and_uses_transcribe_task(tmp_path):
    model = _FakeWhisperModel()
    path = tmp_path / "voice.ogg"
    result = transcribe_original(model, path)
    assert result == "hola mundo"
    assert model.calls == [(str(path), "transcribe")]


def test_translate_to_english_strips_text_and_uses_translate_task(tmp_path):
    model = _FakeWhisperModel()
    path = tmp_path / "voice.ogg"
    result = translate_to_english(model, path)
    assert result == "hello world"
    assert model.calls == [(str(path), "translate")]


def test_output_paths_handles_filenames_with_spaces_and_multiple_dots(tmp_path):
    source = tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.ogg"
    original_path, english_path = output_paths(source)
    assert original_path == tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.txt"
    assert english_path == tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.en.txt"


def test_save_transcripts_writes_both_files(tmp_path):
    source = tmp_path / "voice.ogg"
    original_path, english_path = save_transcripts(source, "hola", "hello")
    assert original_path.read_text(encoding="utf-8") == "hola"
    assert english_path.read_text(encoding="utf-8") == "hello"


def test_save_transcripts_backs_up_existing_files_instead_of_destroying_them(tmp_path):
    source = tmp_path / "voice.ogg"
    existing_original = tmp_path / "voice.txt"
    existing_english = tmp_path / "voice.en.txt"
    existing_original.write_text("pre-existing notes", encoding="utf-8")
    existing_english.write_text("pre-existing english notes", encoding="utf-8")

    save_transcripts(source, "hola", "hello")

    assert (tmp_path / "voice.txt").read_text(encoding="utf-8") == "hola"
    assert (tmp_path / "voice.en.txt").read_text(encoding="utf-8") == "hello"
    assert (tmp_path / "voice.txt.bak").read_text(encoding="utf-8") == "pre-existing notes"
    assert (tmp_path / "voice.en.txt.bak").read_text(encoding="utf-8") == "pre-existing english notes"
