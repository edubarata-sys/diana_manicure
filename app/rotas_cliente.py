"""Área da cliente (opcional): histórico de idas e promoção. Agendar não depende disto."""

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from . import models as m
from . import servicos as sv
from .regras import so_digitos, whatsapp_valido
from .web import get_db, ir, recado, render

router = APIRouter(prefix="/minha-area")


def _cliente_logada(request: Request, db: Session) -> m.Cliente | None:
    cid = request.session.get("cliente_id")
    return db.get(m.Cliente, cid) if cid else None


@router.get("")
def area(request: Request, db: Session = Depends(get_db)):
    cliente = _cliente_logada(request, db)
    if cliente is None:
        return render(request, "cliente/entrar.html", config=sv.config(db))
    agendamentos = sorted(cliente.agendamentos, key=lambda a: a.inicio, reverse=True)
    return render(
        request,
        "cliente/area.html",
        config=sv.config(db),
        cliente=cliente,
        agendamentos=agendamentos,
        progresso=sv.progresso_cliente(db, cliente),
        pacote=sv.pacote_ativo(cliente),
    )


@router.post("/entrar")
def entrar(request: Request, whatsapp: str = Form(""), senha: str = Form(""), db: Session = Depends(get_db)):
    cliente = sv.cliente_por_whatsapp(db, whatsapp)
    if cliente is None or not sv.senha_confere(senha, cliente.senha_hash):
        recado(request, "WhatsApp ou senha não conferem.", "erro")
        return ir("/minha-area")
    request.session["cliente_id"] = cliente.id
    return ir("/minha-area")


@router.post("/cadastrar")
def cadastrar(
    request: Request,
    nome: str = Form(""),
    whatsapp: str = Form(""),
    senha: str = Form(""),
    db: Session = Depends(get_db),
):
    zap = so_digitos(whatsapp)
    if not nome.strip() or not whatsapp_valido(zap):
        recado(request, "Informe seu nome e WhatsApp com DDD.", "erro")
        return ir("/minha-area")
    if len(senha) < 6:
        recado(request, "A senha precisa ter pelo menos 6 caracteres.", "erro")
        return ir("/minha-area")
    cliente = sv.cliente_por_whatsapp(db, zap)
    if cliente is not None and cliente.senha_hash:
        recado(request, "Esse WhatsApp já tem cadastro. Entre com sua senha.", "erro")
        return ir("/minha-area")
    if cliente is None:
        cliente = m.Cliente(nome=nome.strip(), whatsapp=zap)
        db.add(cliente)
    # Quem já agendou sem cadastro (ou foi cadastrada pela Diana) só cria a senha:
    # o histórico dela aparece na hora.
    cliente.senha_hash = sv.hash_senha(senha)
    db.commit()
    request.session["cliente_id"] = cliente.id
    recado(request, "Cadastro feito! Aqui você acompanha suas idas e a promoção.")
    return ir("/minha-area")


@router.post("/sair")
def sair(request: Request):
    request.session.pop("cliente_id", None)
    return ir("/")
