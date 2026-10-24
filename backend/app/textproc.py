"""Text processing: file se text nikalna aur chunk karna.

Ye pure functions hain (database ya ChromaDB nahi chahiye), isliye test karna aasaan hai.
"""
import io

from pypdf import PdfReader


def extract_text(filename: str, content: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return content.decode("utf-8", errors="ignore")


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Text ko lagbhag `size` characters ke tukdon mein todta hai.

    Agle chunk mein pichle ke lagbhag `overlap` characters repeat hote hain, taaki baat beech se na kate.
    Chunk word ke beech se shuru/khatam nahi hota (jab tak text mein spaces hain).
    """
    text = " ".join(text.split())  # extra spaces/newlines hatao
    chunks: list[str] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            cut = text.rfind(" ", start + size // 2, end)
            if cut != -1:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break

        new_start = max(end - overlap, start + 1)  # hamesha aage badhta hai
        if text[new_start - 1] != " ":  # word ke beech mein ho to agle word se shuru karo
            space = text.find(" ", new_start, end)
            if space != -1:
                new_start = space + 1
        start = new_start
    return chunks
