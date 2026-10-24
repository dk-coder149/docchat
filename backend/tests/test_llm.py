"""llm.py ke tests: prompt, provider config, streaming aur error messages (asli API call kabhi nahi)."""
import asyncio
from types import SimpleNamespace

import pytest

from app import llm
from app.config import settings

CHUNKS = [{"filename": "notes.pdf", "text": "RAG searches documents first."}]


# ------------------------------------------------------------------ nakli OpenAI-style client
def _chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


class _FakeStream:
    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self.items:
            yield item


def _fake_client(items=None, error=None, calls=None):
    async def create(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        if error:
            raise error
        return _FakeStream(items)

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _collect(question="What is RAG?", history=None):
    async def run():
        return [t async for t in llm.stream_answer(question, CHUNKS, history or [])]

    return asyncio.run(run())


@pytest.fixture
def groq(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "")


# ------------------------------------------------------------------ prompt
def test_build_messages_puts_history_first_and_context_in_last_message():
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    msgs = llm.build_messages("What is RAG?", CHUNKS, history)
    assert msgs[:2] == history
    assert msgs[-1]["role"] == "user"
    assert "RAG searches documents first." in msgs[-1]["content"]
    assert "notes.pdf" in msgs[-1]["content"]
    assert msgs[-1]["content"].endswith("Question: What is RAG?")


# ------------------------------------------------------------------ config
def test_default_models(monkeypatch, groq):
    assert llm.model_name() == "openai/gpt-oss-20b"
    monkeypatch.setattr(settings, "llm_model", "llama-3.1-8b-instant")
    assert llm.model_name() == "llama-3.1-8b-instant"  # LLM_MODEL se badal sakte hain


def test_config_error_names_the_missing_setting(monkeypatch, groq):
    assert llm.config_error() is None
    assert llm.is_configured()

    monkeypatch.setattr(settings, "groq_api_key", "")
    assert "GROQ_API_KEY" in llm.config_error()

    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert "ANTHROPIC_API_KEY" in llm.config_error()

    monkeypatch.setattr(settings, "llm_provider", "openai_compatible")
    monkeypatch.setattr(settings, "llm_base_url", "")
    assert "LLM_BASE_URL" in llm.config_error()
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434/v1")
    assert "LLM_MODEL" in llm.config_error()
    monkeypatch.setattr(settings, "llm_model", "llama3.2")
    assert llm.config_error() is None  # Ollama ko API key nahi chahiye


# ------------------------------------------------------------------ streaming
def test_streams_text_and_skips_empty_chunks(monkeypatch, groq):
    calls = []
    items = [
        SimpleNamespace(choices=[]),  # kuch providers aakhir mein khali choices bhejte hain
        _chunk("Hello "),
        _chunk(None),  # reasoning/role chunks mein content None hota hai
        _chunk(""),
        _chunk("world"),
    ]
    monkeypatch.setattr(llm, "_get_openai_client", lambda: _fake_client(items, calls=calls))

    assert _collect() == ["Hello ", "world"]

    sent = calls[0]
    assert sent["stream"] is True
    assert sent["model"] == "openai/gpt-oss-20b"
    assert sent["messages"][0]["role"] == "system"
    assert sent["messages"][-1]["role"] == "user"
    assert sent["max_tokens"] == settings.llm_max_tokens
    assert sent["extra_body"] == {"reasoning_effort": "low"}  # gpt-oss par reasoning kam


def test_non_gpt_oss_model_gets_no_reasoning_parameter(monkeypatch, groq):
    monkeypatch.setattr(settings, "llm_model", "llama-3.1-8b-instant")
    calls = []
    monkeypatch.setattr(llm, "_get_openai_client", lambda: _fake_client([_chunk("ok")], calls=calls))
    _collect()
    assert "extra_body" not in calls[0]


def test_openai_compatible_provider_gets_no_reasoning_parameter(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai_compatible")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "llm_model", "openai/gpt-oss-20b")
    calls = []
    monkeypatch.setattr(llm, "_get_openai_client", lambda: _fake_client([_chunk("ok")], calls=calls))
    _collect()
    assert "extra_body" not in calls[0]  # ye parameter sirf Groq ke liye hai


# ------------------------------------------------------------------ errors
class _HttpError(Exception):
    def __init__(self, status_code):
        super().__init__(f"http {status_code}")
        self.status_code = status_code


@pytest.mark.parametrize(
    "status, expected_word",
    [(429, "limit"), (401, "key"), (403, "key"), (404, "Model")],
)
def test_provider_errors_become_friendly_messages(monkeypatch, groq, status, expected_word):
    monkeypatch.setattr(llm, "_get_openai_client", lambda: _fake_client(error=_HttpError(status)))
    with pytest.raises(llm.LLMError) as info:
        _collect()
    assert expected_word in info.value.user_message


def test_unknown_error_gets_generic_message(monkeypatch, groq):
    monkeypatch.setattr(llm, "_get_openai_client", lambda: _fake_client(error=RuntimeError("boom")))
    with pytest.raises(llm.LLMError) as info:
        _collect()
    assert "boom" not in info.value.user_message  # andar ki detail user ko nahi dikhti
