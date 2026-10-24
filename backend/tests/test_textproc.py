"""Chunking aur text extraction ke tests (ye bina database/ChromaDB ke chalte hain)."""
from app.textproc import chunk_text, extract_text
from tests.helpers import make_pdf


def test_empty_text_gives_no_chunks():
    assert chunk_text("", 800, 100) == []
    assert chunk_text("   \n\n  ", 800, 100) == []


def test_short_text_is_one_chunk():
    assert chunk_text("hello   world\nagain", 800, 100) == ["hello world again"]


def test_chunks_respect_size_and_cover_all_words():
    words = [f"word{i}" for i in range(1000)]
    chunks = chunk_text(" ".join(words), size=200, overlap=40)

    assert len(chunks) > 5
    assert all(len(c) <= 200 for c in chunks)

    seen = set()
    for c in chunks:
        seen.update(c.split())
    assert seen == set(words)  # koi word chhuta nahi, aur koi word beech se kata nahi


def test_consecutive_chunks_overlap():
    words = [f"w{i}" for i in range(500)]
    chunks = chunk_text(" ".join(words), size=200, overlap=50)
    for a, b in zip(chunks, chunks[1:]):
        assert set(a.split()) & set(b.split()), "agle chunk mein pichle ka kuch hissa hona chahiye"


def test_text_without_spaces_still_terminates():
    chunks = chunk_text("a" * 5000, size=800, overlap=100)
    assert chunks and all(len(c) <= 800 for c in chunks)
    assert sum(len(c) for c in chunks) >= 5000


def test_overlap_larger_than_size_still_terminates():
    chunks = chunk_text("abc " * 200, size=50, overlap=500)
    assert chunks


def test_extract_text_from_txt_with_hindi():
    assert extract_text("notes.txt", "नमस्ते Dileep".encode("utf-8")) == "नमस्ते Dileep"


def test_extract_text_ignores_bad_bytes():
    assert "ok" in extract_text("notes.txt", b"ok \xff\xfe")


def test_extract_text_from_pdf():
    pdf = make_pdf("Retrieval augmented generation basics")
    assert "Retrieval augmented generation" in extract_text("a.pdf", pdf)
