from types import SimpleNamespace

import pytest

import whisper_gui.grammar_analysis as grammar_analysis
from whisper_gui.grammar_analysis import (
    MODEL,
    MAX_OUTPUT_TOKENS,
    MAX_PROMPT_CHARS,
    analyze,
    build_prompt,
    load_existing_analysis,
    output_path,
    save_analysis,
    validate_length,
)


class _FakeMessages:
    def create(self, **kwargs):
        self.received_kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(text="# Grammar analysis\n...")],
            stop_reason="end_turn",
        )


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


class _StopReasonMessages:
    def __init__(self, stop_reason, content=None):
        self._stop_reason = stop_reason
        self._content = content if content is not None else [SimpleNamespace(text="# Analysis")]

    def create(self, **kwargs):
        return SimpleNamespace(content=self._content, stop_reason=self._stop_reason)


class _StopReasonClient:
    def __init__(self, stop_reason, content=None):
        self.messages = _StopReasonMessages(stop_reason, content)


def test_build_prompt_includes_both_texts():
    prompt = build_prompt("hola mundo", "hello world")
    assert "hola mundo" in prompt
    assert "hello world" in prompt


def test_build_prompt_requests_required_sections():
    prompt = build_prompt("x", "y").lower()
    for keyword in ("tense", "agreement", "vocabulary", "idiom"):
        assert keyword in prompt


def test_validate_length_allows_text_under_the_limit():
    validate_length("short original", "short english")  # does not raise


def test_validate_length_raises_when_combined_text_exceeds_max_chars():
    long_text = "x" * (MAX_PROMPT_CHARS + 1)
    with pytest.raises(ValueError):
        validate_length(long_text, "")


def test_analyze_returns_the_text_of_the_first_content_block():
    result = analyze(_FakeClient(), "hola", "hello")
    assert result == "# Grammar analysis\n..."


def test_analyze_sends_the_configured_model_and_the_built_prompt():
    client = _FakeClient()
    analyze(client, "hola", "hello")
    assert client.messages.received_kwargs["model"] == MODEL
    assert "hola" in client.messages.received_kwargs["messages"][0]["content"]


def test_analyze_requests_enough_output_tokens_for_a_full_analysis():
    client = _FakeClient()
    analyze(client, "hola", "hello")
    assert client.messages.received_kwargs["max_tokens"] == MAX_OUTPUT_TOKENS
    assert MAX_OUTPUT_TOKENS >= 16000


def test_analyze_raises_without_calling_the_client_when_text_is_too_long():
    client = _FakeClient()
    long_text = "x" * (MAX_PROMPT_CHARS + 1)
    with pytest.raises(ValueError):
        analyze(client, long_text, "")
    assert not hasattr(client.messages, "received_kwargs")


def test_analyze_raises_when_response_is_cut_off_at_max_tokens():
    client = _StopReasonClient("max_tokens")
    with pytest.raises(RuntimeError):
        analyze(client, "hola", "hello")


def test_analyze_raises_when_claude_refuses():
    client = _StopReasonClient("refusal")
    with pytest.raises(RuntimeError):
        analyze(client, "hola", "hello")


def test_analyze_raises_when_response_has_no_content_blocks():
    client = _StopReasonClient("end_turn", content=[])
    with pytest.raises(RuntimeError):
        analyze(client, "hola", "hello")


def test_get_client_raises_when_no_api_key_is_configured(monkeypatch):
    monkeypatch.setattr(grammar_analysis, "load_dotenv", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    grammar_analysis._client = None
    with pytest.raises(Exception):
        grammar_analysis.get_client()


def test_get_client_returns_the_same_instance_on_a_second_call(monkeypatch):
    monkeypatch.setattr(grammar_analysis, "load_dotenv", lambda: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    grammar_analysis._client = None
    first = grammar_analysis.get_client()
    second = grammar_analysis.get_client()
    assert first is second


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
