# Synced Playback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user play the audio/video of the selected queue row, with the transcript shown as timed lines that highlight as playback moves, click-to-seek, a repeat-line loop on the original-language panel, variable speed, and a quick rewind.

**Architecture:** Whisper's segment timestamps (currently discarded) are captured and persisted as `.srt`/`.en.srt` files alongside the existing `.txt`/`.en.txt`. A new `MediaPlayerWidget` (Qt Multimedia) and `TimedTranscriptPanel` (per-line list with highlighting) replace the current plain-text panels. The window layout changes from a top/bottom split to a left sidebar (queue) + right column (player above transcripts).

**Tech Stack:** Python 3.13, PySide6 (QtMultimedia, QtMultimediaWidgets — already a dependency, verified importable), openai-whisper, uv, pytest.

**Spec:** `plans/2026-10-21-playback-and-grammar-design.md` (sections 0–3 and the "Decisions" sections; section 4, the Grammar tab, is Plan B — out of scope here).

## Global Constraints

- Preserve the existing backup-before-overwrite behavior (`.bak` sibling) for every output file this plan writes or rewrites: `.txt`, `.en.txt`, and the new `.srt`, `.en.srt`.
- Never block the UI thread during transcription — all Whisper calls stay on `TranscriptionWorker` (`QThread`), unchanged.
- Repeat-line looping applies only to the original-language panel; clicking an English line seeks but never sets a repeat target (spec "Decisions").
- Speed range is 0.5x–1.5x (spec Goal 2). A "rewind 5 seconds" button is included in addition to the spec's controls, per the user's earlier-approved mini-design in this conversation — the spec is silent on it, not against it.
- The Whisper CLI output files already in `data/` are never read or written by this app; this plan only touches files beside the selected media file.
- `ffmpeg` is on PATH; Qt's bundled FFmpeg multimedia backend was verified against a real WhatsApp voice note (Opus-in-Ogg) and a real WhatsApp video (H.264/mp4) on this machine — both load with no transcoding fallback needed.

## Review Focus

- A file whose `.txt`/`.en.txt` exist but whose `.srt`/`.en.srt` do not (older or externally-produced transcripts) — the panel must show the plain text with a "no timing data" note, never crash. (Tasks 2, 6, 7)
- Switching the selected row while media is playing — playback must stop before the new file loads, with no leaked audio from the previous file. (Task 5)
- Toggling "Repeat line" before any line has ever been clicked — must not loop or raise; nothing happens until a target exists. (Task 5)
- Rewinding when already within 5 seconds of the start — must clamp to 0, never go negative. (Task 5)
- A codec Qt cannot decode — the player must show the error and the app must carry on, never crash or hang. (Task 5)
- The English segment list's count/timings can differ from the original's (two independent Whisper passes) — English highlighting must work off its own segment list without assuming parity with the original panel. (Task 7)

---

### Task 1: Segment data model and SRT serialization

**Files:**
- Create: `whisper_gui/segments.py`
- Test: `tests/test_segments.py`

**Interfaces:**
- Produces: `Segment` (dataclass: `start_ms: int`, `end_ms: int`, `text: str`); `segments_to_srt(segments: list[Segment]) -> str`; `parse_srt(content: str) -> list[Segment]`; `segment_at(segments: list[Segment], position_ms: int) -> int | None` (index of the segment with `start_ms <= position_ms < end_ms`, or `None`).

- [ ] **Step 1: Write the failing tests**

