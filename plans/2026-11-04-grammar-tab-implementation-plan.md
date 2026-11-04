# Grammar Tab (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Grammar tab that, on an explicit Analyze button press, sends the selected row's original and English transcripts to Claude and shows a cached grammar/idiom analysis.

**Architecture:** A new `grammar_analysis.py` module (prompt building, length guard, Claude client, file I/O) mirrors the existing `transcription.py`; a new `GrammarWorker` QThread mirrors `TranscriptionWorker`; a new `GrammarPanel` widget is added as a second tab beside the existing transcript panels in `main_window.py`, which already hosts the queue, media player, and transcript panels from Plan A (branch `whisper-synced-playback`, commits `0aeff8a..2386aab`).

**Tech Stack:** Python 3.13, PySide6 (`QThread`, `QTabWidget`, `QTextBrowser`), `anthropic` (official SDK), `python-dotenv`, `uv`, `pytest`.

**Spec:** `plans/2026-10-21-playback-and-grammar-design.md` (section 4 "Grammar tab", the relevant parts of section 0, and the "Decisions" sections — section 2/3 player and synced-transcript work is already shipped).

## Global Constraints

- Model: `claude-sonnet-5-5` (constant, named `MODEL` in `grammar_analysis.py`). The design's confirmed decision named `claude-opus-5-5`, but its own "Decisions I made" note said the constant was kept single-source specifically so it could be swapped to Sonnet, and the user chose that swap when reviewing this plan on 2026-11-04.
- Credentials: `ANTHROPIC_API_KEY` from the environment or the gitignored project `.env` file only; no in-app key storage or prompt UI; a missing/invalid key surfaces in the Grammar tab's status line, never a crash.
- Cache file: `<stem>.grammar.md` beside the media file, using the existing `.bak`-on-overwrite backup behavior (`_backup_if_exists` from `transcription.py`).
- No Claude API call without an explicit Analyze button press — never on selection change, transcription finish, or app startup (anti-goal).
- The API call runs on a background `QThread`; the UI thread is never blocked (anti-goal).
- Analyze is enabled only when the selected row's status is `Done`.
- Re-running Analyze on a row that already has a cached result asks for confirmation ("this will use API tokens again") before calling the API again.
- Very long transcripts are never silently truncated — they raise a surfaced error instead. `MAX_PROMPT_CHARS = 100_000` is this plan's own call, since the design explicitly leaves the exact bound to the builder.
- Errors (missing key, network, rate limit, refusal, too-long) show in the Grammar tab's status line; nothing is written to disk on failure.
- Outputs are only read/written beside the media file; the `data/` directory is never touched.
- The prompt has Claude identify the source language itself — Whisper's detected language is never persisted or passed. (The design's confirmed "Decisions" section supersedes the earlier draft text in section 4, which mentioned surfacing Whisper's detected language.)
- Any test exercising `get_client()` must monkeypatch `load_dotenv` to a no-op and clear `ANTHROPIC_API_KEY` from the environment first, so it never reads the project's real `.env` file (which now holds a live key).

## Review Focus

- Very long transcripts must not be silently truncated — `validate_length`/`analyze` raise a clear error instead of truncating. Pinned in Task 1 (`test_validate_length_raises_when_combined_text_exceeds_max_chars`) and Task 3 (`test_worker_emits_error_and_saves_nothing_when_text_is_too_long`).
- A missing/invalid API key must surface as an error in the status line, not crash the app or silently do nothing. Pinned in Task 1 (`test_get_client_raises_when_no_api_key_is_configured`), Task 3 (`test_worker_emits_error_and_saves_nothing_when_client_construction_fails`), Task 5 (`test_grammar_error_shows_in_status_line_and_nothing_is_saved`).
- Re-running Analyze on a row that already has a cached result must ask for confirmation before spending tokens again, and declining must not call the API. Pinned in Task 5 (`test_declining_the_reanalyze_confirmation_does_not_start_a_worker`, `test_accepting_the_reanalyze_confirmation_starts_a_new_worker`).
- Closing the app while a grammar analysis is in flight must not crash or silently abandon the running thread. Pinned in Task 5 (`test_close_event_waits_for_a_running_grammar_worker_before_accepting`).
- The Analyze action must stay inert for a row that is not yet `Done` (Queued/Transcribing/Translating/Error), so it can never run on text that doesn't exist yet. Pinned in Task 5 (`test_analyze_disabled_for_a_row_that_is_not_done`, `test_clicking_analyze_noops_for_a_row_that_is_not_done`).

