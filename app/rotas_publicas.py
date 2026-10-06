"""Site da cliente: tabela, escolher horário, confirmar e pagar o sinal."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import servicos as sv
from .regras import MESES, agora_loja, msg_comprovante, semanas_do_mes, so_digitos, whatsapp_valido
from .web import get_db, ir, recado, render

router = APIRouter()


@router.get("/")
def inicio(request: Request, db: Session = Depends(get_db)):
    return render(request, "inicio.html", config=sv.config(db), servicos=sv.servicos_ativos(db))


def _servico_agendavel(db: Session, servico_id: int | None) -> m.Servico | None:
    if not servico_id:
        return None
    s = db.get(m.Servico, servico_id)
    return s if s and s.ativo and s.agendavel else None


@router.get("/agendar")
def agendar(
    request: Request,
    servico: int | None = None,
    mes: str | None = None,
    dia: str | None = None,
    db: Session = Depends(get_db),
):
    s = _servico_agendavel(db, servico)
    if s is None:
        recado(request, "Escolha um serviço para ver os horários.", "aviso")
        return ir("/#servicos")
    sv.expirar_sinais(db)
    hoje = agora_loja().date()
    try:
        ano, mm = (int(x) for x in (mes or f"{hoje:%Y-%m}").split("-"))
        date(ano, mm, 1)
    except ValueError:
        ano, mm = hoje.year, hoje.month
    dia_escolhido = None
    if dia:
        try:
            dia_escolhido = date.fromisoformat(dia)
        except ValueError:
            dia_escolhido = None

    semanas = semanas_do_mes(ano, mm)
    disponiveis = {d for semana in semanas for d in semana if d and sv.livres(db, d, s)}
    horarios = sv.livres(db, dia_escolhido, s) if dia_escolhido else []
    anterior = f"{ano - (mm == 1)}-{(mm - 2) % 12 + 1:02d}"
    proximo = f"{ano + (mm == 12)}-{mm % 12 + 1:02d}"
    return render(
        request,
        "agendar.html",
        config=sv.config(db),
        servico=s,
        semanas=semanas,
        disponiveis=disponiveis,
        titulo_mes=f"{MESES[mm - 1].capitalize()} {ano}",
        mes=f"{ano}-{mm:02d}",
        anterior=anterior,
        proximo=proximo,
        mostrar_anterior=(ano, mm) > (hoje.year, hoje.month),
        dia=dia_escolhido,
        horarios=horarios,
        hoje=hoje,
    )


def _ler_inicio(texto: str) -> datetime | None:
    try:
        return datetime.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


@router.get("/agendar/confirmar")
def confirmar_form(request: Request, servico: int, inicio: str, db: Session = Depends(get_db)):
    s = _servico_agendavel(db, servico)
    quando = _ler_inicio(inicio)
    if s is None or quando is None:
        return ir("/")
    cliente = None
    if request.session.get("cliente_id"):
        cliente = db.get(m.Cliente, request.session["cliente_id"])
    c = sv.config(db)
    return render(
        request,
        "confirmar.html",
        config=c,
        servico=s,
        inicio=quando,
        sinal=sv.calcular_sinal(s.preco, c.sinal_percentual, s.eh_pacote),
        cliente=cliente,
        pacote=sv.pacote_ativo(cliente) if cliente else None,
    )


@router.post("/agendar/confirmar")
def confirmar(
    request: Request,
    servico: int = Form(...),
    inicio: str = Form(...),
    nome: str = Form(""),
    whatsapp: str = Form(""),
    aceite: str = Form(""),
    db: Session = Depends(get_db),
):
    s = _servico_agendavel(db, servico)
    quando = _ler_inicio(inicio)
    voltar = f"/agendar/confirmar?servico={servico}&inicio={inicio}"
    if s is None or quando is None:
        return ir("/")
    zap = so_digitos(whatsapp)
    if not nome.strip() or not whatsapp_valido(zap):
        recado(request, "Informe seu nome e um WhatsApp com DDD.", "erro")
        return ir(voltar)
    if not aceite:
        recado(request, "Para agendar é preciso aceitar a regra do sinal.", "erro")
        return ir(voltar)
    cliente = sv.obter_ou_criar_cliente(db, nome, zap)
    try:
        ag = sv.criar_agendamento(db, cliente, s, quando)
    except sv.HorarioIndisponivel as e:
        db.rollback()
        recado(request, str(e), "erro")
        return ir(f"/agendar?servico={s.id}&dia={quando.date().isoformat()}&mes={quando:%Y-%m}")
    return ir(f"/reserva/{ag.codigo}")


@router.get("/reserva/{codigo}")
def reserva(request: Request, codigo: str, db: Session = Depends(get_db)):
    sv.expirar_sinais(db)
    ag = db.scalar(select(m.Agendamento).where(m.Agendamento.codigo == codigo))
    if ag is None:
        recado(request, "Agendamento não encontrado.", "erro")
        return ir("/")
    c = sv.config(db)
    return render(
        request,
        "reserva.html",
        config=c,
        ag=ag,
        msg_whatsapp=msg_comprovante(ag.cliente.nome, ag.servico.nome, ag.inicio, ag.sinal),
    )
