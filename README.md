# Whisper Dual-Language Transcriber

A desktop GUI (PySide6) for transcribing voice notes with OpenAI Whisper —
original language + English translation, synced playback with the timed
transcript, and an optional Claude-powered grammar/idiom breakdown.

## Requirements

- Python 3.13 (see `.python-version`)
- [uv](https://docs.astral.sh/uv/) for dependency management
- [ffmpeg](https://ffmpeg.org/) on your `PATH` (required by Whisper for audio decoding)
- An NVIDIA GPU with CUDA 12.6 drivers (the pinned `torch` build is CUDA-only — see note below if you don't have one)
- An [Anthropic API key](https://console.anthropic.com/settings/keys), only if you want the Grammar tab's analysis feature

## Setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it.
2. Install ffmpeg and make sure it's on your `PATH` (`ffmpeg -version` should work in a terminal).
3. Install dependencies:

   ```bash
   uv sync
   ```

4. Create a `.env` file in the project root with your Anthropic API key (only needed for the Grammar tab):

   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

   `.env` is gitignored — never commit it.

## Running

```bash
uv run main.py
```

## Running tests

```bash
uv run pytest
```

## No CUDA GPU?

`pyproject.toml` pins `torch` to the CUDA 12.6 build. If you're on CPU-only
or a different CUDA version, edit the `[tool.uv.sources]` / `[[tool.uv.index]]`
entries in `pyproject.toml` to point at the appropriate PyTorch index (or
remove the pin to use the default CPU wheel), then re-run `uv sync`.

## Project layout

- `main.py` — entry point
- `whisper_gui/` — application code (main window, transcription worker, queue model, media player, grammar analysis)
- `tests/` — pytest suite
- `plans/` — design and implementation plans for past features
- `data/` — local transcription output (gitignored for personal recordings; see `.gitignore`)

## Contributing

1. Fork the repo and create a branch for your change.
2. Follow the setup steps above to get a working environment.
3. Add or update tests for any behavior change, and make sure `uv run pytest` passes.
4. Open a pull request describing what changed and why.

For anything beyond a small fix, please open an issue first to discuss the
change before investing time in a PR.
