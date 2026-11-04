from pathlib import Path

import anthropic
from dotenv import load_dotenv

from whisper_gui.transcription import _backup_if_exists

MODEL = "claude-sonnet-5-5"
MAX_PROMPT_CHARS = 100_000


def build_prompt(original_text: str, english_text: str) -> str:
    return (
        "You are a language-learning tutor. Below is a transcript of a voice "
        "note in its original language, together with an English translation "
        "provided only as a meaning reference. Identify the source language "
        "yourself from the original text; do not assume it has already been "
        "detected.\n\n"
        f"Original text:\n{original_text}\n\n"
        f"English reference translation:\n{english_text}\n\n"
        "Write a grammar analysis in English with these sections:\n"
        "1. A per-sentence breakdown noting tense/mood and key grammatical "
        "constructions.\n"
        "2. Agreement (gender, number, etc.) and other notable grammar points.\n"
        "3. A short vocabulary list with dictionary (lemma) forms.\n"
        "4. Idioms and colloquial expressions used, each with its literal "
        "meaning versus its actual/intended meaning.\n"
    )


def validate_length(original_text: str, english_text: str) -> None:
    combined_len = len(original_text) + len(english_text)
    if combined_len > MAX_PROMPT_CHARS:
        raise ValueError(
            f"Transcript too long to analyze ({combined_len} characters, "
            f"max {MAX_PROMPT_CHARS})."
        )


def analyze(client, original_text: str, english_text: str) -> str:
    validate_length(original_text, english_text)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": build_prompt(original_text, english_text)}],
    )
    return response.content[0].text


_client = None


def get_client():
    global _client
    if _client is None:
        load_dotenv()
        client = anthropic.Anthropic()
        if client.api_key is None and client.auth_token is None and client.credentials is None:
            raise RuntimeError(
                "No Anthropic API credentials found. Set ANTHROPIC_API_KEY in "
                "the environment or in the project's .env file."
            )
        _client = client
    return _client


def output_path(source: Path) -> Path:
    return source.with_name(source.stem + ".grammar.md")


def save_analysis(source: Path, content: str) -> Path:
    path = output_path(source)
    _backup_if_exists(path)
    path.write_text(content, encoding="utf-8")
    return path


def load_existing_analysis(source: Path) -> str | None:
    path = output_path(source)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
