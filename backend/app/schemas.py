"""Pydantic schemas: API ka input/output format (database table se alag cheez)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):  # password yahan nahi hai, isliye response mein kabhi nahi jayega
    id: int
    username: str
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DocumentOut(BaseModel):
    id: int
    filename: str
    status: str
    chunk_count: int
    error: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_id: int | None = None  # None = saare documents mein dhundo


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: list = []
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
