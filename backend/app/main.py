"""FastAPI app: sab kuch yahan judta hai."""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (tables register hone ke liye zaroori)
from app.config import settings
from app.database import Base, engine, get_db
from app.limiter import limiter
from app.routers import auth, chat, documents

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("docchat")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # tables nahi hain to bana do
    logger.info("DocChat start ho gaya")
    yield
    logger.info("DocChat band ho raha hai")


app = FastAPI(title="DocChat API", version="1.0.0", lifespan=lifespan)

# ---- rate limit ----
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---- CORS: sirf apna frontend allowed ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- middleware: har request ka time naapo ----
@app.middleware("http")
async def add_process_time(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
    return response


# ---- routers ----
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)):
    """Cloud platform / Docker isse check karta hai ki app aur database zinda hain."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
