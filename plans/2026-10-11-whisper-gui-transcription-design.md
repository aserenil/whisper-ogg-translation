# Design: Whisper dual-language transcription GUI

Status: **approved** — proceeding to implementation plan.

## Goal

A PySide6 desktop app that transcribes audio files with OpenAI Whisper,
showing two read-only panels side by side: the transcription in the audio's
original spoken language, and an English translation. Files are picked via a
browser-style address bar / file dialog, support a batch queue, and
auto-save transcripts next to the source file.

## Current state

- `pyproject.toml` already depends on `openai-whisper`; no GUI code exists yet
  (`main.py` is the unmodified PyCharm scaffold).
- The user has an established manual workflow: run Whisper's CLI on WhatsApp
  voice notes (`.opus`/`.ogg` containers), producing `.json`/`.srt`/`.tsv`/
  `.txt`/`.vtt` files next to the source audio. This GUI formalizes and
  extends that workflow with a translation panel.
- Machine has an RTX 3080 Laptop GPU (16 GB VRAM, driver 617.42) but the
  venv's torch build is CPU-only. `ffmpeg` 6.0 is already on PATH.

## Decisions (confirmed with user)

| Decision | Value |
|---|---|
| Whisper model | `medium`, fixed default (no per-run model picker) |
| Compute device | GPU — swap venv torch for a CUDA build |
| File handling | Batch queue, not single-file-only |
| Output persistence | Auto-save next to source file after each run |

## Architecture

Single-window PySide6 app, three stacked regions:

```
┌─────────────────────────────────────────────────────────┐
│ [ address bar: path text field ] [Browse] [Add to Queue] │
├─────────────────────────────────────────────────────────┤
│ Queue: file list with status column                      │
│   WhatsApp Ptt ... .ogg      Done                        │
│   voicemail.m4a              Transcribing...              │
│   note.mp3                   Queued                       │
│                                           [ Start ]        │
├───────────────────────────┬───────────────────────────────┤
│ Original language   [Copy]│ English              [Copy]   │
│ (read-only text panel)    │ (read-only text panel)        │
└───────────────────────────┴───────────────────────────────┘
```

### Components

- **AddressBar widget** — `QLineEdit` (typeable/pasteable path) + **Browse**
  button opening `QFileDialog.getOpenFileNames` with a filter preset to
  ffmpeg-decodable formats: `*.wav *.mp3 *.m4a *.ogg *.opus *.flac *.aac
  *.wma *.mp4 *.mov *.mkv *.webm`, plus "All Files (*)". **Add to Queue**
  appends the current path (or all paths from a multi-select Browse) to the
  queue list, validating the file exists before adding.
- **QueueWidget** — `QListWidget` (or `QTableWidget` if a status column needs
  its own cell) holding one row per file: filename, status
  (`Queued`/`Transcribing`/`Translating`/`Done`/`Error`). Selecting a `Done`
  row loads its cached result into the two text panels. An `Error` row shows
  the exception message as a tooltip.
- **Start button** — disabled while a batch is already running; triggers the
  worker thread to process the queue from the next `Queued` item onward.
- **TranscriptionWorker(QThread)** — owns the loaded Whisper model (loaded
  once, lazily, on first use; reused across the queue — reloading `medium`
  per file would dominate runtime). Processes queued files **strictly
  sequentially** (single GPU — concurrent jobs would just contend for the
  same device and add complexity with no throughput benefit). Emits Qt
  signals back to the main thread:
  - `status_changed(row_index, status)`
  - `result_ready(row_index, original_text, english_text)`
  - `error(row_index, message)`
- **ResultPanels** — two `QPlainTextEdit` widgets in read-only mode, each with
  a **Copy** button (`QApplication.clipboard().setText(...)`).

### Data flow

1. User adds file(s) to the queue (address bar + Browse, or typed path +
   Enter).
2. User clicks **Start**. Main thread hands the queue to
   `TranscriptionWorker` and disables **Start**.
3. For each queued file, in order:
   a. Emit `status_changed(row, "Transcribing")`.
   b. `model.transcribe(path, task="transcribe")` → original-language text.
   c. Emit `status_changed(row, "Translating")`.
   d. `model.transcribe(path, task="translate")` → English text.
   e. Write `<stem>.txt` (original) and `<stem>.en.txt` (English) next to the
      source file.
   f. Emit `result_ready(row, original_text, english_text)` →
      `status_changed(row, "Done")`.
   g. On any exception in (b)–(e): emit `error(row, str(exc))` →
      `status_changed(row, "Error")`, then continue to the next file instead
      of aborting the batch.
4. Main thread updates the queue row's status/tooltip on every signal, and
   repopulates the two panels only when the *currently selected* queue row
   receives a `result_ready` signal (so switching selection mid-batch doesn't
   get clobbered by an unrelated file's result).

### Error handling

- Missing/invalid file path when adding to queue: reject with an inline
  message in the address bar area, don't add a bad row.
- Decode/transcription failure per file: caught in the worker, surfaced as
  `Error` status + tooltip, batch continues.
- Model load failure (e.g., CUDA OOM, missing CUDA runtime): caught once
  before the loop starts; surfaced as a blocking error dialog since no file
  can proceed without a model.

### Setup changes required

- Add `PySide6` to `pyproject.toml` dependencies.
- Replace the CPU-only torch wheel with a CUDA build matching driver 617.42
  (CUDA 12.x series wheel) so `whisper.load_model("medium", device="cuda")`
  actually uses the GPU.
- No ffmpeg install needed — already on PATH.

### Testing

- Unit-testable pieces: address-bar path validation, queue status transitions
  given mocked worker signals, filename derivation for auto-save paths
  (`<stem>.txt` / `<stem>.en.txt` collision handling if a file is re-run).
- The Whisper pipeline itself is not meaningfully unit-testable (external
  model inference) — verify manually by running the two existing WhatsApp
  `.ogg`-family sample files already in the repo root through the GUI and
  comparing output to the existing CLI-generated `.txt` files for sanity.
- GPU path: confirm `torch.cuda.is_available()` is `True` after the torch
  swap, and that `nvidia-smi` shows GPU utilization during a transcription
  run.

## Resolved items

1. **Auto-save format.** Confirmed: only `<stem>.txt` (original) and
   `<stem>.en.txt` (English), no `.srt`/timestamps. Can be revisited later as
   a follow-up feature if timestamped output is wanted.
2. **Sequential-only queue processing.** Confirmed as the simpler, GPU-safe
   default.
