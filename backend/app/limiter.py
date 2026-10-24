"""Rate limiter (ek IP se bahut zyada request roke, LLM bill bachane ke liye)."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
