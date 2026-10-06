"""Conexão com o banco. Postgres no Railway (DATABASE_URL); SQLite local sem ela."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///./agenda.db")
    # Railway entrega postgres:// ou postgresql://; o driver é o psycopg 3.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def criar_engine(url: str | None = None):
    url = url or _url()
    extra = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=extra, pool_pre_ping=True)


engine = criar_engine()
SessaoLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