---

### Task 1: `grammar_analysis.py` — prompt, Claude client, and file I/O

**Files:**
- Create: `whisper_gui/grammar_analysis.py`
- Modify: `pyproject.toml` (add `anthropic`, `python-dotenv`)
- Test: `tests/test_grammar_analysis.py`

**Interfaces:**
- Consumes: `whisper_gui.transcription._backup_if_exists(path: Path) -> None`
- Produces:
  - `MODEL: str = "claude-sonnet-5-5"`
  - `MAX_PROMPT_CHARS: int = 100_000`
  - `build_prompt(original_text: str, english_text: str) -> str`
  - `validate_length(original_text: str, english_text: str) -> None` (raises `ValueError`)
  - `get_client() -> anthropic.Anthropic` (module-level singleton `_client`)
  - `analyze(client, original_text: str, english_text: str) -> str`
  - `output_path(source: Path) -> Path`
  - `save_analysis(source: Path, content: str) -> Path`
  - `load_existing_analysis(source: Path) -> str | None`

- [ ] **Step 1: Add dependencies**

Run: `uv add anthropic python-dotenv`
Expected: `pyproject.toml` and `uv.lock` updated, packages installed into `.venv`.

- [ ] **Step 2: Verify the new imports resolve**

Run: `uv run python -c "import anthropic, dotenv"`
Expected: exits 0, no output.

- [ ] **Step 3: Write failing tests for `build_prompt`**

```python
def test_build_prompt_includes_both_texts():
    prompt = build_prompt("hola mundo", "hello world")
    assert "hola mundo" in prompt
    assert "hello world" in prompt


def test_build_prompt_requests_required_sections():
    prompt = build_prompt("x", "y").lower()
    for keyword in ("tense", "agreement", "vocabulary", "idiom"):
        assert keyword in prompt
```

- [ ] **Step 4: Run tests, verify they fail**

Run: `uv run pytest tests/test_grammar_analysis.py -v`
Expected: FAIL — `build_prompt` not defined / ImportError.

- [ ] **Step 5: Implement `build_prompt(original_text: str, english_text: str) -> str`**

Compose an English-language instruction string that embeds both texts and asks for: (a) a per-sentence breakdown with tense/mood and key constructions, (b) agreement and notable grammar points, (c) a short vocabulary list with dictionary forms, (d) idioms and colloquial expressions with literal vs. actual meaning, and tells Claude to identify the source language itself (per the Global Constraints note — do not reference a pre-detected language).

- [ ] **Step 6: Run tests, verify they pass**

Run: `uv run pytest tests/test_grammar_analysis.py -v`
Expected: PASS.

- [ ] **Step 7: Write failing tests for `validate_length`**

```python
def test_validate_length_allows_text_under_the_limit():
    validate_length("short original", "short english")  # does not raise


def test_validate_length_raises_when_combined_text_exceeds_max_chars():
    long_text = "x" * (MAX_PROMPT_CHARS + 1)
    with pytest.raises(ValueError):
        validate_length(long_text, "")
```

- [ ] **Step 8: Run tests, verify they fail**

Run: `uv run pytest tests/test_grammar_analysis.py -v`
Expected: FAIL — `validate_length` not defined.

- [ ] **Step 9: Implement `validate_length(original_text: str, english_text: str) -> None`**

Raise `ValueError(f"Transcript too long to analyze ({combined_len} characters, max {MAX_PROMPT_CHARS}).")` when `len(original_text) + len(english_text) > MAX_PROMPT_CHARS`.

- [ ] **Step 10: Run tests, verify they pass**

Run: `uv run pytest tests/test_grammar_analysis.py -v`
Expected: PASS.

- [ ] **Step 11: Write failing tests for `analyze`**

```python
from types import SimpleNamespace


class _FakeMessages:
    def create(self, **kwargs):
        self.received_kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(text="# Grammar analysis\n...")])


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


def test_analyze_returns_the_text_of_the_first_content_block():
    result = analyze(_FakeClient(), "hola", "hello")
    assert result == "# Grammar analysis\n..."


def test_analyze_sends_the_configured_model_and_the_built_prompt():
    client = _FakeClient()
    analyze(client, "hola", "hello")
    assert client.messages.received_kwargs["model"] == MODEL
    assert "hola" in client.messages.received_kwargs["messages"][0]["content"]


def test_analyze_raises_without_calling_the_client_when_text_is_too_long():
    client = _FakeClient()
    long_text = "x" * (MAX_PROMPT_CHARS + 1)
    with pytest.raises(ValueError):
        analyze(client, long_text, "")
    assert not hasattr(client.messages, "received_kwargs")
```

