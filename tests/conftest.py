import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("ADMIN_SENHA", "senha-teste")

from app import db as banco  # noqa: E402
from app.main import criar_app, iniciar_banco  # noqa: E402


@pytest.fixture()
def fabrica(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    fab = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(banco, "SessaoLocal", fab)
    iniciar_banco(eng, fab)
    return fab


@pytest.fixture()
def cliente_http(fabrica):
    return TestClient(criar_app(com_ciclo=False))


@pytest.fixture()
def painel(cliente_http):
    r = cliente_http.post("/painel/entrar", data={"senha": "senha-teste"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/painel"
    return cliente_http
