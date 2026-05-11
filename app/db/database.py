"""SQLite + SQLAlchemy: движок и фабрика сессий для MVP."""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Корень проекта: app/db -> на два уровня вверх
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "wrapvision.db"

DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

# Для SessionMiddleware (cookie-сессии). В проде задайте WRAPVISION_SESSION_SECRET.
SESSION_SECRET_KEY = os.environ.get(
    "WRAPVISION_SESSION_SECRET",
    "wrapvision-dev-session-secret-change-in-production",
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
