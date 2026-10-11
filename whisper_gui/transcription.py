from pathlib import Path

import whisper

MODEL_SIZE = "medium"
DEVICE = "cuda"

_model = None


def get_model():
    global _model
    if _model is None:
        _model = whisper.load_model(MODEL_SIZE, device=DEVICE)
    return _model


def transcribe_original(model, path: Path) -> str:
    result = model.transcribe(str(path), task="transcribe")
    return result["text"].strip()


def translate_to_english(model, path: Path) -> str:
    result = model.transcribe(str(path), task="translate")
    return result["text"].strip()


def output_paths(source: Path) -> tuple[Path, Path]:
    original = source.with_suffix(".txt")
    english = source.with_name(source.stem + ".en.txt")
    return original, english


def save_transcripts(source: Path, original: str, english: str) -> tuple[Path, Path]:
    original_path, english_path = output_paths(source)
    original_path.write_text(original, encoding="utf-8")
    english_path.write_text(english, encoding="utf-8")
    return original_path, english_path