```python
from whisper_gui.segments import Segment, segment_at, segments_to_srt, parse_srt


def test_segments_to_srt_formats_two_lines():
    segs = [
        Segment(start_ms=0, end_ms=3420, text="Hola mundo"),
        Segment(start_ms=3420, end_ms=5100, text="Segunda linea"),
    ]
    srt = segments_to_srt(segs)
    assert srt == (
        "1\n00:00:00,000 --> 00:00:03,420\nHola mundo\n\n"
        "2\n00:00:03,420 --> 00:00:05,100\nSegunda linea\n\n"
    )


def test_parse_srt_round_trips_segments_to_srt_output():
    segs = [
        Segment(start_ms=0, end_ms=3420, text="Hola mundo"),
        Segment(start_ms=3420, end_ms=5100, text="Segunda linea"),
    ]
    assert parse_srt(segments_to_srt(segs)) == segs


def test_segment_at_returns_index_of_containing_segment():
    segs = [
        Segment(start_ms=0, end_ms=3420, text="a"),
        Segment(start_ms=3420, end_ms=5100, text="b"),
    ]
    assert segment_at(segs, 1000) == 0
    assert segment_at(segs, 3420) == 1
    assert segment_at(segs, 5099) == 1


def test_segment_at_returns_none_outside_all_segments():
    segs = [Segment(start_ms=1000, end_ms=2000, text="a")]
    assert segment_at(segs, 500) is None
    assert segment_at(segs, 2000) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_segments.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'whisper_gui.segments'`

- [ ] **Step 3: Implement `Segment`, `segments_to_srt`, `parse_srt`, `segment_at` in `whisper_gui/segments.py`**

`Segment` is a plain `@dataclass`. `segments_to_srt` numbers entries from 1 and formats each timestamp as `HH:MM:SS,mmm` (zero-padded, from an integer millisecond count — e.g. 3420 → `00:00:03,420`). `parse_srt` is the inverse: split on blank lines, read the index line, parse the `-->` timestamp line back to milliseconds, join remaining lines as `text`. `segment_at` does a linear scan for `start_ms <= position_ms < end_ms`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_segments.py -v`
Expected: PASS (4/4)

- [ ] **Step 5: Commit**

```bash
git add whisper_gui/segments.py tests/test_segments.py
git commit -m "feat: add Segment model and SRT serialization"
```

---

### Task 2: Capture segment timestamps in the transcription pipeline

**Files:**
- Modify: `whisper_gui/transcription.py`
- Modify: `tests/test_transcription.py`

**Interfaces:**
- Consumes: `Segment`, `segments_to_srt`, `parse_srt` from Task 1 (`whisper_gui.segments`).
- Produces: `transcribe_original(model, path: Path) -> tuple[str, list[Segment]]`; `translate_to_english(model, path: Path) -> tuple[str, list[Segment]]` (signatures changed — both now return `(text, segments)`); `output_srt_paths(source: Path) -> tuple[Path, Path]` (mirrors `output_paths`, suffixes `.srt`/`.en.srt`); `save_transcripts(source: Path, original: str, original_segments: list[Segment], english: str, english_segments: list[Segment]) -> tuple[Path, Path, Path, Path]` (signature changed — returns `(original_txt, english_txt, original_srt, english_srt)`); `LoadedTranscript` (dataclass: `original_text: str`, `original_segments: list[Segment]`, `english_text: str`, `english_segments: list[Segment]`); `load_existing_transcripts(source: Path) -> LoadedTranscript | None` (returns `None` unless both `.txt` and `.en.txt` exist beside `source`; segments come from `.srt`/`.en.srt` if present, else `[]`).

- [ ] **Step 1: Write the failing tests**

Replace `_FakeWhisperModel` and the existing transcription tests in `tests/test_transcription.py` with:

```python
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


def test_output_srt_paths_mirrors_output_paths_naming(tmp_path):
    source = tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.ogg"
    original_srt, english_srt = output_srt_paths(source)
    assert original_srt == tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.srt"
    assert english_srt == tmp_path / "WhatsApp Ptt 2026-10-07 at 1.19.18 PM.en.srt"


