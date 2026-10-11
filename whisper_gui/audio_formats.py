from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".wma",
    ".mp4", ".mov", ".mkv", ".webm",
}

FILE_DIALOG_FILTER = (
    "Audio/Video Files (*.wav *.mp3 *.m4a *.ogg *.opus *.flac *.aac *.wma "
    "*.mp4 *.mov *.mkv *.webm);;All Files (*)"
)


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def validate_path(raw_path: str) -> Path:
    stripped = raw_path.strip()
    if not stripped:
        raise ValueError("No file path given.")
    path = Path(stripped)
    if not path.exists():
        raise ValueError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    if not is_supported(path):
        raise ValueError(f"Unsupported file type: {path.suffix}")
    return path