- [ ] **Step 12: Run tests, verify they fail**

Run: `uv run pytest tests/test_grammar_analysis.py -v`
Expected: FAIL — `analyze` not defined.

- [ ] **Step 13: Implement `analyze(client, original_text: str, english_text: str) -> str`**

Call `validate_length` first. Then `client.messages.create(model=MODEL, max_tokens=4096, messages=[{"role": "user", "content": build_prompt(original_text, english_text)}])` and return `response.content[0].text`.

- [ ] **Step 14: Run tests, verify they pass**

Run: `uv run pytest tests/test_grammar_analysis.py -v`
Expected: PASS.

- [ ] **Step 15: Write failing tests for `get_client`**

```python
def test_get_client_raises_when_no_api_key_is_configured(monkeypatch):
    import whisper_gui.grammar_analysis as grammar_analysis
    monkeypatch.setattr(grammar_analysis, "load_dotenv", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    grammar_analysis._client = None
    with pytest.raises(Exception):
        grammar_analysis.get_client()


def test_get_client_returns_the_same_instance_on_a_second_call(monkeypatch):
    import whisper_gui.grammar_analysis as grammar_analysis
    monkeypatch.setattr(grammar_analysis, "load_dotenv", lambda: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    grammar_analysis._client = None
    first = grammar_analysis.get_client()
    second = grammar_analysis.get_client()
    assert first is second
```

Both tests must monkeypatch `load_dotenv` to a no-op — otherwise `get_client()` would call the real `load_dotenv()` and pick up this project's actual `.env` file (which now holds a live key), making these tests order-dependent and occasionally pass/fail for the wrong reason.

- [ ] **Step 16: Run tests, verify they fail**

Run: `uv run pytest tests/test_grammar_analysis.py -v`
Expected: FAIL — `get_client` not defined.

- [ ] **Step 17: Implement `get_client() -> anthropic.Anthropic`**

```python
_client = None

def get_client():
    global _client
    if _client is None:
        load_dotenv()
        _client = anthropic.Anthropic()
    return _client
```

With `import anthropic` and `from dotenv import load_dotenv` at module top. `anthropic.Anthropic()` reads `ANTHROPIC_API_KEY` from the environment itself and raises if it's missing.

- [ ] **Step 18: Run tests, verify they pass**

Run: `uv run pytest tests/test_grammar_analysis.py -v`
Expected: PASS.

- [ ] **Step 19: Write failing tests for `output_path`, `save_analysis`, `load_existing_analysis`**

```python
def test_output_path_appends_grammar_md_suffix(tmp_path):
    source = tmp_path / "voice.ogg"
    assert output_path(source) == tmp_path / "voice.grammar.md"


def test_save_analysis_writes_file_and_returns_its_path(tmp_path):
    source = tmp_path / "voice.ogg"
    path = save_analysis(source, "# Analysis")
    assert path == tmp_path / "voice.grammar.md"
    assert path.read_text(encoding="utf-8") == "# Analysis"


def test_save_analysis_backs_up_an_existing_file(tmp_path):
    source = tmp_path / "voice.ogg"
    existing = tmp_path / "voice.grammar.md"
    existing.write_text("old", encoding="utf-8")
    save_analysis(source, "new")
    assert (tmp_path / "voice.grammar.md.bak").read_text(encoding="utf-8") == "old"
    assert existing.read_text(encoding="utf-8") == "new"


def test_load_existing_analysis_returns_none_when_no_file_exists(tmp_path):
    assert load_existing_analysis(tmp_path / "voice.ogg") is None


def test_load_existing_analysis_returns_the_file_contents(tmp_path):
    source = tmp_path / "voice.ogg"
    (tmp_path / "voice.grammar.md").write_text("# Analysis", encoding="utf-8")
    assert load_existing_analysis(source) == "# Analysis"
```

- [ ] **Step 20: Run tests, verify they fail**

