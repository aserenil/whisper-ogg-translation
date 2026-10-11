from pathlib import Path

import pytest

from whisper_gui.audio_formats import is_supported, validate_path


def test_is_supported_recognizes_ogg_case_insensitively():
    assert is_supported(Path("voice.OGG")) is True


def test_is_supported_rejects_unknown_extension():
    assert is_supported(Path("notes.txt")) is False


def test_validate_path_rejects_empty_input():
    with pytest.raises(ValueError, match="No file path given"):
        validate_path("   ")


def test_validate_path_rejects_missing_file(tmp_path):
    missing = tmp_path / "missing.ogg"
    with pytest.raises(ValueError, match="File not found"):
        validate_path(str(missing))


def test_validate_path_rejects_unsupported_extension(tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported file type"):
        validate_path(str(text_file))


def test_validate_path_accepts_supported_existing_file(tmp_path):
    audio_file = tmp_path / "voice.ogg"
    audio_file.write_bytes(b"fake audio bytes")
    result = validate_path(str(audio_file))
    assert result == audio_file
