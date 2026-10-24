"""Database connection (SQLAlchemy).

Local par SQLite, Docker/production mein PostgreSQL. Sirf DATABASE_URL badalta hai.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Har request ko ek DB session milta hai, kaam ke baad band ho jata hai."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