Run: `uv run pytest tests/test_grammar_analysis.py -v`
Expected: FAIL — the three functions are not defined.

- [ ] **Step 21: Implement `output_path`, `save_analysis`, `load_existing_analysis`**

`output_path(source)` returns `source.with_name(source.stem + ".grammar.md")`. `save_analysis` calls the imported `_backup_if_exists(output_path(source))` then writes `content` with `encoding="utf-8"` and returns the path. `load_existing_analysis` returns `None` if the path doesn't exist, else its UTF-8 text (no decode-error guard needed beyond what `_load_segments`-style code already established — this file is never machine-generated from untrusted binary, it's Claude's own Markdown output).

- [ ] **Step 22: Run tests, verify they pass**

Run: `uv run pytest tests/test_grammar_analysis.py -v`
Expected: PASS, full file.

- [ ] **Step 23: Commit**

```bash
git add whisper_gui/grammar_analysis.py tests/test_grammar_analysis.py pyproject.toml uv.lock
git commit -m "feat: add Claude-based grammar analysis logic"
```

---

### Task 2: `QueueModel` gains grammar storage

**Files:**
- Modify: `whisper_gui/queue_model.py`
- Test: `tests/test_queue_model.py`

**Interfaces:**
- Produces: `QueueItem.grammar_text: str | None = None` (new field); `QueueModel.set_grammar(index: int, text: str) -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_new_queue_item_has_no_grammar_text_by_default(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "voice.ogg")
    assert model[0].grammar_text is None


def test_set_grammar_stores_text_without_changing_status(tmp_path):
    model = QueueModel()
    model.add(tmp_path / "voice.ogg")
    model.set_result(0, "hola", [], "hello", [])
    model.set_grammar(0, "# Analysis")
    assert model[0].grammar_text == "# Analysis"
    assert model[0].status == QueueStatus.DONE
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_queue_model.py -v`
Expected: FAIL — `grammar_text` / `set_grammar` not defined.

- [ ] **Step 3: Implement**

Add `grammar_text: str | None = None` to the `QueueItem` dataclass. Add to `QueueModel`:

```python
def set_grammar(self, index: int, text: str) -> None:
    self._items[index].grammar_text = text
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_queue_model.py -v`
Expected: PASS, full file.

- [ ] **Step 5: Commit**

```bash
git add whisper_gui/queue_model.py tests/test_queue_model.py
git commit -m "feat: let QueueModel store a cached grammar analysis per row"
```

---

### Task 3: `GrammarWorker`

**Files:**
- Create: `whisper_gui/grammar_worker.py`
- Test: `tests/test_grammar_worker.py`

**Interfaces:**
- Consumes: `grammar_analysis.get_client() -> client` (Task 1), `grammar_analysis.analyze(client, original_text, english_text) -> str` (Task 1), `grammar_analysis.save_analysis(source, content) -> Path` (Task 1)
- Produces: `GrammarWorker(QThread)` with `__init__(self, index: int, path: Path, original_text: str, english_text: str, parent=None)`, signals `status_changed = Signal(int, str)`, `result_ready = Signal(int, str)`, `error = Signal(int, str)`

- [ ] **Step 1: Write failing tests**

```python
from types import SimpleNamespace

from whisper_gui import grammar_worker as grammar_worker_module
from whisper_gui.grammar_worker import GrammarWorker


class _FakeMessages:
    def create(self, **kwargs):
        return SimpleNamespace(content=[SimpleNamespace(text="# Analysis")])


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


def test_worker_saves_result_and_emits_it_on_success(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(grammar_worker_module, "get_client", lambda: _FakeClient())
    path = tmp_path / "voice.ogg"
    w = GrammarWorker(0, path, "hola", "hello")
    statuses, results = [], []
    w.status_changed.connect(lambda i, s: statuses.append((i, s)))
    w.result_ready.connect(lambda i, text: results.append((i, text)))

    w.run()

    assert results == [(0, "# Analysis")]
    assert statuses == [(0, "Analyzing"), (0, "Done")]
    assert (tmp_path / "voice.grammar.md").read_text(encoding="utf-8") == "# Analysis"


def test_worker_emits_error_and_saves_nothing_when_client_construction_fails(qapp, tmp_path, monkeypatch):
    def _raise():
        raise RuntimeError("missing API key")

    monkeypatch.setattr(grammar_worker_module, "get_client", _raise)
    path = tmp_path / "voice.ogg"
    w = GrammarWorker(0, path, "hola", "hello")
    errors, statuses = [], []
    w.error.connect(lambda i, m: errors.append((i, m)))
    w.status_changed.connect(lambda i, s: statuses.append((i, s)))

    w.run()

    assert errors == [(0, "missing API key")]
    assert statuses == [(0, "Analyzing"), (0, "Error")]
    assert not (tmp_path / "voice.grammar.md").exists()


def test_worker_emits_error_and_saves_nothing_when_text_is_too_long(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(grammar_worker_module, "get_client", lambda: _FakeClient())
    path = tmp_path / "voice.ogg"
    long_text = "x" * 200_000
    w = GrammarWorker(0, path, long_text, "")
    errors = []
    w.error.connect(lambda i, m: errors.append((i, m)))

    w.run()

    assert len(errors) == 1 and errors[0][0] == 0
    assert not (tmp_path / "voice.grammar.md").exists()
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_grammar_worker.py -v`
Expected: FAIL — `grammar_worker` module / `GrammarWorker` not found.

