"""Peças comuns das rotas: banco por requisição, templates e recados (flash)."""

from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import db as banco
from . import models as m
from .regras import brl, data_extenso, formatar_whatsapp, link_whatsapp

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["brl"] = brl
templates.env.filters["zap"] = formatar_whatsapp
templates.env.filters["extenso"] = data_extenso
templates.env.globals["link_whatsapp"] = link_whatsapp
templates.env.globals["ROTULO_STATUS"] = m.ROTULO_STATUS
templates.env.globals["ROTULO_FORMA"] = m.ROTULO_FORMA


def get_db() -> Iterator[Session]:
    # Lê a fábrica no módulo a cada chamada (os testes trocam por um banco em memória).
    with banco.SessaoLocal() as sessao:
        yield sessao


def recado(request: Request, texto: str, tipo: str = "ok") -> None:
    request.session["recado"] = {"texto": texto, "tipo": tipo}


def pegar_recado(request: Request) -> dict | None:
    return request.session.pop("recado", None)


def ir(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def render(request: Request, nome: str, **ctx):
    ctx.setdefault("recado", pegar_recado(request))
    return templates.TemplateResponse(request, nome, ctx)
