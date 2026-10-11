# Whisper Dual-Language Transcription GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PySide6 desktop app that transcribes audio files with Whisper, showing the original-language transcript and an English translation side by side, fed by an address-bar-style file picker and a sequential batch queue.

**Architecture:** A `whisper_gui` package split by responsibility — pure-logic modules (`audio_formats`, `queue_model`, `transcription`) that are unit-tested without Qt, a `worker.py` `QThread` that drives the pipeline and is tested with a fake model, and a `main_window.py` that assembles the Qt widgets and is verified manually. `main.py` is the launcher.

**Tech Stack:** Python 3.13, PySide6, openai-whisper, torch (CUDA build), pytest, uv.

**Spec:** `plans/2026-10-11-whisper-gui-transcription-design.md`

## Global Constraints

- Whisper model is fixed at `medium` — no per-run size picker (spec decision).
- Transcription device is CUDA (GPU) — torch must be a CUDA-enabled build, not the CPU-only wheel currently installed.
- The batch queue processes files strictly sequentially — never run two transcriptions concurrently.
- Auto-save writes exactly two files per source: `<stem>.txt` (original language) and `<stem>.en.txt` (English) — no `.srt`/`.vtt`/timestamped output in this version.
- Supported file-picker formats: `.wav .mp3 .m4a .ogg .opus .flac .aac .wma .mp4 .mov .mkv .webm` (plus "All Files"); `ffmpeg` is already on PATH and handles decoding, including WhatsApp's `.ogg`/`.opus` voice notes.
- A single file's transcription failure must not abort the rest of the queue; only a model-load failure blocks the whole batch (shown as a blocking dialog).

## Review Focus

- Empty/whitespace-only path submitted via the address bar must be rejected with a clear message, not silently queued or crash the app.
- A file with an unsupported extension (e.g. a `.txt` picked via "All Files") must be rejected before it ever reaches Whisper.
- A path to a file that doesn't exist (typed by hand, or deleted after being typed) must be rejected with a clear message, not raise an unhandled exception.
- One file in a multi-file batch raising an exception during transcription must not stop the remaining queued files from being processed.
- Filenames containing spaces and multiple dots (e.g. `WhatsApp Ptt 2026-10-07 at 1.19.18 PM.ogg`, matching real WhatsApp export names already in this repo) must produce correctly-named sibling output files, not mangled paths.

---

### Task 1: Project dependencies — CUDA torch, PySide6, pytest

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: a working venv with `torch.cuda.is_available() == True`, `PySide6` importable, `pytest` runnable via `uv run pytest`. All later tasks depend on this.

- [ ] **Step 1: Replace `pyproject.toml` with the dependency set needed for the GUI**

Replace the full file contents with:

```toml
[project]
name = "whisper-ogg-translation"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "openai-whisper>=20250625",
    "torch>=2.4",
    "pyside6>=6.7",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
]

[tool.uv.sources]
torch = [
    { index = "pytorch-cu121" },
]

[[tool.uv.index]]
name = "pytorch-cu121"
url = "https://download.pytorch.org/whl/cu121"
explicit = true

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Sync the environment**

Run: `uv sync`
Expected: completes without error; torch is resolved from the `pytorch-cu121` index (log lines mention `download.pytorch.org`), and `pyside6` + `pytest` are installed.

- [ ] **Step 3: Verify GPU torch is actually in place**

Run: `uv run python -c "import torch; print(torch.cuda.is_available())"`
Expected: prints `True`. If it prints `False`, the CUDA index wasn't picked up — re-check the `[tool.uv.sources]`/`[[tool.uv.index]]` blocks match exactly and re-run `uv sync`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: switch to CUDA torch, add PySide6 and pytest"
```

---

### Task 2: Audio format validation

**Files:**
- Create: `whisper_gui/__init__.py`
- Create: `whisper_gui/audio_formats.py`
- Test: `tests/test_audio_formats.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `is_supported(path: Path) -> bool`, `validate_path(raw_path: str) -> Path` (raises `ValueError` with a user-facing message), `FILE_DIALOG_FILTER: str`. Used by `main_window.py` (Task 6).

- [ ] **Step 1: Create the empty package marker**

Create `whisper_gui/__init__.py` with no content (empty file).

- [ ] **Step 2: Write the failing tests**

Create `tests/test_audio_formats.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_audio_formats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'whisper_gui.audio_formats'`.

- [ ] **Step 4: Implement `audio_formats.py`**

Create `whisper_gui/audio_formats.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_audio_formats.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add whisper_gui/__init__.py whisper_gui/audio_formats.py tests/test_audio_formats.py
git commit -m "feat: add audio file format validation"
```

---

### Task 3: Queue model

**Files:**
- Create: `whisper_gui/queue_model.py`
- Test: `tests/test_queue_model.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `QueueStatus` enum (`QUEUED`, `TRANSCRIBING`, `TRANSLATING`, `DONE`, `ERROR`, with `.value` strings `"Queued"`/`"Transcribing"`/`"Translating"`/`"Done"`/`"Error"`), `QueueItem` dataclass (`path: Path`, `status: QueueStatus`, `original_text: str | None`, `english_text: str | None`, `error_message: str | None`), `QueueModel` with `add(path) -> int`, `set_status(index, status)`, `set_result(index, original, english)`, `set_error(index, message)`, `pending_items() -> list[tuple[int, Path]]`, `__len__`, `__getitem__`. Used by `worker.py` (Task 5) and `main_window.py` (Task 6).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_queue_model.py`:

```python
from whisper_gui.queue_model import QueueModel, QueueStatus


