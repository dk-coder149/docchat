"""Signup, login, current user."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.limiter import limiter
from app.models import User
from app.schemas import TokenOut, UserCreate, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_auth)
def signup(request: Request, data: UserCreate, db: Session = Depends(get_db)):
    username = data.username.lower()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=400, detail="Ye username pehle se le liya gaya hai")
    user = User(username=username, hashed_password=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # do log ek saath same username banayein to
        db.rollback()
        raise HTTPException(status_code=400, detail="Ye username pehle se le liya gaya hai")
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
@limiter.limit(settings.rate_limit_auth)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),  # form data: username + password
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.username == form.username.lower()))
    ok = verify_password(form.password, user.hashed_password if user else None)
    if not user or not ok:
        raise HTTPException(status_code=401, detail="Username ya password galat hai")
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
