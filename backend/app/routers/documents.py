"""Document upload, list, delete.

Upload turant jawab deta hai (status="processing"), aur chunking + embedding
BackgroundTasks mein peeche chalti hai. Frontend status poll karta rehta hai.
"""
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import rag, textproc
from app.config import settings
from app.database import SessionLocal, get_db
from app.deps import get_current_user
from app.models import Document, User
from app.schemas import DocumentOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".txt"}


def process_document(document_id: int, user_id: int, filename: str, content: bytes) -> None:
    """Background task: text nikalo -> chunk karo -> ChromaDB mein store karo."""
    db = SessionLocal()  # request wala session yahan kaam nahi karega, apna session
    try:
        doc = db.get(Document, document_id)
        if doc is None:  # beech mein user ne delete kar diya
            return
        try:
            text = textproc.extract_text(filename, content)
            if not text.strip():
                raise ValueError("Document mein text nahi mila (scanned PDF ho sakti hai)")
            chunks = textproc.chunk_text(text, settings.chunk_size, settings.chunk_overlap)
            rag.add_chunks(user_id, document_id, filename, chunks)
            doc.status, doc.chunk_count, doc.error = "ready", len(chunks), None
        except Exception as exc:
            logger.exception("Document %s process nahi hua", document_id)
            doc.status = "failed"
            doc.error = str(exc)[:500] if isinstance(exc, ValueError) else "File padhi nahi ja saki"
        db.commit()
    finally:
        db.close()


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def upload_document(  # sync def: FastAPI ise threadpool mein chalata hai, to blocking kaam server nahi rokta
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filename = os.path.basename(file.filename or "")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Sirf PDF ya TXT file chalegi")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    content = file.file.read(max_bytes + 1)  # limit se 1 byte zyada padho, taaki badi file pakdi jaye
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File {settings.max_upload_mb} MB se badi hai")
    if not content:
        raise HTTPException(status_code=400, detail="File khali hai")
    if ext == ".pdf" and not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Ye asli PDF file nahi lagti")

    doc = Document(user_id=user.id, filename=filename[:255], status="processing")
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(process_document, doc.id, user.id, doc.filename, content)
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Document).where(Document.user_id == user.id).order_by(Document.id.desc())
    return db.scalars(stmt).all()


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document nahi mila")
    rag.delete_document_chunks(doc.id)
    db.delete(doc)
    db.commit()