- [ ] **Step 3: Implement `GrammarWorker`**

```python
class GrammarWorker(QThread):
    status_changed = Signal(int, str)
    result_ready = Signal(int, str)
    error = Signal(int, str)

    def __init__(self, index, path, original_text, english_text, parent=None):
        super().__init__(parent)
        self.index = index
        self.path = path
        self.original_text = original_text
        self.english_text = english_text

    def run(self) -> None:
        self.status_changed.emit(self.index, "Analyzing")
        try:
            client = get_client()
            result = analyze(client, self.original_text, self.english_text)
            save_analysis(self.path, result)
        except Exception as exc:
            self.error.emit(self.index, str(exc))
            self.status_changed.emit(self.index, "Error")
            return
        self.result_ready.emit(self.index, result)
        self.status_changed.emit(self.index, "Done")
```

Import `get_client, analyze, save_analysis` from `.grammar_analysis`, and `QThread, Signal` from `PySide6.QtCore`, matching `worker.py`'s existing style.

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_grammar_worker.py -v`
Expected: PASS, full file.

- [ ] **Step 5: Commit**

```bash
git add whisper_gui/grammar_worker.py tests/test_grammar_worker.py
git commit -m "feat: add background worker for grammar analysis"
```

---

### Task 4: `GrammarPanel` widget

**Files:**
- Create: `whisper_gui/grammar_panel.py`
- Test: `tests/test_grammar_panel.py`

**Interfaces:**
- Produces: `GrammarPanel(QWidget)` with signal `analyze_requested = Signal()`; attributes `analyze_button`, `status_label`, `result_view`; methods `set_analyze_enabled(enabled: bool) -> None`, `set_status(message: str) -> None`, `set_result(markdown_text: str) -> None`, `clear() -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_clicking_analyze_emits_analyze_requested(qapp):
    panel = GrammarPanel()
    received = []
    panel.analyze_requested.connect(lambda: received.append(True))
    panel.analyze_button.click()
    assert received == [True]


def test_set_result_shows_the_analysis_text(qapp):
    panel = GrammarPanel()
    panel.set_result("# Heading\nSome analysis text.")
    assert "Some analysis text." in panel.result_view.toPlainText()


def test_set_status_updates_the_status_label(qapp):
    panel = GrammarPanel()
    panel.set_status("Analyzing...")
    assert panel.status_label.text() == "Analyzing..."


def test_set_analyze_enabled_toggles_the_button(qapp):
    panel = GrammarPanel()
    panel.set_analyze_enabled(False)
    assert panel.analyze_button.isEnabled() is False
    panel.set_analyze_enabled(True)
    assert panel.analyze_button.isEnabled() is True


def test_clear_resets_result_and_status(qapp):
    panel = GrammarPanel()
    panel.set_result("text")
    panel.set_status("Analyzing...")
    panel.clear()
    assert panel.result_view.toPlainText() == ""
    assert panel.status_label.text() == ""
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_grammar_panel.py -v`
Expected: FAIL — `GrammarPanel` not found.

- [ ] **Step 3: Implement `GrammarPanel`**

`QPushButton("Analyze")` wired to emit `analyze_requested` on click; `QLabel` for `status_label`; `QTextBrowser` (read-only) for `result_view`, using `.setMarkdown(markdown_text)` in `set_result` to render it. `clear()` calls `result_view.clear()` and `status_label.setText("")`. Stack them vertically in a `QVBoxLayout`.

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_grammar_panel.py -v`
Expected: PASS, full file.

