# Chat log — Whisper GUI brainstorm (2026-10-11)

## Request

Build a PySide GUI that uses Whisper to transcribe audio files, with two panels:
one showing the transcription in the original language, one showing an English
translation. Include a browser-style address bar for picking files, and support
valid audio formats including WhatsApp's `.ogg` format.

## Context discovered

- Project `whisper-ogg-translation` already has `openai-whisper` as a dependency
  (`pyproject.toml`), but no GUI code yet — `main.py` is still the PyCharm
  scaffold stub.
- The user has already been running Whisper's CLI manually on WhatsApp voice
  notes — the repo root has `.json`/`.srt`/`.tsv`/`.txt`/`.vtt` output sets for
  several "WhatsApp Ptt ... " audio files.
- The venv's PyTorch build is CPU-only (`2.14.1+cpu`, `torch.cuda.is_available()
  == False`), but the machine has an NVIDIA RTX 3080 Laptop GPU (16 GB VRAM,
  driver 617.42) sitting unused.
- `ffmpeg` (6.0-essentials, gyan.dev build) is already on PATH, so any format
  ffmpeg can decode — including WhatsApp's `.ogg`/`.opus` voice notes — will
  work without extra setup.

## Classification

Treated as **architectural** (new subsystem, no existing GUI flow to extend) —
full brainstorming process: clarifying questions, design, written spec, then
an implementation plan via writing-plans.

## Clarifying questions asked and answers

| Question | Answer |
|---|---|
| Default Whisper model size | **medium** (fixed default, not a per-run dropdown) |
| Use the RTX 3080 GPU? | **Yes** — install a CUDA-enabled torch build |
| Single file or batch queue? | **Batch queue** |
| Auto-save transcripts to disk, or manual export only? | **Auto-save next to source file** |

## Design presented

- **Top: address bar.** `QLineEdit` styled like a browser address bar, a
  **Browse** button (native file dialog filtered to ffmpeg-decodable
  audio/video formats: `.wav .mp3 .m4a .ogg .opus .flac .aac .wma .mp4 .mov
  .mkv .webm`, plus "All Files"), and an **Add to Queue** button.
- **Middle: queue panel.** `QListWidget`/table of queued files with a status
  column (Queued → Transcribing → Translating → Done → Error). Clicking a
  completed item loads its result into the panels below. A **Start** button
  processes the queue strictly sequentially (one GPU, no parallel jobs).
- **Bottom: two read-only text panels** — "Original language" and "English" —
  each with its own **Copy** button.
- **Pipeline:** load the `medium` Whisper model once (CUDA device), kept warm
  across the whole queue. Per file: `model.transcribe(path,
  task="transcribe")` for the original-language text, and
  `model.transcribe(path, task="translate")` for the English text. Runs on a
  background `QThread` so the GUI doesn't freeze; the thread emits signals
  per-file for status changes, results, and errors.
- **Auto-save:** after each file finishes, write `<filename>.txt` (original
  language) and `<filename>.en.txt` (English) next to the source audio file.
- **Error handling:** a failing file is marked `Error` in the queue (exception
  message as tooltip); the queue continues to the next file rather than
  aborting the batch.
- **Setup changes:** swap venv torch for a CUDA build matching driver 617.42
  (CUDA 12.x wheel), add `PySide6` as a dependency.

## Open questions at time of this log (not yet answered)

1. Do the two auto-saved `.txt` files (original + English) suffice, or should
   the app also emit `.srt`/timestamped output per panel like the existing CLI
   workflow?
2. Confirm strictly-sequential queue processing is the right call (vs. any
   other scheduling).

The user's next message asked to save this chat to `.claude/` and the plan to
`plans/` rather than answering those two questions, so the plan file records
them as open assumptions (defaulted conservatively) rather than confirmed
decisions.
