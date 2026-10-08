"""App da agenda da Diana Ferraz — site da cliente + painel da Diana."""

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import inspect, text
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .db import Base, SessaoLocal, engine
from .servicos import semear

PASTA = Path(__file__).parent


# Colunas que entraram depois da primeira subida: create_all só cria tabela nova,
# não acrescenta coluna em tabela que já existe no Postgres do Railway.
COLUNAS_NOVAS = [
    # tabela, coluna, DDL, SQL de preenchimento logo após criar
    ("servicos", "ultimo_inicio", "VARCHAR(5) NOT NULL DEFAULT ''",
     None),
    ("config", "tolerancia_atraso_min", "INTEGER NOT NULL DEFAULT 10", None),
]


def atualizar_colunas(eng) -> list[str]:
    feitas = []
    nomes = inspect(eng).get_table_names()
    for tabela, coluna, ddl, preencher in COLUNAS_NOVAS:
        if tabela not in nomes:
            continue
        existentes = {c["name"] for c in inspect(eng).get_columns(tabela)}
        if coluna in existentes:
            continue
        with eng.begin() as conn:
            conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {ddl}"))
            if preencher:
                conn.execute(text(preencher))
        feitas.append(f"{tabela}.{coluna}")
    return feitas


def iniciar_banco(eng=engine, fabrica=SessaoLocal) -> None:
    Base.metadata.create_all(eng)
    atualizar_colunas(eng)
    with fabrica() as db:
        semear(db)


@asynccontextmanager
async def ciclo(_app: FastAPI):
    iniciar_banco()
    yield


def criar_app(com_ciclo: bool = True) -> FastAPI:
    app = FastAPI(title="Agenda Diana Ferraz", lifespan=ciclo if com_ciclo else None, docs_url=None, redoc_url=None)
    app.add_middleware(
        SessionMiddleware,
        # Sem SECRET_KEY, gera uma aleatoria a cada subida (sessoes caem no restart).
        # Nunca um valor fixo: o repositorio e publico e daria pra forjar o login do painel.
        secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        session_cookie="agenda_sessao",
        max_age=60 * 60 * 24 * 30,
        same_site="lax",
        https_only=os.environ.get("HTTPS_ONLY", "0") == "1",
    )
    app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")

    from . import rotas_cliente, rotas_painel, rotas_publicas

    app.include_router(rotas_publicas.router)
    app.include_router(rotas_cliente.router)
    app.include_router(rotas_painel.router)

    @app.get("/saude")
    def saude():
        return {"status": "ok"}

    return app


app = criar_app()