- [ ] **Step 5: Commit**

```bash
git add whisper_gui/grammar_panel.py tests/test_grammar_panel.py
git commit -m "feat: add GrammarPanel widget"
```

---

### Task 5: Wire the Grammar tab into `MainWindow`

**Files:**
- Modify: `whisper_gui/main_window.py`
- Test: `tests/test_main_window.py`

**Interfaces:**
- Consumes: `GrammarPanel` (Task 4), `GrammarWorker` (Task 3), `QueueModel.set_grammar` (Task 2), `grammar_analysis.load_existing_analysis` (Task 1)
- Produces: `MainWindow.grammar_panel`, `MainWindow.grammar_worker: GrammarWorker | None`, `MainWindow.content_tabs: QTabWidget`, `MainWindow._on_analyze_clicked`, `_on_grammar_result`, `_on_grammar_error`, `_on_grammar_finished`, `_update_grammar_panel_for_row`

- [ ] **Step 1: Write failing tests**

```python
from types import SimpleNamespace

from whisper_gui import grammar_worker as grammar_worker_module


class _FakeMessages:
    def create(self, **kwargs):
        return SimpleNamespace(content=[SimpleNamespace(text="# Analysis")])


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


class _SlowMessages:
    def create(self, **kwargs):
        time.sleep(0.2)
        return SimpleNamespace(content=[SimpleNamespace(text="# Analysis")])


class _SlowClient:
    def __init__(self):
        self.messages = _SlowMessages()


def test_main_window_has_a_grammar_tab_beside_the_transcript_tab(qapp, tmp_path):
    window = MainWindow()
    assert window.content_tabs.count() == 2
    assert window.content_tabs.tabText(0) == "Transcript"
    assert window.content_tabs.tabText(1) == "Grammar"


def test_analyze_disabled_for_a_row_that_is_not_done(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    assert window.grammar_panel.analyze_button.isEnabled() is False


def test_clicking_analyze_noops_for_a_row_that_is_not_done(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_analyze_clicked()
    assert window.grammar_worker is None


def test_clicking_analyze_on_a_done_row_runs_the_worker_and_updates_model_and_panel(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(grammar_worker_module, "get_client", lambda: _FakeClient())
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])

    window._on_analyze_clicked()
    assert window.grammar_worker is not None
    window.grammar_worker.wait()
    qapp.processEvents()

    assert window.queue_model[0].grammar_text == "# Analysis"
    assert "Analysis" in window.grammar_panel.result_view.toPlainText()


def test_declining_the_reanalyze_confirmation_does_not_start_a_worker(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])
    window.queue_model.set_grammar(0, "# Old analysis")

    window._on_analyze_clicked()

    assert window.grammar_worker is None


def test_accepting_the_reanalyze_confirmation_starts_a_new_worker(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(grammar_worker_module, "get_client", lambda: _FakeClient())
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])
    window.queue_model.set_grammar(0, "# Old analysis")

    window._on_analyze_clicked()

    assert window.grammar_worker is not None
    window.grammar_worker.wait()


def test_grammar_error_shows_in_status_line_and_nothing_is_saved(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])

    window._on_grammar_error(0, "rate limit exceeded")

    assert window.grammar_panel.status_label.text() == "rate limit exceeded"
    assert window.queue_model[0].grammar_text is None


def test_close_event_waits_for_a_running_grammar_worker_before_accepting(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(grammar_worker_module, "get_client", lambda: _SlowClient())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    window = MainWindow()
    window._add_path(str(source))
    window.queue_list.setCurrentRow(0)
    window._on_result_ready(0, "hola", [], "hello", [])

    window._on_analyze_clicked()
    for _ in range(100):
        if window.grammar_worker is not None and window.grammar_worker.isRunning():
            break
        time.sleep(0.01)
    assert window.grammar_worker.isRunning()

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted()
    assert window.grammar_worker.isRunning() is False


def test_add_path_loads_existing_grammar_analysis(qapp, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")
    (tmp_path / "voice.txt").write_text("hola", encoding="utf-8")
    (tmp_path / "voice.en.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "voice.grammar.md").write_text("# Analysis", encoding="utf-8")

    window = MainWindow()
    window._add_path(str(source))

    assert window.queue_model[0].grammar_text == "# Analysis"


def test_add_path_still_adds_row_when_existing_grammar_file_load_raises(qapp, tmp_path, monkeypatch):
    import whisper_gui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module, "load_existing_analysis",
        lambda path: (_ for _ in ()).throw(RuntimeError("corrupt")),
    )
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"fake")

    window = MainWindow()
    window._add_path(str(source))

    assert len(window.queue_model) == 1
    assert window.queue_model[0].grammar_text is None
```

