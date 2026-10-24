"""RAG chat: question -> milte chunks (ChromaDB) -> LLM -> word-by-word jawab.

Stream ka format NDJSON hai (har line ek JSON):
  {"type": "sources", "sources": [...]}
  {"type": "token", "text": "..."}      (kai baar)
  {"type": "done"}   ya   {"type": "error", "message": "..."}
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import llm, rag
from app.config import settings
from app.database import SessionLocal, get_db
from app.deps import get_current_user
from app.limiter import limiter
from app.models import ChatMessage, Document, User
from app.schemas import ChatRequest, MessageOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


def _line(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _prepare(db: Session, user: User, req: ChatRequest):
    """Blocking kaam (DB + ChromaDB) ek jagah, taaki async endpoint threadpool mein chala sake."""
    if req.document_id is not None:
        doc = db.scalar(
            select(Document).where(Document.id == req.document_id, Document.user_id == user.id)
        )
        if doc is None:
            raise HTTPException(status_code=404, detail="Document nahi mila")
        if doc.status != "ready":
            raise HTTPException(status_code=409, detail="Ye document abhi process ho raha hai ya fail hua")

    ready = db.scalar(
        select(func.count()).select_from(Document).where(
            Document.user_id == user.id, Document.status == "ready"
        )
    )
    if not ready:
        raise HTTPException(status_code=400, detail="Pehle koi document upload karo (aur ready hone do)")

    chunks = rag.search(user.id, req.question, settings.top_k, req.document_id)

    rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.id.desc())
        .limit(settings.history_messages)
    ).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(rows)]
    while history and history[0]["role"] != "user":  # LLM ko pehla message user ka chahiye
        history.pop(0)
    return chunks, history


def _save_exchange(user_id: int, question: str, answer: str, sources: list[dict]) -> None:
    db = SessionLocal()  # stream ke baad request wala session band ho chuka hota hai
    try:
        db.add(ChatMessage(user_id=user_id, role="user", content=question, sources=[]))
        db.add(ChatMessage(user_id=user_id, role="assistant", content=answer, sources=sources))
        db.commit()
    finally:
        db.close()


@router.post("/stream")
@limiter.limit(settings.rate_limit_chat)
async def chat_stream(
    request: Request,
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    problem = llm.config_error()
    if problem:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=problem)

    chunks, history = await run_in_threadpool(_prepare, db, user, req)

    # ek document ka naam ek hi baar dikhao
    unique = {c["document_id"]: c["filename"] for c in chunks}
    sources = [{"document_id": i, "filename": name} for i, name in unique.items()]
    user_id, question = user.id, req.question

    async def event_stream():
        yield _line({"type": "sources", "sources": sources})
        parts: list[str] = []
        try:
            async for token in llm.stream_answer(question, chunks, history):
                parts.append(token)
                yield _line({"type": "token", "text": token})
        except llm.LLMError as exc:  # llm.py ne already log kiya aur friendly message banaya
            yield _line({"type": "error", "message": exc.user_message})
            return
        except Exception:
            logger.exception("Chat stream fail hui")
            yield _line({"type": "error", "message": "AI se jawab nahi aa paya, thodi der baad try karo"})
            return
        answer = "".join(parts).strip()
        if answer:
            await run_in_threadpool(_save_exchange, user_id, question, answer, sources)
        yield _line({"type": "done"})

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history", response_model=list[MessageOut])
def get_history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.id.desc())
        .limit(100)
    ).all()
    return list(reversed(rows))


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    for msg in db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id)).all():
        db.delete(msg)
    db.commit()