def test_save_transcripts_writes_text_and_srt_files(tmp_path):
    source = tmp_path / "voice.ogg"
    segs = [Segment(start_ms=0, end_ms=1200, text="hola")]
    original_txt, english_txt, original_srt, english_srt = save_transcripts(
        source, "hola", segs, "hello", segs
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
```

Keep the existing `test_output_paths_handles_filenames_with_spaces_and_multiple_dots` test as-is (its target function, `output_paths`, is unchanged).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_transcription.py -v`
Expected: FAIL — `transcribe_original`/`translate_to_english` still return a bare string, `output_srt_paths`/`load_existing_transcripts` don't exist yet, `save_transcripts` has the old 3-argument signature.

- [ ] **Step 3: Implement the changes in `whisper_gui/transcription.py`**

- `transcribe_original`/`translate_to_english`: build `Segment(start_ms=round(s["start"] * 1000), end_ms=round(s["end"] * 1000), text=s["text"].strip())` for each entry in `result["segments"]`; return `(text, segments)`.
- `output_srt_paths(source)`: same pattern as `output_paths`, suffixes `.srt`/`.en.srt`.
- `save_transcripts`: write the two `.txt` files as today, plus `segments_to_srt(original_segments)`/`segments_to_srt(english_segments)` to the two `.srt` paths — call `_backup_if_exists` on all four paths before writing. Return the four paths in the order `(original_txt, english_txt, original_srt, english_srt)`.
- `LoadedTranscript`: plain `@dataclass` with the four fields listed in Interfaces.
- `load_existing_transcripts(source)`: return `None` if either `.txt` path from `output_paths(source)` is missing; otherwise read both `.txt` files, and for each of the two `.srt` paths from `output_srt_paths(source)`, read+`parse_srt` it if it exists else use `[]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_transcription.py -v`
Expected: PASS (9/9)

- [ ] **Step 5: Commit**

```bash
git add whisper_gui/transcription.py tests/test_transcription.py
git commit -m "feat: capture Whisper segment timestamps and persist as SRT"
```

---

### Task 3: Carry segments on QueueItem

**Files:**
- Modify: `whisper_gui/queue_model.py`
- Modify: `tests/test_queue_model.py`

**Interfaces:**
- Consumes: `Segment` from Task 1 (`whisper_gui.segments`).
- Produces: `QueueItem` gains `original_segments: list[Segment]` and `english_segments: list[Segment]` (both default to `[]`); `QueueModel.set_result(self, index: int, original: str, original_segments: list[Segment], english: str, english_segments: list[Segment]) -> None` (signature changed — two new positional params).

- [ ] **Step 1: Write the failing test**

Update `test_set_result_stores_texts_and_marks_done` and `test_pending_items_returns_only_queued_items_with_original_index` in `tests/test_queue_model.py` to pass segment lists, and add one new test:

```python
from whisper_gui.segments import Segment
from whisper_gui.queue_model import QueueModel, QueueStatus


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


def test_pending_items_returns_only_queued_items_with_original_index(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "a.ogg")
    model.add(tmp_path / "b.ogg")
    model.add(tmp_path / "c.ogg")
    model.set_result(0, "a", [], "a-en", [])
    model.set_error(1, "boom")
    pending = model.pending_items()
    assert pending == [(2, model[2].path)]
```

Also add a default-value assertion to the existing `test_add_appends_item_with_queued_status`:

```python
    assert model[0].original_segments == []
    assert model[0].english_segments == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_queue_model.py -v`
Expected: FAIL — `set_result()` rejects the extra positional arguments (`TypeError`), and `QueueItem` has no `original_segments`/`english_segments` attributes.

- [ ] **Step 3: Implement the changes in `whisper_gui/queue_model.py`**

Add the two fields to `QueueItem` using `field(default_factory=list)` (import `field` from `dataclasses`). Extend `set_result`'s signature as specified and assign both segment lists onto the item alongside the existing text/status assignment.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_queue_model.py -v`
Expected: PASS (6/6)

- [ ] **Step 5: Commit**

```bash
git add whisper_gui/queue_model.py tests/test_queue_model.py
git commit -m "feat: carry segment timestamps on QueueItem"
```

---

### Task 4: Propagate segments through the transcription worker

**Files:**
- Modify: `whisper_gui/worker.py`
- Modify: `tests/test_worker.py`

**Interfaces:**
- Consumes: `transcribe_original`/`translate_to_english`/`save_transcripts` from Task 2 (new signatures); `QueueModel`/`QueueItem` unaffected directly (the worker doesn't touch `QueueModel` — `MainWindow` does, in Task 7).
- Produces: `TranscriptionWorker.result_ready` signal changes shape to `Signal(int, str, object, str, object)`, emitting `(index, original_text, original_segments, english_text, english_segments)` (the two `object` slots carry `list[Segment]` — Qt signals use `object` for arbitrary Python types).

- [ ] **Step 1: Write the failing tests**

Update `tests/test_worker.py`: the `_FailingOnBadFileModel` and inline `_Model` fakes' `transcribe` methods must return `{"text": ..., "segments": []}` instead of just `{"text": ...}`. Update every `result_ready.connect(lambda i, o, e: ...)` to a 5-argument lambda and the assertions that unpack `results`:

```python
    w.result_ready.connect(lambda i, o, o_segs, e, e_segs: results.append((i, o, e)))
    ...
    assert [i for i, _, _ in results] == [0, 2]
```

(Only the lambda signature changes — segments are accepted but not asserted on in this test, since `_FailingOnBadFileModel` returns no real timing data. The existing `assert errors == [...]` and `assert statuses == [...]` lines are unchanged.)

Apply the same `{"text": ..., "segments": []}` fix and 5-argument lambda to `test_worker_stops_early_when_stop_requested_before_run` and `test_worker_emits_model_load_failed_and_processes_nothing`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_worker.py -v`
Expected: FAIL — `result_ready` still has the 3-argument signature, so connecting a 5-argument lambda raises `TypeError` when the signal fires.

- [ ] **Step 3: Implement the changes in `whisper_gui/worker.py`**

Change `result_ready = Signal(int, str, str)` to `Signal(int, str, object, str, object)`. In `run()`, unpack `original, original_segments = transcribe_original(model, path)` and `english, english_segments = translate_to_english(model, path)`; pass all four to `save_transcripts(path, original, original_segments, english, english_segments)`; emit `self.result_ready.emit(index, original, original_segments, english, english_segments)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_worker.py -v`
Expected: PASS (3/3)

- [ ] **Step 5: Commit**

```bash
git add whisper_gui/worker.py tests/test_worker.py
git commit -m "feat: propagate segment timestamps through the worker thread"
```

---

### Task 5: Media player widget

**Files:**
- Create: `whisper_gui/media_player.py`
- Test: `tests/test_media_player.py`

**Interfaces:**
- Produces: `clamp_rewind(position_ms: int, rewind_ms: int = 5000) -> int` (pure function: `max(0, position_ms - rewind_ms)`); `SPEED_OPTIONS: tuple[float, ...]` = `(0.5, 0.75, 1.0, 1.25, 1.5)`; `MediaPlayerWidget(QWidget)` with: constructor `__init__(self, parent=None, player: QMediaPlayer | None = None)` (injectable player for tests); signal `position_changed = Signal(int)` (re-emits the player's position in ms); methods `load(self, path: Path) -> None`, `seek(self, position_ms: int) -> None`, `rewind(self) -> None`, `stop(self) -> None`, `set_repeat_target(self, start_ms: int, end_ms: int) -> None`; public attributes `play_button`, `rewind_button`, `repeat_checkbox`, `speed_box`, `scrub_bar`, `status_label` (all real Qt widgets, for the smoke test and for Task 7 to read `isChecked()`/etc. if ever needed — Task 7 doesn't need to, it only uses the methods above).

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import MagicMock

from PySide6.QtMultimedia import QMediaPlayer

from whisper_gui.media_player import SPEED_OPTIONS, MediaPlayerWidget, clamp_rewind


def test_clamp_rewind_subtracts_five_seconds_by_default():
    assert clamp_rewind(12000) == 7000


def test_clamp_rewind_floors_at_zero():
    assert clamp_rewind(2000) == 0


def test_widget_constructs_with_default_speed_one_x(qapp):
    widget = MediaPlayerWidget()
    assert widget.speed_box.currentData() == 1.0
    assert list(SPEED_OPTIONS) == sorted(SPEED_OPTIONS)
    assert 1.0 in SPEED_OPTIONS


def test_rewind_seeks_player_to_clamped_position(qapp):
    fake_player = MagicMock(spec=QMediaPlayer)
    fake_player.position.return_value = 12000
    widget = MediaPlayerWidget(player=fake_player)
    widget.rewind()
    fake_player.setPosition.assert_called_once_with(7000)


def test_repeat_checked_with_no_target_set_does_not_seek(qapp):
    fake_player = MagicMock(spec=QMediaPlayer)
    widget = MediaPlayerWidget(player=fake_player)
    widget.repeat_checkbox.setChecked(True)
    widget._on_position_changed(9999)
    fake_player.setPosition.assert_not_called()


def test_repeat_checked_seeks_back_to_target_start_past_end(qapp):
    fake_player = MagicMock(spec=QMediaPlayer)
    widget = MediaPlayerWidget(player=fake_player)
    widget.set_repeat_target(1000, 2000)
    widget.repeat_checkbox.setChecked(True)
    widget._on_position_changed(2000)
    fake_player.setPosition.assert_called_once_with(1000)


def test_load_stops_playback_before_loading_new_source(qapp, tmp_path):
    fake_player = MagicMock(spec=QMediaPlayer)
    widget = MediaPlayerWidget(player=fake_player)
    path = tmp_path / "b.ogg"
    widget.load(path)
    call_names = [c[0] for c in fake_player.method_calls]
    assert call_names.index("stop") < call_names.index("setSource")


def test_player_error_shows_in_status_label(qapp):
    fake_player = MagicMock(spec=QMediaPlayer)
    widget = MediaPlayerWidget(player=fake_player)
    widget._on_error(QMediaPlayer.Error.FormatError, "codec not supported")
    assert widget.status_label.text() == "codec not supported"
```

Note: `QMediaPlayer` has no real backend wired up for `fake_player` (it's a `MagicMock(spec=QMediaPlayer)`), so `self.player.positionChanged.connect(...)` etc. in the widget's constructor must tolerate a mock — `MagicMock(spec=...)` auto-mocks signal attributes as further mocks, so `.connect(...)` calls on them are no-ops; this is why `_on_position_changed` is called directly in the test instead of relying on a real signal firing.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_media_player.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'whisper_gui.media_player'`

- [ ] **Step 3: Implement `whisper_gui/media_player.py`**

`clamp_rewind` and `SPEED_OPTIONS` as specified. `MediaPlayerWidget`: build `self.player` (the injected one or a new `QMediaPlayer(self)`), a `QAudioOutput` wired via `self.player.setAudioOutput(...)`, a `QVideoWidget` wired via `self.player.setVideoOutput(...)` and hidden/shown on `self.player.hasVideoChanged` (`video_widget.setVisible(has_video)`); `play_button` toggles `player.play()`/`player.pause()` based on `player.playbackState()`, and its own text updates on `player.playbackStateChanged`; `rewind_button` calls `self.rewind()`; `repeat_checkbox` is a plain `QCheckBox`; `speed_box` is a `QComboBox` populated from `SPEED_OPTIONS` with `1.0` selected by default, and its `currentIndexChanged` calls `player.setPlaybackRate(speed_box.currentData())`; `scrub_bar` is a horizontal `QSlider` whose range is set from `player.durationChanged` and whose `sliderMoved` calls `self.seek`; `player.positionChanged` connects to `self._on_position_changed`, which updates `scrub_bar`'s value (unless the user is dragging it), checks the repeat condition (`repeat_checkbox.isChecked()` and a target is set and `position_ms >= target_end`, then `self.seek(target_start)`), and emits `self.position_changed`. `status_label` is a `QLabel`, initially empty, wired via `player.errorOccurred.connect(self._on_error)` where `_on_error(self, error, error_string)` sets `status_label.setText(error_string)`. `load()` calls `self.player.stop()` **before** `self.player.setSource(QUrl.fromLocalFile(str(path)))`, in that order, and clears any repeat target and `status_label`'s text. `set_repeat_target` stores `(start_ms, end_ms)` on the instance.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_media_player.py -v`
Expected: PASS (8/8)

- [ ] **Step 5: Commit**

```bash
git add whisper_gui/media_player.py tests/test_media_player.py
git commit -m "feat: add media player widget with speed, rewind, and line-repeat"
```

---

### Task 6: Timed transcript panel

**Files:**
- Create: `whisper_gui/timed_transcript_panel.py`
- Test: `tests/test_timed_transcript_panel.py`

**Interfaces:**
- Consumes: `Segment`, `segment_at` from Task 1 (`whisper_gui.segments`).
- Produces: `TimedTranscriptPanel(QWidget)` with: signals `seek_requested = Signal(int)` (ms, emitted whenever the user clicks a line), `line_activated = Signal(int, int)` (start_ms, end_ms — also emitted on every line click; `MainWindow` in Task 7 connects this only for the original panel); methods `set_segments(self, segments: list[Segment]) -> None` (switches to timed-line display), `set_plain_text(self, text: str) -> None` (switches to a plain read-only view with a "No timing data — re-run to enable highlighting." note), `update_position(self, position_ms: int) -> None` (no-op unless in timed-line mode; highlights the row from `segment_at`), `clear(self) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
from whisper_gui.segments import Segment
from whisper_gui.timed_transcript_panel import TimedTranscriptPanel


def _segs():
    return [
        Segment(start_ms=0, end_ms=1000, text="Hola"),
        Segment(start_ms=1000, end_ms=2000, text="Mundo"),
    ]


def test_set_segments_then_update_position_highlights_matching_row(qapp):
    panel = TimedTranscriptPanel()
    panel.set_segments(_segs())
    panel.update_position(1500)
    assert panel.list_widget.currentRow() == 1


def test_update_position_outside_any_segment_clears_highlight(qapp):
    panel = TimedTranscriptPanel()
    panel.set_segments(_segs())
    panel.update_position(1500)
    panel.update_position(50000)
    assert panel.list_widget.currentRow() == -1


def test_clicking_a_line_emits_seek_requested_and_line_activated(qapp):
    panel = TimedTranscriptPanel()
    panel.set_segments(_segs())
    seeks = []
    activations = []
    panel.seek_requested.connect(seeks.append)
    panel.line_activated.connect(lambda s, e: activations.append((s, e)))
    panel._on_item_clicked(panel.list_widget.item(1))
    assert seeks == [1000]
    assert activations == [(1000, 2000)]


def test_set_plain_text_shows_note_and_ignores_update_position(qapp):
    panel = TimedTranscriptPanel()
    panel.set_plain_text("some text without timing")
    panel.update_position(500)
    assert panel.list_widget.currentRow() == -1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_timed_transcript_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'whisper_gui.timed_transcript_panel'`

- [ ] **Step 3: Implement `whisper_gui/timed_transcript_panel.py`**

Internally hold a `QStackedWidget` with two pages: a `QListWidget` (`self.list_widget`, one item per segment, item text is the segment's `.text`) for timed mode, and a plain-text page (a `QLabel` note above a read-only `QPlainTextEdit`) for fallback mode. `set_segments` stores the list, repopulates `self.list_widget`, and switches the stack to the list page. `set_plain_text` switches to the plain-text page and sets its text; also clear `self._segments` to `[]` so `update_position` has nothing to match. `update_position`: no-op if `self._segments` is empty; otherwise call `segment_at(self._segments, position_ms)` and `self.list_widget.setCurrentRow(idx if idx is not None else -1)`. Connect `self.list_widget.itemClicked` (not `currentRowChanged`, which also fires from `update_position`'s own `setCurrentRow` call and would create a feedback loop) to `self._on_item_clicked`, which looks up the clicked row's index via `self.list_widget.row(item)`, and emits both `seek_requested` (the segment's `start_ms`) and `line_activated` (its `start_ms`, `end_ms`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_timed_transcript_panel.py -v`
Expected: PASS (4/4)

- [ ] **Step 5: Commit**

```bash
git add whisper_gui/timed_transcript_panel.py tests/test_timed_transcript_panel.py
git commit -m "feat: add timed transcript panel with highlighting and click-to-seek"
```

---

### Task 7: Wire the new window layout

**Files:**
- Modify: `whisper_gui/main_window.py`
- Modify: `tests/test_main_window.py`

**Interfaces:**
- Consumes: `MediaPlayerWidget` (Task 5), `TimedTranscriptPanel` (Task 6), `load_existing_transcripts` (Task 2), `QueueModel.set_result`'s new signature (Task 3), `TranscriptionWorker.result_ready`'s new signature (Task 4).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_main_window.py` (keep the existing `test_close_event_stops_running_worker_before_accepting`, updating only what its own `_SlowModel.transcribe` returns, to `{"text": "x", "segments": []}`, since `TranscriptionWorker` now expects a `"segments"` key):

```python
from whisper_gui.segments import Segment
from whisper_gui.transcription import save_transcripts


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
```

(This needs `from whisper_gui.media_player import MediaPlayerWidget` added to the test file's imports.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main_window.py -v`
Expected: FAIL — `MainWindow` has no `media_player`/`original_panel.list_widget` yet, `_add_path` doesn't call `load_existing_transcripts`, `_on_result_ready` still takes 3 arguments.

- [ ] **Step 3: Rebuild the layout and wiring in `whisper_gui/main_window.py`**

Layout: a `QSplitter(Qt.Orientation.Horizontal)` with two children — a left sidebar widget (`QVBoxLayout`: the existing top-bar address/Browse/Add row, `self.queue_list`, `self.start_button` — unchanged from today) and a right-column widget containing a `QSplitter(Qt.Orientation.Vertical)` with `self.media_player` (a `MediaPlayerWidget`) on top and a panels row (`QHBoxLayout` of the original and English panel widgets, each now a `TimedTranscriptPanel` wrapped with its existing header/Copy-button row) below.

`self.original_panel`/`self.english_panel` become `TimedTranscriptPanel` instances (replacing the two `QPlainTextEdit`s), so the existing `_copy(panel)` static method (which calls `panel.toPlainText()`) no longer applies. Replace it with `_copy_current(self, getter: Callable[[QueueItem], str | None]) -> None`: no-ops if `self.queue_list.currentRow() < 0`, else copies `getter(self.queue_model[self.queue_list.currentRow()]) or ""` via `QGuiApplication.clipboard().setText(...)`. Wire `original_copy.clicked.connect(lambda: self._copy_current(lambda item: item.original_text))` and the equivalent for `english_copy`/`item.english_text`.

`_add_path`: after `index = self.queue_model.add(path)`, call `loaded = load_existing_transcripts(path)`; if not `None`, call `self.queue_model.set_result(index, loaded.original_text, loaded.original_segments, loaded.english_text, loaded.english_segments)` and add the list item with status `"Done"` instead of `"Queued"`.

`_on_selection_changed(row)`: in addition to its current clearing/populating behavior, call `self.media_player.load(self.queue_model[row].path)` when `row` is valid (and `self.media_player.stop()` when not); feed each panel via `set_segments(item.original_segments)` if non-empty else `set_plain_text(item.original_text or "")` (same pattern for the English panel/segments).

`_on_result_ready(self, index, original, original_segments, english, english_segments)`: store via `self.queue_model.set_result(index, original, original_segments, english, english_segments)`; if `index` is the currently selected row, populate both panels the same way `_on_selection_changed` does.

Wire once in `__init__`: `self.media_player.position_changed.connect(self.original_panel.update_position)`, same for `self.english_panel`; `self.original_panel.seek_requested.connect(self.media_player.seek)`, same for `self.english_panel.seek_requested`; `self.original_panel.line_activated.connect(self.media_player.set_repeat_target)` (English panel's `line_activated` is intentionally left unconnected — spec: no repeat from the English panel).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main_window.py -v`
Expected: PASS (7/7)

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS, all tests across every module green.

- [ ] **Step 6: Commit**

```bash
git add whisper_gui/main_window.py tests/test_main_window.py
git commit -m "feat: synced media playback with timed transcript panels"
```