`time` and `QCloseEvent` are already imported at the top of `tests/test_main_window.py`; add `from PySide6.QtWidgets import QMessageBox` only if not already present (it already is).

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_main_window.py -v`
Expected: FAIL — `content_tabs` / `grammar_panel` / `grammar_worker` / `_on_analyze_clicked` etc. not found.

- [ ] **Step 3: Add imports and construct the Grammar tab in `__init__`**

Add to the top of `main_window.py`: `from PySide6.QtWidgets import QTabWidget` (alongside the existing `QtWidgets` imports), `from .grammar_analysis import load_existing_analysis`, `from .grammar_panel import GrammarPanel`, `from .grammar_worker import GrammarWorker`.

In `__init__`, after `panels_widget` is built (currently added directly to `right_splitter`) and before `right_splitter = QSplitter(...)`:

```python
self.grammar_panel = GrammarPanel()
self.grammar_panel.analyze_requested.connect(self._on_analyze_clicked)
self.grammar_worker: GrammarWorker | None = None

self.content_tabs = QTabWidget()
self.content_tabs.addTab(panels_widget, "Transcript")
self.content_tabs.addTab(self.grammar_panel, "Grammar")
```

Change `right_splitter.addWidget(panels_widget)` to `right_splitter.addWidget(self.content_tabs)` (the stretch factors stay as they are — they already target index 1).

- [ ] **Step 4: Load a cached grammar analysis in `_add_path`**

After the existing `loaded`/`load_existing_transcripts` block in `_add_path` (both the `if loaded is not None:` and `else:` branches have already run), add:

```python
try:
    grammar_text = load_existing_analysis(path)
except Exception:
    grammar_text = None
if grammar_text is not None:
    self.queue_model.set_grammar(index, grammar_text)
```

- [ ] **Step 5: Keep the Grammar tab in sync with the selected row**

Add a new method:

```python
def _update_grammar_panel_for_row(self, row: int) -> None:
    if row < 0 or row >= len(self.queue_model):
        self.grammar_panel.clear()
        self.grammar_panel.set_analyze_enabled(False)
        return
    item = self.queue_model[row]
    if item.grammar_text:
        self.grammar_panel.set_result(item.grammar_text)
    else:
        self.grammar_panel.clear()
    busy = self.grammar_worker is not None and self.grammar_worker.isRunning()
    self.grammar_panel.set_analyze_enabled(item.status == QueueStatus.DONE and not busy)
