"""MVP: регистрация, проверка пароля, нормализация email (без JWT/OAuth)."""

from __future__ import annotations

import hashlib
import secrets
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Client, User

_PBKDF2_ITERS = 260_000
_SCHEME = "pbkdf2_sha256"


def normalize_email(value: str) -> str:
    return value.strip().lower()


def hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        plain.encode("utf-8"),
        salt.encode("ascii"),
        _PBKDF2_ITERS,
    )
    return f"{_scheme_prefix()}{salt}${dk.hex()}"


def _scheme_prefix() -> str:
    return f"{_SCHEME}$"


def verify_password(plain: str, stored: str) -> bool:
    if not stored or not plain:
        return False
    if not stored.startswith(_scheme_prefix()):
        return False
    rest = stored[len(_scheme_prefix()) :]
    parts = rest.split("$", 1)
    if len(parts) != 2:
        return False
    salt_hex, hash_hex = parts
    try:
        salt = salt_hex.encode("ascii")
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        plain.encode("utf-8"),
        salt,
        _PBKDF2_ITERS,
    )
    return secrets.compare_digest(dk, expected)


def get_user_by_email(session: Session, email: str) -> User | None:
    key = normalize_email(email)
    if not key:
        return None
    return session.scalars(select(User).where(User.email == key).limit(1)).first()


def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def create_user(
    session: Session, *, name: str, email: str, password: str, city: str
) -> User:
    u = User(
        name=name.strip(),
        email=normalize_email(email),
        password_hash=hash_password(password),
        city=city.strip() or None,
    )
    session.add(u)
    session.flush()
    return u


def get_or_create_client_for_user(session: Session, user: User) -> Client:
    if user.email:
        existing = session.scalars(
            select(Client).where(Client.contact_email == user.email).limit(1)
        ).first()
        if existing is not None:
            return existing
    c = Client(name=user.name, contact_email=user.email or None)
    session.add(c)
    session.flush()
    return c
