"""Test setup.

Tests kabhi asli database, asli ChromaDB folder ya asli Anthropic key ko nahi chhoote:
  - SQLite temp file
  - temp ChromaDB folder + nakli (hash-based) embeddings, koi model download nahi
  - nakli LLM (fake_llm fixture), koi paisa kharch nahi
"""
import hashlib
import itertools
import math
import os
import re
import tempfile
import uuid

import pytest

# IMPORTANT: ye env vars `app` import hone se PEHLE set hone chahiye (settings import par bante hain).
_TMP = tempfile.mkdtemp(prefix="docchat-test-")
os.environ.update(
    {
        "SECRET_KEY": "test-secret-key-not-for-production",
        "DATABASE_URL": f"sqlite:///{_TMP}/test.db",
        "CHROMA_PATH": f"{_TMP}/chroma",
        "LLM_PROVIDER": "groq",
        "GROQ_API_KEY": "test-key",
        "ANTHROPIC_API_KEY": "",
        "LLM_MODEL": "",
        "LLM_BASE_URL": "",
        "LLM_API_KEY": "",
        "RATE_LIMIT_CHAT": "1000/minute",
        "RATE_LIMIT_AUTH": "1000/minute",
        "CORS_ORIGINS": "http://localhost:3000",
    }
)


class HashEmbedding:
    """Nakli embedding: words ko hash karke 64-dim vector. Milte-julte words wale text paas aate hain."""

    DIM = 64

    def __call__(self, input):  # ChromaDB isi naam (input) se call karta hai
        return [self._embed(text) for text in input]

    # Naye ChromaDB search (query) ke waqt embed_query, aur document add karte waqt embed_documents bulate hain.
    def embed_query(self, input):
        return self(input)

    def embed_documents(self, input):
        return self(input)

    def _embed(self, text):
        vec = [0.0] * self.DIM
        for word in re.findall(r"\w+", text.lower()):
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    # Naye ChromaDB versions ye extra methods dekhte hain; purane unhe ignore karte hain.
    @staticmethod
    def name():
        return "docchat-hash-test"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config):
        return HashEmbedding()

    def default_space(self):
        return "cosine"

    def supported_spaces(self):
        return ["cosine", "l2", "ip"]


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app import rag

    rag.configure(HashEmbedding())
    from app.main import app

    with TestClient(app) as test_client:  # "with" se lifespan chalta hai (tables ban jate hain)
        yield test_client


@pytest.fixture
def make_user(client):
    """Naya user banata hai aur uske Authorization headers deta hai."""
    counter = itertools.count(1)

    def _make(prefix="user"):
        name = f"{prefix}{next(counter)}_{uuid.uuid4().hex[:6]}"
        password = "correct-horse-battery"
        r = client.post("/api/auth/signup", json={"username": name, "password": password})
        assert r.status_code == 201, r.text
        r = client.post("/api/auth/login", data={"username": name, "password": password})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        return {
            "username": name,
            "password": password,
            "headers": {"Authorization": f"Bearer {token}"},
        }

    return _make


@pytest.fixture
def fake_llm(monkeypatch):
    """LLM ki jagah nakli jawab. Return: calls ki list (kya-kya LLM ko bheja gaya)."""
    from app import llm

    calls = []

    async def fake_stream(question, chunks, history):
        calls.append({"question": question, "chunks": chunks, "history": history})
        for token in ["Hello ", "from ", "fake LLM"]:
            yield token

    monkeypatch.setattr(llm, "stream_answer", fake_stream)
    return calls
