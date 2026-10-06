"""App da agenda da Diana Ferraz — site da cliente + painel da Diana."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .db import Base, SessaoLocal, engine
from .servicos import semear

PASTA = Path(__file__).parent


def iniciar_banco(eng=engine, fabrica=SessaoLocal) -> None:
    Base.metadata.create_all(eng)
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
        secret_key=os.environ.get("SECRET_KEY", "dev-troque-em-producao"),
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
