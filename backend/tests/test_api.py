"""API ke tests: auth, documents, chat, aur users ke beech isolation."""
from app import rag
from app.config import settings
from tests.helpers import make_pdf, parse_stream, upload

RAG_TEXT = (
    "Retrieval augmented generation, or RAG, first searches your documents for relevant "
    "passages and then gives those passages to a language model so it can answer."
)


# --------------------------------------------------------------------- system
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert "x-process-time-ms" in r.headers  # middleware chal raha hai


def test_cors_allows_configured_origin(client):
    r = client.options(
        "/api/auth/login",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


# --------------------------------------------------------------------- auth
def test_signup_login_me(client, make_user):
    user = make_user()
    r = client.get("/api/auth/me", headers=user["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == user["username"].lower()
    assert "password" not in body and "hashed_password" not in body


def test_signup_duplicate_username_is_rejected_case_insensitively(client, make_user):
    user = make_user()
    r = client.post(
        "/api/auth/signup",
        json={"username": user["username"].upper(), "password": "another-password"},
    )
    assert r.status_code == 400


def test_signup_validation(client):
    assert client.post("/api/auth/signup", json={"username": "ab", "password": "long-enough-pw"}).status_code == 422
    assert client.post("/api/auth/signup", json={"username": "valid_name", "password": "short"}).status_code == 422
    assert client.post("/api/auth/signup", json={"username": "bad name!", "password": "long-enough-pw"}).status_code == 422


def test_login_wrong_password_and_unknown_user(client, make_user):
    user = make_user()
    r = client.post("/api/auth/login", data={"username": user["username"], "password": "wrong-password"})
    assert r.status_code == 401
    r = client.post("/api/auth/login", data={"username": "nobody_here", "password": "whatever-pw"})
    assert r.status_code == 401


def test_protected_routes_need_a_valid_token(client):
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/documents", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/chat/history").status_code == 401


# --------------------------------------------------------------------- documents
def test_upload_txt_becomes_ready(client, make_user):
    user = make_user()
    r = upload(client, user["headers"], "rag.txt", RAG_TEXT.encode())
    assert r.status_code == 202
    assert r.json()["filename"] == "rag.txt"

    # TestClient background task response se pehle poora kar deta hai
    docs = client.get("/api/documents", headers=user["headers"]).json()
    assert len(docs) == 1
    assert docs[0]["status"] == "ready"
    assert docs[0]["chunk_count"] >= 1


def test_upload_real_pdf(client, make_user):
    user = make_user()
    r = upload(client, user["headers"], "paper.pdf", make_pdf("Photosynthesis happens in chloroplasts"), "application/pdf")
    assert r.status_code == 202
    doc = client.get("/api/documents", headers=user["headers"]).json()[0]
    assert doc["status"] == "ready"


def test_upload_rejects_bad_files(client, make_user):
    h = make_user()["headers"]
    assert upload(client, h, "virus.exe", b"MZ...").status_code == 400
    assert upload(client, h, "empty.txt", b"").status_code == 400
    assert upload(client, h, "fake.pdf", b"this is not a pdf").status_code == 400


def test_upload_too_large(client, make_user, monkeypatch):
    h = make_user()["headers"]
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    assert upload(client, h, "big.txt", b"x").status_code == 413


def test_whitespace_only_document_is_marked_failed(client, make_user):
    user = make_user()
    upload(client, user["headers"], "blank.txt", b"   \n\n   ")
    doc = client.get("/api/documents", headers=user["headers"]).json()[0]
    assert doc["status"] == "failed"
    assert doc["error"]


def test_delete_document_removes_chunks(client, make_user):
    user = make_user()
    upload(client, user["headers"], "rag.txt", RAG_TEXT.encode())
    doc = client.get("/api/documents", headers=user["headers"]).json()[0]
    uid = client.get("/api/auth/me", headers=user["headers"]).json()["id"]
    assert rag.search(uid, "retrieval augmented generation", 3)  # delete se pehle milta hai

    assert client.delete(f"/api/documents/{doc['id']}", headers=user["headers"]).status_code == 204
    assert client.get("/api/documents", headers=user["headers"]).json() == []
    assert rag.search(uid, "retrieval augmented generation", 3) == []  # ChromaDB se bhi gaya
    assert client.delete(f"/api/documents/{doc['id']}", headers=user["headers"]).status_code == 404


# --------------------------------------------------------------------- chat
def test_chat_streams_answer_sources_and_saves_history(client, make_user, fake_llm):
    user = make_user()
    upload(client, user["headers"], "rag.txt", RAG_TEXT.encode())

    r = client.post("/api/chat/stream", headers=user["headers"], json={"question": "What is RAG?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")

    events = parse_stream(r)
    assert events[0]["type"] == "sources"
    assert events[0]["sources"][0]["filename"] == "rag.txt"
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Hello from fake LLM"
    assert events[-1] == {"type": "done"}

    # LLM ko document ka text mila
    assert "Retrieval augmented generation" in fake_llm[0]["chunks"][0]["text"]

    history = client.get("/api/chat/history", headers=user["headers"]).json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "What is RAG?"
    assert history[1]["content"] == "Hello from fake LLM"
    assert history[1]["sources"][0]["filename"] == "rag.txt"


def test_chat_remembers_previous_messages(client, make_user, fake_llm):
    user = make_user()
    upload(client, user["headers"], "rag.txt", RAG_TEXT.encode())
    client.post("/api/chat/stream", headers=user["headers"], json={"question": "first question"})
    client.post("/api/chat/stream", headers=user["headers"], json={"question": "second question"})

    history_sent = fake_llm[1]["history"]
    assert [m["role"] for m in history_sent] == ["user", "assistant"]
    assert history_sent[0]["content"] == "first question"


def test_chat_needs_a_ready_document(client, make_user, fake_llm):
    user = make_user()
    r = client.post("/api/chat/stream", headers=user["headers"], json={"question": "anything?"})
    assert r.status_code == 400
    assert fake_llm == []  # LLM bulaya hi nahi gaya


def test_chat_validation(client, make_user, fake_llm):
    h = make_user()["headers"]
    assert client.post("/api/chat/stream", headers=h, json={"question": ""}).status_code == 422
    assert client.post("/api/chat/stream", headers=h, json={"question": "x" * 2001}).status_code == 422


def test_chat_without_api_key_returns_503(client, make_user, monkeypatch):
    user = make_user()
    upload(client, user["headers"], "rag.txt", RAG_TEXT.encode())
    monkeypatch.setattr(settings, "groq_api_key", "")
    r = client.post("/api/chat/stream", headers=user["headers"], json={"question": "hi"})
    assert r.status_code == 503
    assert "GROQ_API_KEY" in r.json()["detail"]  # saaf bataya ki kaunsi key chahiye


def test_llm_error_message_reaches_the_user(client, make_user, monkeypatch):
    from app import llm

    async def rate_limited(question, chunks, history):
        raise llm.LLMError("AI provider ki free limit abhi lag gayi hai, thodi der baad try karo")
        yield  # async generator banane ke liye

    monkeypatch.setattr(llm, "stream_answer", rate_limited)
    user = make_user()
    upload(client, user["headers"], "rag.txt", RAG_TEXT.encode())
    events = parse_stream(
        client.post("/api/chat/stream", headers=user["headers"], json={"question": "hello?"})
    )
    assert events[-1]["type"] == "error"
    assert "limit" in events[-1]["message"]


def test_llm_failure_sends_error_event_and_saves_nothing(client, make_user, monkeypatch):
    from app import llm

    async def boom(question, chunks, history):
        raise RuntimeError("LLM down")
        yield  # isse ye async generator banta hai

    monkeypatch.setattr(llm, "stream_answer", boom)
    user = make_user()
    upload(client, user["headers"], "rag.txt", RAG_TEXT.encode())

    r = client.post("/api/chat/stream", headers=user["headers"], json={"question": "hello?"})
    events = parse_stream(r)
    assert events[-1]["type"] == "error"
    assert "done" not in [e["type"] for e in events]
    assert client.get("/api/chat/history", headers=user["headers"]).json() == []


def test_clear_history(client, make_user, fake_llm):
    user = make_user()
    upload(client, user["headers"], "rag.txt", RAG_TEXT.encode())
    client.post("/api/chat/stream", headers=user["headers"], json={"question": "hi"})
    assert client.delete("/api/chat/history", headers=user["headers"]).status_code == 204
    assert client.get("/api/chat/history", headers=user["headers"]).json() == []


# --------------------------------------------------------------------- isolation
def test_users_cannot_see_each_others_documents_or_answers(client, make_user, fake_llm):
    alice = make_user("alice")
    bob = make_user("bob")
    upload(client, alice["headers"], "alice_secret.txt", b"The alpha launch code is hidden in the vault.")
    upload(client, bob["headers"], "bob_notes.txt", b"Bob writes about gardening and tomatoes.")

    alice_doc = client.get("/api/documents", headers=alice["headers"]).json()[0]

    # Bob ki list mein sirf uska document
    bob_docs = client.get("/api/documents", headers=bob["headers"]).json()
    assert [d["filename"] for d in bob_docs] == ["bob_notes.txt"]

    # Bob Alice ka document delete nahi kar sakta, aur uske document_id se chat bhi nahi
    assert client.delete(f"/api/documents/{alice_doc['id']}", headers=bob["headers"]).status_code == 404
    r = client.post(
        "/api/chat/stream",
        headers=bob["headers"],
        json={"question": "alpha launch code vault", "document_id": alice_doc["id"]},
    )
    assert r.status_code == 404

    # Bob alpha launch code poochhe, tab bhi LLM ko sirf Bob ke chunks milte hain
    client.post("/api/chat/stream", headers=bob["headers"], json={"question": "alpha launch code vault"})
    sent = fake_llm[-1]["chunks"]
    assert sent and all(c["filename"] == "bob_notes.txt" for c in sent)

    # Chat history bhi alag
    assert client.get("/api/chat/history", headers=alice["headers"]).json() == []
