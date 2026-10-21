# Design: Synced playback and on-demand grammar analysis

Status: **draft for review**. Extends `2026-10-11-whisper-gui-transcription-design.md`.

## Intent

The user is using this app to *learn the source language* from real voice
notes (WhatsApp `.ogg`/`.opus`, possibly video files too). Today the app
produces text only. They want to hear the audio/video while reading the
transcript, and to ask Claude for a grammar and idiom explanation of a
file when they choose to.

## Goals

1. Play the audio or video of the file selected in the queue.
2. Study-friendly playback: the transcript is a list of timed lines; the
   current line highlights during playback; clicking a line seeks to it;
   a "repeat this line" toggle loops it; playback speed 0.5x to 1.5x.
3. A **Grammar** tab that, only when the user presses **Analyze**, sends the
   selected file's transcript to the Claude API and shows a grammar
   analysis plus explanations of idioms.
4. Never spend tokens implicitly. Results are cached on disk; re-selecting
   a row shows the cached result for free.

## Non-goals

- Editing transcripts, subtitle burn-in, exporting video.
- Analyzing a single line or selection (the whole file's text is analyzed;
  the user chose file-row granularity).
- A model picker UI, streaming token display, chat follow-up questions.
- Word-level timestamps.

## Anti-goals (a failure even if it "works")

- Any Claude API call without an explicit button press (including on
  selection change, on transcription finish, or at startup).
- Losing or silently overwriting existing transcripts (the app already
  backs up to `.bak`; keep that behavior).
- Blocking the UI thread during transcription or the API call.

## Current state (verified in code)

- `whisper_gui/transcription.py` returns only `result["text"]`; segment
  timestamps are discarded. Original and English are two separate Whisper
  passes (`task="transcribe"` and `task="translate"`), so their segments do
  not align one-to-one.
- `main_window.py`: queue `QListWidget`; two read-only `QPlainTextEdit`
  panels fed by `QueueItem.original_text` / `english_text`.
- Existing transcripts on disk are `.txt` only (no timing). Whisper's CLI
  `.srt/.json` files from the user's earlier manual runs exist in `data/`.
- Stack: Python 3.13, PySide6, openai-whisper (CUDA torch), uv, pytest.
  `ffmpeg` is on PATH. File filter already includes `.mp4 .mov .mkv .webm`.

## Design

### 0. Loading existing transcripts (confirmed by the user)

When a file is added to the queue and `<stem>.txt` and `<stem>.en.txt`
already exist beside it, the row loads them as Done without re-running
Whisper. It also loads `<stem>.srt` / `<stem>.en.srt` timing if present,
and `<stem>.grammar.md` if present. Rows with only `.txt` files play
without highlighting and show the "no timing data" note. Start only
processes rows that are still Queued, as today.

### 1. Timing data

- `transcribe_original` / `translate_to_english` return text **and**
  segments (`start`, `end`, `text`) from Whisper's result.
- `save_transcripts` additionally writes `<stem>.srt` (original) and
  `<stem>.en.srt` (English), with the existing `.bak` safety behavior.
- `QueueItem` gains `original_segments` and `english_segments`.
- Loading timing for a file: use the in-memory segments if transcribed this
  session; otherwise parse `<stem>.srt` / `<stem>.en.srt` if present;
  otherwise the file plays without highlighting and the panel shows a
  "no timing data, re-run to enable highlighting" note.

### 2. Player

- `QMediaPlayer` + `QAudioOutput` + `QVideoWidget` (PySide6 QtMultimedia).
- Controls bar: play/pause, seek slider, time readout, speed selector,
  repeat-line toggle.
- The video pane is shown only for files that have a video stream; audio
  files show controls only. Selecting a different queue row stops playback
  and loads the new file.
- Layout: controls (and the video pane when present) sit between the queue
  list and the transcript panels.

### 3. Synced transcript

- The original-language panel becomes a list of timed lines (one per
  segment) with per-line styling for the current line. The Copy button
  still copies the full plain text.
- Highlight follows `positionChanged`. Click on a line seeks to its start.
  Repeat-line loops between the line's start and end.
- English panel: highlight the English segment overlapping the current
  time (approximate by nature; the user accepted this). Click-to-seek is
  also available there.

### 4. Grammar tab

- A tab beside the transcript panels (the transcript panels remain the
  default view). It contains an **Analyze** button, a status line, and a
  read-only rendered result area.
- **Analyze** runs on a worker thread, enabled only when the selected row
  is Done. It sends the original text and the English text (as meaning
  reference) to Claude.
- Requested output (prompt is the builder's to write, within these
  bounds): per-sentence breakdown with tense/mood and key constructions;
  agreement and notable grammar points; a short vocabulary list with
  dictionary forms; **idioms and colloquial expressions explained**, with
  literal vs actual meaning. Explanations are written in English. The
  source language is whatever Whisper detected (surface the detected
  language to the prompt).
- Result saved to `<stem>.grammar.md` beside the transcripts (backup like
  other outputs when re-run). Selecting a row loads this file if present.
  Pressing Analyze again on a cached row asks for confirmation ("this will
  use API tokens again").
- Errors (missing key, network, rate limit, refusal) show in the status
  line; nothing is saved on failure.

### Decisions I made (not confirmed by the user)

- Model: `claude-opus-5-5` through the official `anthropic` Python SDK,
  default client (reads credentials from environment / `ant auth login`
  profile). Kept as a single constant so it is easy to change to
  `claude-sonnet-5-5`.
- Use the repo's existing convention (`plans/`) for this document.
- Cache file format is Markdown; the result view renders it.
- Speed range 0.5x to 1.5x.
- Credentials: environment / `ant auth login` only. No key storage or key
  prompt in the app; a missing key shows in the status line. Add
  `anthropic` to `pyproject.toml`.
- Language: do not persist Whisper's detected language. The prompt tells
  Claude to identify the source language itself, which also works for
  files loaded from disk.
- Outputs are only read and written beside the media file. The Whisper CLI
  files in `data/` are never touched. Re-transcribing regenerates `.srt`
  with the existing `.bak` behavior.
- Repeat-line applies only to the original-language panel's current line.
  Clicking an English line seeks to its start and does not set a repeat.
- Playback errors (a codec Qt cannot play) show in the player's status
  area and the app carries on. No transcoding fallback. The builder should
  verify early that the installed PySide6 plays `.ogg`/`.opus` on this
  machine and report if not.

### Left to the builder

Exact layout and widget choices, prompt wording, SRT parsing details,
handling of very long transcripts (do not silently truncate; surface an
error or message), tests (follow the existing pytest style; the Claude
call and QMediaPlayer should be behind seams so they can be faked).