```

Call `self._update_grammar_panel_for_row(row)` at the end of `_on_selection_changed` (both in its early-return branch for `row < 0`, and after `self.media_player.load(item.path)` in the main branch).

- [ ] **Step 6: Implement `_on_analyze_clicked`**

```python
def _on_analyze_clicked(self) -> None:
    row = self.queue_list.currentRow()
    if row < 0:
        return
    item = self.queue_model[row]
    if item.status != QueueStatus.DONE:
        return
    if self.grammar_worker is not None and self.grammar_worker.isRunning():
        return
    if item.grammar_text is not None:
        response = QMessageBox.question(
            self,
            "Re-analyze",
            "This will use API tokens again. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
    self.grammar_panel.set_analyze_enabled(False)
    self.grammar_panel.set_status("Analyzing...")
    self.grammar_worker = GrammarWorker(row, item.path, item.original_text or "", item.english_text or "")
    self.grammar_worker.result_ready.connect(self._on_grammar_result)
    self.grammar_worker.error.connect(self._on_grammar_error)
    self.grammar_worker.finished.connect(self._on_grammar_finished)
    self.grammar_worker.start()
```

- [ ] **Step 7: Implement the result, error, and finished handlers**

```python
def _on_grammar_result(self, index: int, text: str) -> None:
    self.queue_model.set_grammar(index, text)
    if self.queue_list.currentRow() == index:
        self.grammar_panel.set_result(text)

def _on_grammar_error(self, index: int, message: str) -> None:
    if self.queue_list.currentRow() == index:
        self.grammar_panel.set_status(message)

def _on_grammar_finished(self) -> None:
    self.grammar_worker = None
    self._update_grammar_panel_for_row(self.queue_list.currentRow())
```

- [ ] **Step 8: Extend `closeEvent` to also wait for a running `GrammarWorker`**

Replace the body of `closeEvent` with:

```python
def closeEvent(self, event) -> None:
    transcription_running = self.worker is not None and self.worker.isRunning()
    grammar_running = self.grammar_worker is not None and self.grammar_worker.isRunning()
    if transcription_running or grammar_running:
        response = QMessageBox.question(
            self,
            "Work in progress",
            "A transcription or grammar analysis is still running. Quit anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        if transcription_running:
            self.worker.request_stop()
            self.worker.wait()
        if grammar_running:
            self.grammar_worker.wait()
    event.accept()
```

- [ ] **Step 9: Run the whole test file, verify it passes**

Run: `uv run pytest tests/test_main_window.py -v`
Expected: PASS, full file (new tests and all pre-existing ones).

- [ ] **Step 10: Run the full project test suite**

Run: `uv run pytest`
Expected: PASS, full suite, 0 failures.

- [ ] **Step 11: Commit**

```bash
git add whisper_gui/main_window.py tests/test_main_window.py
git commit -m "feat: add the Grammar tab to MainWindow"
```

---

## Self-Review

**Spec coverage:** Section 0's `.grammar.md` loading → Task 5 Step 4. Section 4's Analyze button, worker-thread call, Done-only gating, prompt content, `.grammar.md` cache + `.bak` behavior, re-analyze confirmation, error surfacing → Tasks 1, 3, 4, 5. "Decisions" section's model constant, no-detected-language-persistence, credentials-via-env/`.env` → Global Constraints and Task 1. No task covers "Non-goals" (editing transcripts, model picker, streaming, word-level timestamps, single-line analysis) because the plan simply never builds them — nothing to pin.

**Step scan:** Every code step names the exact signature and file; algorithm bodies are given only for `analyze`, `get_client`, `GrammarWorker.run`, `_on_analyze_clicked`, `_update_grammar_panel_for_row`, and `closeEvent` — the actual integration decisions this plan exists to pin. `build_prompt`'s exact wording and `GrammarPanel`'s exact widget layout are left to the implementer, matching the design's own "left to the builder" note on prompt wording and widget choices.

**Type consistency:** `GrammarWorker.__init__(index, path, original_text, english_text)` (Task 3) matches the call in `_on_analyze_clicked` (Task 5). `result_ready = Signal(int, str)` matches `_on_grammar_result(self, index: int, text: str)`. `error = Signal(int, str)` matches `_on_grammar_error(self, index: int, message: str)`. `QueueModel.set_grammar(index, text)` (Task 2) matches both `GrammarWorker`'s save-then-model-update flow (handled in `_on_grammar_result`, not inside the worker) and `_add_path`'s load path (Task 5 Step 4).

**Review Focus:** all five items trace to a task and a named test, as listed above.

**Proportion:** the design's section 4 plus the relevant parts of section 0/Decisions is about 35 lines; this plan is longer because of per-step TDD granularity (consistent with the already-shipped Plan A plan), not because it transcribes algorithm bodies the signatures don't already determine.

---

Plan complete and saved to `plans/2026-11-04-grammar-tab-implementation-plan.md`. Please review the plan. Which execution approach would you prefer?

- **Subagent-driven** - A fresh subagent implements each task and a fresh reviewer checks it before the next one starts, then a whole-branch review at the end. Most thorough; costs a fresh context per task and per review.
- **Native** - I implement every task myself in this session, the way this harness runs work, then one fresh reviewer on the most capable model checks the whole branch. Cheapest and fastest; no independent review until the end. Runs well with a mid-tier session model, since the plan carries the design.

For this plan I recommend **Native**, the same approach used for Plan A: the five tasks are small, mostly sequential (each one's Interfaces block is a short, concrete handoff to the next), and a shipped mistake here is cheap to catch — it would show up as a wrong on-screen status message or an unsaved file, not silent data loss. Does the plan capture what you want, and which approach should we use?