def test_add_appends_item_with_queued_status(tmp_path):
    model = QueueModel()
    path = tmp_path / "voice.ogg"
    index = model.add(path)
    assert index == 0
    assert len(model) == 1
    assert model[0].status == QueueStatus.QUEUED
    assert model[0].path == path


def test_set_status_updates_existing_item(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "voice.ogg")
    model.set_status(0, QueueStatus.TRANSCRIBING)
    assert model[0].status == QueueStatus.TRANSCRIBING


def test_set_result_stores_texts_and_marks_done(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "voice.ogg")
    model.set_result(0, "hola", "hello")
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
    model.set_result(0, "a", "a-en")
    model.set_error(1, "boom")
    pending = model.pending_items()
    assert pending == [(2, model[2].path)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_queue_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'whisper_gui.queue_model'`.

- [ ] **Step 3: Implement `queue_model.py`**

Create `whisper_gui/queue_model.py`:

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class QueueStatus(Enum):
    QUEUED = "Queued"
    TRANSCRIBING = "Transcribing"
    TRANSLATING = "Translating"
    DONE = "Done"
    ERROR = "Error"


@dataclass
class QueueItem:
    path: Path
    status: QueueStatus = QueueStatus.QUEUED
    original_text: str | None = None
    english_text: str | None = None
    error_message: str | None = None


class QueueModel:
    def __init__(self) -> None:
        self._items: list[QueueItem] = []

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> QueueItem:
        return self._items[index]

    def add(self, path: Path) -> int:
        self._items.append(QueueItem(path=path))
        return len(self._items) - 1

    def set_status(self, index: int, status: QueueStatus) -> None:
        self._items[index].status = status

    def set_result(self, index: int, original: str, english: str) -> None:
        item = self._items[index]
        item.original_text = original
        item.english_text = english
        item.status = QueueStatus.DONE

    def set_error(self, index: int, message: str) -> None:
        item = self._items[index]
        item.error_message = message
        item.status = QueueStatus.ERROR

    def pending_items(self) -> list[tuple[int, Path]]:
        return [
            (i, item.path)
            for i, item in enumerate(self._items)
            if item.status == QueueStatus.QUEUED
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_queue_model.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add whisper_gui/queue_model.py tests/test_queue_model.py
git commit -m "feat: add queue model for tracking per-file transcription status"
```

---

### Task 4: Transcription pure functions (model wrapper, I/O)

**Files:**
- Create: `whisper_gui/transcription.py`
- Test: `tests/test_transcription.py`

**Interfaces:**
- Consumes: nothing (uses `whisper.load_model` internally, duck-typed model elsewhere).
- Produces: `get_model()` (loads/caches the real `medium` CUDA model — not exercised in unit tests), `transcribe_original(model, path: Path) -> str`, `translate_to_english(model, path: Path) -> str`, `output_paths(source: Path) -> tuple[Path, Path]`, `save_transcripts(source: Path, original: str, english: str) -> tuple[Path, Path]`. Used by `worker.py` (Task 5).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_transcription.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_transcription.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'whisper_gui.transcription'`.

- [ ] **Step 3: Implement `transcription.py`**

Create `whisper_gui/transcription.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_transcription.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add whisper_gui/transcription.py tests/test_transcription.py
git commit -m "feat: add transcription/translation pipeline functions"
```

---

### Task 5: Transcription worker thread

**Files:**
- Create: `whisper_gui/worker.py`
- Create: `tests/conftest.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `get_model`, `transcribe_original`, `translate_to_english`, `save_transcripts` from `whisper_gui.transcription` (Task 4).
- Produces: `TranscriptionWorker(QThread)` constructed with `items: list[tuple[int, Path]]`, with Qt signals `status_changed(int, str)`, `result_ready(int, str, str)`, `error(int, str)`, `model_load_failed(str)`, and a `run()` method. Used by `main_window.py` (Task 6).

- [ ] **Step 1: Add the shared `qapp` test fixture**

Create `tests/conftest.py`:

```python
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_worker.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_worker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'whisper_gui.worker'`.

- [ ] **Step 4: Implement `worker.py`**

Create `whisper_gui/worker.py`:

```python
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .transcription import get_model, save_transcripts, transcribe_original, translate_to_english


class TranscriptionWorker(QThread):
    status_changed = Signal(int, str)
    result_ready = Signal(int, str, str)
    error = Signal(int, str)
    model_load_failed = Signal(str)

    def __init__(self, items: list[tuple[int, Path]], parent=None):
        super().__init__(parent)
        self.items = items

    def run(self) -> None:
        try:
            model = get_model()
        except Exception as exc:
            self.model_load_failed.emit(str(exc))
            return

        for index, path in self.items:
            self.status_changed.emit(index, "Transcribing")
            try:
                original = transcribe_original(model, path)
                self.status_changed.emit(index, "Translating")
                english = translate_to_english(model, path)
                save_transcripts(path, original, english)
            except Exception as exc:
                self.error.emit(index, str(exc))
                self.status_changed.emit(index, "Error")
                continue
            self.result_ready.emit(index, original, english)
            self.status_changed.emit(index, "Done")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_worker.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add whisper_gui/worker.py tests/conftest.py tests/test_worker.py
git commit -m "feat: add sequential transcription worker thread"
```

---

### Task 6: Main window GUI and entry point

**Files:**
- Create: `whisper_gui/main_window.py`
- Modify: `main.py`

**Interfaces:**
- Consumes: `FILE_DIALOG_FILTER`, `validate_path` from `whisper_gui.audio_formats` (Task 2); `QueueModel`, `QueueStatus` from `whisper_gui.queue_model` (Task 3); `TranscriptionWorker` from `whisper_gui.worker` (Task 5).
- Produces: `MainWindow(QMainWindow)` with no required constructor args. Used by `main.py`.

- [ ] **Step 1: Implement `main_window.py`**

Create `whisper_gui/main_window.py`:

```python
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .audio_formats import FILE_DIALOG_FILTER, validate_path
from .queue_model import QueueModel, QueueStatus
from .worker import TranscriptionWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Whisper Dual-Language Transcriber")

        self.queue_model = QueueModel()
        self.worker: TranscriptionWorker | None = None

        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Type or paste an audio file path...")
        self.address_bar.returnPressed.connect(self._add_from_address_bar)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_files)

        add_button = QPushButton("Add to Queue")
        add_button.clicked.connect(self._add_from_address_bar)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self.address_bar)
        top_bar.addWidget(browse_button)
        top_bar.addWidget(add_button)

        self.queue_list = QListWidget()
        self.queue_list.currentRowChanged.connect(self._on_selection_changed)

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start_batch)

        queue_box = QVBoxLayout()
        queue_box.addLayout(top_bar)
        queue_box.addWidget(self.queue_list)
        queue_box.addWidget(self.start_button)

        self.original_panel = QPlainTextEdit()
        self.original_panel.setReadOnly(True)
        self.english_panel = QPlainTextEdit()
        self.english_panel.setReadOnly(True)

        original_copy = QPushButton("Copy")
        original_copy.clicked.connect(lambda: self._copy(self.original_panel))
        english_copy = QPushButton("Copy")
        english_copy.clicked.connect(lambda: self._copy(self.english_panel))

        original_header = QHBoxLayout()
        original_header.addWidget(QLabel("Original language"))
        original_header.addWidget(original_copy)
        original_box = QVBoxLayout()
        original_box.addLayout(original_header)
        original_box.addWidget(self.original_panel)

        english_header = QHBoxLayout()
        english_header.addWidget(QLabel("English"))
        english_header.addWidget(english_copy)
        english_box = QVBoxLayout()
        english_box.addLayout(english_header)
        english_box.addWidget(self.english_panel)

        original_widget = QWidget()
        original_widget.setLayout(original_box)
        english_widget = QWidget()
        english_widget.setLayout(english_box)

        panels_widget = QWidget()
        panels_layout = QHBoxLayout(panels_widget)
        panels_layout.addWidget(original_widget)
        panels_layout.addWidget(english_widget)

        queue_widget = QWidget()
        queue_widget.setLayout(queue_box)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(queue_widget)
        splitter.addWidget(panels_widget)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(splitter)
        self.setCentralWidget(central)

    def _add_from_address_bar(self) -> None:
        self._add_path(self.address_bar.text())

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select audio files", "", FILE_DIALOG_FILTER
        )
        for raw_path in paths:
            self._add_path(raw_path)

    def _add_path(self, raw_path: str) -> None:
        try:
            path = validate_path(raw_path)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot add file", str(exc))
            return
        self.queue_model.add(path)
        self.queue_list.addItem(f"{path.name} — {QueueStatus.QUEUED.value}")
        self.address_bar.clear()

    def _start_batch(self) -> None:
        pending = self.queue_model.pending_items()
        if not pending:
            QMessageBox.information(self, "Nothing to do", "No queued files to process.")
            return
        self.start_button.setEnabled(False)
        self.worker = TranscriptionWorker(pending)
        self.worker.status_changed.connect(self._on_status_changed)
        self.worker.result_ready.connect(self._on_result_ready)
        self.worker.error.connect(self._on_error)
        self.worker.model_load_failed.connect(self._on_model_load_failed)
        self.worker.finished.connect(self._on_batch_finished)
        self.worker.start()

    def _on_status_changed(self, index: int, status: str) -> None:
        self.queue_model.set_status(index, QueueStatus(status))
        item = self.queue_list.item(index)
        path = self.queue_model[index].path
        item.setText(f"{path.name} — {status}")

    def _on_result_ready(self, index: int, original: str, english: str) -> None:
        self.queue_model.set_result(index, original, english)
        if self.queue_list.currentRow() == index:
            self.original_panel.setPlainText(original)
            self.english_panel.setPlainText(english)

    def _on_error(self, index: int, message: str) -> None:
        self.queue_model.set_error(index, message)
        self.queue_list.item(index).setToolTip(message)

    def _on_model_load_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Model failed to load", message)

    def _on_batch_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.worker = None

    def _on_selection_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.queue_model):
            self.original_panel.clear()
            self.english_panel.clear()
            return
        item = self.queue_model[row]
        self.original_panel.setPlainText(item.original_text or "")
        self.english_panel.setPlainText(item.english_text or "")

    @staticmethod
    def _copy(panel: QPlainTextEdit) -> None:
        QGuiApplication.clipboard().setText(panel.toPlainText())
```

- [ ] **Step 2: Replace `main.py` with the launcher**

Replace the full contents of `main.py` with:

```python
import sys

from PySide6.QtWidgets import QApplication

from whisper_gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Manually verify the window launches cleanly**

Run: `uv run python main.py`
Expected: a window titled "Whisper Dual-Language Transcriber" opens showing the address bar + Browse + Add to Queue row, an empty queue list, a Start button, and two empty read-only panels labeled "Original language" and "English". No traceback in the terminal. Close the window to end the process.

- [ ] **Step 4: Commit**

```bash
git add whisper_gui/main_window.py main.py
git commit -m "feat: assemble main window GUI and wire entry point"
```

---

### Task 7: End-to-end manual smoke test

**Files:** none (verification only; fix forward in the relevant task's files if something breaks).

**Interfaces:**
- Consumes: the full app (Tasks 1-6).
- Produces: confidence the real pipeline works end-to-end on GPU with a real audio file, including a WhatsApp-style `.ogg`/`.opus` voice note.

Note: the repo currently only contains Whisper-CLI *output* files (`.json`/`.srt`/`.tsv`/`.txt`/`.vtt`) for past WhatsApp voice notes — the original audio files aren't in the repo. Use any real audio file you have on hand (a WhatsApp-exported `.opus`/`.ogg` voice note is ideal since it's the format this app is named for; any `.wav`/`.mp3`/`.m4a` also works for the general pipeline check).

- [ ] **Step 1: Launch the app**

Run: `uv run python main.py`

- [ ] **Step 2: Add a real audio file**

Type or paste the full path to a real audio file into the address bar and press Enter (or use Browse).
Expected: a new row appears in the queue list reading `<filename> — Queued`.

- [ ] **Step 3: Start the batch and watch status transitions**

Click **Start**.
Expected: the row's status cycles `Transcribing` → `Translating` → `Done`. Clicking the row shows the original-language text in the left panel and the English translation in the right panel.

- [ ] **Step 4: Confirm GPU is actually being used**

While step 3 is running, in a separate terminal run: `nvidia-smi`
Expected: a `python` process appears in the process list with non-zero GPU memory/utilization.

- [ ] **Step 5: Confirm auto-saved files**

Check the folder containing the source audio file.
Expected: two new files exist, `<name>.txt` (original language) and `<name>.en.txt` (English), whose contents match what's shown in the two panels.

- [ ] **Step 6: Confirm batch continues past a bad file**

Add a second, non-audio file via Browse by switching its filter to "All Files" and picking e.g. `README.md`, then rename/retype a path that doesn't exist, confirming it's rejected at add-time (per Task 2's validation) rather than reaching the queue. Then add one more real, valid audio file after the first one and click Start again — confirm both process correctly in order.
Expected: the invalid path is rejected with a warning dialog at add-time and never appears in the queue; the two valid files both reach `Done`.

If any step doesn't match the expected result, fix the responsible module (from Tasks 2-6) and commit the fix with a message like `fix: <what was wrong>` before considering this plan complete.
