from dataclasses import dataclass
from pathlib import Path

import whisper

from whisper_gui.segments import Segment, parse_srt, segments_to_srt

MODEL_SIZE = "medium"
DEVICE = "cuda"

_model = None


def get_model():
    global _model
    if _model is None:
        _model = whisper.load_model(MODEL_SIZE, device=DEVICE)
    return _model


def _segments_from_result(result) -> list[Segment]:
    return [
        Segment(
            start_ms=round(s["start"] * 1000),
            end_ms=round(s["end"] * 1000),
            text=s["text"].strip(),
        )
        for s in result["segments"]
    ]


def transcribe_original(model, path: Path) -> tuple[str, list[Segment]]:
    result = model.transcribe(str(path), task="transcribe")
    return result["text"].strip(), _segments_from_result(result)


def translate_to_english(model, path: Path) -> tuple[str, list[Segment]]:
    result = model.transcribe(str(path), task="translate")
    return result["text"].strip(), _segments_from_result(result)


def output_paths(source: Path) -> tuple[Path, Path]:
    original = source.with_suffix(".txt")
    english = source.with_name(source.stem + ".en.txt")
    return original, english


def output_srt_paths(source: Path) -> tuple[Path, Path]:
    original = source.with_suffix(".srt")
    english = source.with_name(source.stem + ".en.srt")
    return original, english


def _backup_if_exists(path: Path) -> None:
    if path.exists():
        path.replace(path.with_name(path.name + ".bak"))


def save_transcripts(
    source: Path,
    original: str,
    original_segments: list[Segment],
    english: str,
    english_segments: list[Segment],
) -> tuple[Path, Path, Path, Path]:
    original_path, english_path = output_paths(source)
    original_srt_path, english_srt_path = output_srt_paths(source)

    for path in (original_path, english_path, original_srt_path, english_srt_path):
        _backup_if_exists(path)

    original_path.write_text(original, encoding="utf-8")
    english_path.write_text(english, encoding="utf-8")
    original_srt_path.write_text(segments_to_srt(original_segments), encoding="utf-8")
    english_srt_path.write_text(segments_to_srt(english_segments), encoding="utf-8")

    return original_path, english_path, original_srt_path, english_srt_path


@dataclass
class LoadedTranscript:
    original_text: str
    original_segments: list[Segment]
    english_text: str
    english_segments: list[Segment]


def _load_segments(path: Path) -> list[Segment]:
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    return parse_srt(content)


def load_existing_transcripts(source: Path) -> LoadedTranscript | None:
    original_path, english_path = output_paths(source)
    if not original_path.exists() or not english_path.exists():
        return None

    original_srt_path, english_srt_path = output_srt_paths(source)
    return LoadedTranscript(
        original_text=original_path.read_text(encoding="utf-8"),
        original_segments=_load_segments(original_srt_path),
        english_text=english_path.read_text(encoding="utf-8"),
        english_segments=_load_segments(english_srt_path),
    )
