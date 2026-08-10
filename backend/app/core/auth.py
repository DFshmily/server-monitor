"""Authentication core: password hashing, JWT tokens, user/invite helpers."""
import os
import secrets
import time
import uuid

import bcrypt
import jwt

from app.core.config import JWT_SECRET, JWT_EXPIRE_SECONDS

ALGO = "HS256"


# ── Password hashing ──────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


# ── JWT ───────────────────────────────────────────────────────────
def create_token(email: str, role: str, remember: bool = False) -> str:
    now = int(time.time())
    ttl = 7 * 86400 if remember else JWT_EXPIRE_SECONDS
    payload = {
        "sub": email,
        "role": role,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGO)


def decode_token(token: str) -> dict | None:
    """Return payload dict, or None if invalid/expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGO])
    except (jwt.PyJWTError, Exception):
        return None


# ── Invite codes ──────────────────────────────────────────────────
def generate_invite_code(n: int = 10) -> list[str]:
    """Generate n unique invite codes (10 chars, uppercase alnum)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I/O/0/1 confusion
    codes = set()
    while len(codes) < n:
        codes.add("".join(secrets.choice(alphabet) for _ in range(10)))
    return sorted(codes)


def make_invite_expiry(days: int = 7) -> int:
    return int(time.time()) + days * 86400
