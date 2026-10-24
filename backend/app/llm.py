"""LLM se jawab banwana, word-by-word (streaming).

Providers (LLM_PROVIDER):
  groq              -> Groq (default), OpenAI-compatible API
  anthropic         -> Claude
  openai_compatible -> koi bhi OpenAI-compatible server (Gemini, Ollama, OpenRouter, Cerebras...)
                       LLM_BASE_URL + LLM_MODEL (+ LLM_API_KEY) dena padta hai
"""
import logging
from collections.abc import AsyncIterator

from app.config import settings

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODELS = {
    "groq": "openai/gpt-oss-20b",
    "anthropic": "claude-sonnet-5-5",
}

SYSTEM_PROMPT = (
    "You are DocChat, an assistant that answers questions using ONLY the document "
    "excerpts provided in the user's message under 'Context'. "
    "If the answer is not in the context, say clearly that you could not find it in the "
    "uploaded documents; never make things up. "
    "LANGUAGE: reply in the language the user's QUESTION is written in "
    "(Hinglish question -> Hinglish answer). "
    "FORMAT: the chat window renders Markdown, so write well-structured, easy-to-scan answers. "
    "Never write one big paragraph. Use short headings (## or ###) when the answer has more than "
    "one part, bullet lists ('- ') for lists, numbered lists ('1.') for steps, **bold** for key "
    "terms, and a blank line between sections. Use a Markdown table only when comparing several "
    "items on the same attributes. Never use HTML tags such as <br>. "
    "For a summary use this layout: one line saying what the document is about, then "
    "'## Key points' with 4 to 7 bullets, then (only if relevant) '## Steps' or "
    "'## Important notes'. Keep answers clear and concise."
)


class LLMError(Exception):
    """LLM call fail hui. `user_message` seedha user ko dikhane layak hota hai."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


# ------------------------------------------------------------------ config
def model_name() -> str:
    return settings.llm_model or DEFAULT_MODELS.get(settings.llm_provider, "")


def config_error() -> str | None:
    """Kuch set karna baaki ho to batao kya; sab theek ho to None."""
    provider = settings.llm_provider
    if provider == "groq" and not settings.groq_api_key:
        return "Server par GROQ_API_KEY set nahi hai (.env file mein daalo)"
    if provider == "anthropic" and not settings.anthropic_api_key:
        return "Server par ANTHROPIC_API_KEY set nahi hai (.env file mein daalo)"
    if provider == "openai_compatible":
        if not settings.llm_base_url:
            return "LLM_BASE_URL set nahi hai (openai_compatible provider ke liye zaroori)"
        if not settings.llm_model:
            return "LLM_MODEL set nahi hai (openai_compatible provider ke liye zaroori)"
    return None


def is_configured() -> bool:
    return config_error() is None


# ------------------------------------------------------------------ clients (pehli baar use par banta hai)
_openai_client = None
_anthropic_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI

        if settings.llm_provider == "groq":
            base_url, api_key = GROQ_BASE_URL, settings.groq_api_key
        else:
            base_url = settings.llm_base_url
            api_key = settings.llm_api_key or "not-needed"  # Ollama jaisi local servers key ignore karti hain
        _openai_client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=60, max_retries=1)
    return _openai_client





# ------------------------------------------------------------------ prompt
def build_messages(question: str, chunks: list[dict], history: list[dict]) -> list[dict]:
    """Pichli baatcheet + naye question ke saath document ka context."""
    context = "\n\n".join(
        f"[{i}] ({c['filename']})\n{c['text']}" for i, c in enumerate(chunks, start=1)
    )
    final_user_message = f"Context:\n{context}\n\nQuestion: {question}"
    return [*history, {"role": "user", "content": final_user_message}]


# ------------------------------------------------------------------ streaming
async def _stream_openai_compatible(messages: list[dict]) -> AsyncIterator[str]:
    model = model_name()
    kwargs = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        "max_tokens": settings.llm_max_tokens,
        "stream": True,
    }
    # gpt-oss "reasoning" models soch-soch mein bahut tokens kharch karte hain; free quota bachane ke liye kam
    if settings.llm_provider == "groq" and model.startswith("openai/gpt-oss"):
        kwargs["extra_body"] = {"reasoning_effort": "low"}

    stream = await _get_openai_client().chat.completions.create(**kwargs)
    async for chunk in stream:
        if not chunk.choices:
            continue
        text = chunk.choices[0].delta.content
        if text:
            yield text





def _friendly_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)  # openai aur anthropic dono ke errors mein hota hai
    if status == 429:
        return "AI provider ki free limit abhi lag gayi hai, thodi der baad try karo"
    if status in (401, 403):
        return "AI provider ne API key accept nahi ki, .env mein key check karo"
    if status == 404:
        return "Model ka naam galat hai ya provider par available nahi hai (LLM_MODEL check karo)"
    if status is None and "connect" in type(exc).__name__.lower():
        return "AI provider tak pahunch nahi paye, internet ya LLM_BASE_URL check karo"
    return "AI se jawab nahi aa paya, thodi der baad try karo"






async def stream_answer(
    question: str, chunks: list[dict], history: list[dict]
) -> AsyncIterator[str]:
    messages = build_messages(question, chunks, history)
    try:
        async for token in _stream_openai_compatible(messages):
            yield token
    except Exception as exc:
        logger.exception("LLM call fail hui (provider=%s)", settings.llm_provider)
        raise LLMError(_friendly_error(exc)) from exc