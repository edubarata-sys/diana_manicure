"""Painel da Diana: agenda, clientes (frequência e mensagens), financeiro por cliente, configurações."""

import hmac
import os
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models as m
from . import servicos as sv
from .regras import (
    MESES,
    agora_loja,
    ler_valor,
    msg_lembrete,
    msg_promocao,
    msg_saudade,
    msg_sinal_recebido,
    so_digitos,
    whatsapp_valido,
)
from .web import get_db, ir, recado, render

router = APIRouter(prefix="/painel")


def _logada(request: Request) -> bool:
    return bool(request.session.get("admin"))




def _exigir(request: Request):
    if not _logada(request):
        return ir("/painel/entrar")
    return None


@router.get("/entrar")
def entrar_form(request: Request, db: Session = Depends(get_db)):
    return render(
        request,
        "painel/entrar.html",
        config=sv.config(db),
        sem_senha=not os.environ.get("ADMIN_SENHA"),
    )


@router.post("/entrar")
def entrar(request: Request, senha: str = Form("")):
    certa = os.environ.get("ADMIN_SENHA", "")
    if certa and hmac.compare_digest(senha.encode(), certa.encode()):
        request.session["admin"] = True
        return ir("/painel")
    recado(request, "Senha incorreta.", "erro")
    return ir("/painel/entrar")


@router.post("/sair")
def sair(request: Request):
    request.session.pop("admin", None)
    return ir("/painel/entrar")


# ---------------- Agenda ----------------


def _agendamentos_do_dia(db: Session, dia: date) -> list[m.Agendamento]:
    ini = datetime.combine(dia, datetime.min.time())
    return list(
        db.scalars(
            select(m.Agendamento)
            .where(m.Agendamento.inicio >= ini, m.Agendamento.inicio < ini + timedelta(days=1))
            .order_by(m.Agendamento.inicio)
        )
    )


@router.get("")
def agenda(request: Request, dia: str | None = None, db: Session = Depends(get_db)):
    if (r := _exigir(request)) is not None:
        return r
    sv.expirar_sinais(db)
    hoje = agora_loja().date()
    try:
        d = date.fromisoformat(dia) if dia else hoje
    except ValueError:
        d = hoje
    pendentes = list(
        db.scalars(
            select(m.Agendamento)
            .where(m.Agendamento.status == m.AGUARDANDO_SINAL, m.Agendamento.inicio >= datetime.combine(hoje, datetime.min.time()))
            .order_by(m.Agendamento.inicio)
        )
    )
    itens = _agendamentos_do_dia(db, d)
    mensagens = {
        a.id: {
            "lembrete": msg_lembrete(a.cliente.nome, a.servico.nome, a.inicio),
            "sinal": msg_sinal_recebido(a.cliente.nome, a.servico.nome, a.inicio),
        }
        for a in itens + pendentes
    }
    semana = [hoje + timedelta(days=i) for i in range(7)]
    return render(
        request,
        "painel/agenda.html",
        config=sv.config(db),
        dia=d,
        hoje=hoje,
        itens=itens,
        pendentes=pendentes,
        mensagens=mensagens,
        semana=semana,
        anterior=(d - timedelta(days=1)).isoformat(),
        proximo=(d + timedelta(days=1)).isoformat(),
        formas=m.FORMAS,
    )


def _ag(db: Session, ag_id: int) -> m.Agendamento | None:
    return db.get(m.Agendamento, ag_id)


def _voltar_dia(ag: m.Agendamento) -> str:
    return f"/painel?dia={ag.inicio.date().isoformat()}"


@router.post("/ag/{ag_id}/sinal")
def sinal(request: Request, ag_id: int, forma: str = Form("pix"), db: Session = Depends(get_db)):
    if (r := _exigir(request)) is not None:
        return r
    ag = _ag(db, ag_id)
    if ag is None:
        return ir("/painel")
    sv.confirmar_sinal(db, ag, forma if forma in m.FORMAS else "pix")
    recado(request, f"Sinal de {ag.cliente.nome} confirmado. Avise ela pelo WhatsApp.")
    return ir(_voltar_dia(ag))


@router.post("/ag/{ag_id}/concluir")
def concluir(
    request: Request,
    ag_id: int,
    valor: str = Form(""),
    forma: str = Form("pix"),
    adesivos: int = Form(0),
    cortesia: str = Form(""),
    uso_pacote: str = Form(""),
    db: Session = Depends(get_db),
):
    if (r := _exigir(request)) is not None:
        return r
    ag = _ag(db, ag_id)
    if ag is None:
        return ir("/painel")
    recebido = ler_valor(valor)
    if recebido is None:
        recebido = 0
    sv.concluir(
        db,
        ag,
        recebido,
        forma if forma in m.FORMAS else "pix",
        max(0, adesivos),
        bool(cortesia),
        uso_pacote,
    )
    recado(request, f"Atendimento de {ag.cliente.nome} concluído.")
    return ir(_voltar_dia(ag))


@router.post("/ag/{ag_id}/cancelar")
def cancelar(request: Request, ag_id: int, db: Session = Depends(get_db)):
    if (r := _exigir(request)) is not None:
        return r
    ag = _ag(db, ag_id)
    if ag is None:
        return ir("/painel")
    ag.status = m.CANCELADO
    db.commit()
    recado(request, "Agendamento cancelado. O horário ficou livre.")
    return ir(_voltar_dia(ag))


@router.post("/ag/{ag_id}/falta")
def falta(request: Request, ag_id: int, db: Session = Depends(get_db)):
    if (r := _exigir(request)) is not None:
        return r
    ag = _ag(db, ag_id)
    if ag is None:
        return ir("/painel")
    sv.marcar_falta(db, ag)
    recado(request, "Falta registrada. O sinal fica com você (regra do agendamento).")
    return ir(_voltar_dia(ag))


@router.get("/novo")
def novo_form(
    request: Request,
    cliente_id: int | None = None,
    servico: int | None = None,
    dia: str | None = None,
    db: Session = Depends(get_db),
):
    if (r := _exigir(request)) is not None:
        return r
    hoje = agora_loja().date()
    try:
        d = date.fromisoformat(dia) if dia else hoje
    except ValueError:
        d = hoje
    servicos = [s for s in sv.servicos_ativos(db) if s.agendavel]
    s = db.get(m.Servico, servico) if servico else (servicos[0] if servicos else None)
    livres = sv.livres(db, d, s) if s else []
    clientes = list(db.scalars(select(m.Cliente).order_by(m.Cliente.nome)))
    return render(
        request,
        "painel/novo.html",
        config=sv.config(db),
        servicos=servicos,
        servico=s,
        dia=d,
        livres=livres,
        clientes=clientes,
        cliente_id=cliente_id,
    )


@router.post("/novo")
def novo(
    request: Request,
    servico: int = Form(...),
    dia: str = Form(...),
    hora: str = Form(...),
    cliente_id: str = Form(""),
    nome: str = Form(""),
    whatsapp: str = Form(""),
    sinal_pago: str = Form(""),
    observacao: str = Form(""),
    db: Session = Depends(get_db),
):
    if (r := _exigir(request)) is not None:
        return r
    s = db.get(m.Servico, servico)
    try:
        inicio = datetime.fromisoformat(f"{dia}T{hora}")
    except ValueError:
        recado(request, "Data ou hora inválida.", "erro")
        return ir("/painel/novo")
    if cliente_id.strip().isdigit():
        cliente = db.get(m.Cliente, int(cliente_id))
    else:
        zap = so_digitos(whatsapp)
        if not nome.strip() or not whatsapp_valido(zap):
            recado(request, "Escolha uma cliente ou informe nome e WhatsApp.", "erro")
            return ir(f"/painel/novo?dia={dia}&servico={servico}")
        cliente = sv.obter_ou_criar_cliente(db, nome, zap)
    if s is None or cliente is None:
        return ir("/painel/novo")
    try:
        # A Diana pode encaixar fora da grade, mas nunca em cima de outro horário.
        ag = sv.criar_agendamento(db, cliente, s, inicio, origem="painel", validar_expediente=False, observacao=observacao)
    except sv.HorarioIndisponivel as e:
        db.rollback()
        recado(request, str(e), "erro")
        return ir(f"/painel/novo?dia={dia}&servico={servico}")
    if sinal_pago:
        sv.confirmar_sinal(db, ag)
    recado(request, f"Agendado: {cliente.nome}, {s.nome} às {inicio:%H:%M}.")
    return ir(f"/painel?dia={dia}")


# ---------------- Clientes ----------------


@router.get("/clientes")
def clientes(request: Request, filtro: str = "todas", q: str = "", db: Session = Depends(get_db)):
    if (r := _exigir(request)) is not None:
        return r
    todas = list(db.scalars(select(m.Cliente).order_by(m.Cliente.nome)))
    linhas = []
    for c in todas:
        if q and q.lower() not in c.nome.lower() and so_digitos(q) not in c.whatsapp:
            continue
        f = sv.frequencia_cliente(c)
        if filtro == "sumidas" and not f.sumida:
            continue
        linhas.append({"cliente": c, "freq": f, "msg": msg_saudade(c.nome)})
    linhas.sort(key=lambda x: (x["freq"].dias_sem_vir is None, -(x["freq"].dias_sem_vir or 0)) if filtro == "sumidas" else 0)
    return render(request, "painel/clientes.html", config=sv.config(db), linhas=linhas, filtro=filtro, q=q)


@router.post("/clientes")
def cliente_novo(
    request: Request,
    nome: str = Form(""),
    whatsapp: str = Form(""),
    observacoes: str = Form(""),
    db: Session = Depends(get_db),
):
    if (r := _exigir(request)) is not None:
        return r
    zap = so_digitos(whatsapp)
    if not nome.strip() or not whatsapp_valido(zap):
        recado(request, "Informe nome e WhatsApp com DDD.", "erro")
        return ir("/painel/clientes")
    if sv.cliente_por_whatsapp(db, zap):
        recado(request, "Já existe cliente com esse WhatsApp.", "erro")
        return ir("/painel/clientes")
    c = m.Cliente(nome=nome.strip(), whatsapp=zap, observacoes=observacoes.strip())
    db.add(c)
    db.commit()
    recado(request, f"{c.nome} cadastrada.")
    return ir(f"/painel/clientes/{c.id}")


@router.get("/clientes/{cid}")
def cliente(request: Request, cid: int, db: Session = Depends(get_db)):
    if (r := _exigir(request)) is not None:
        return r
    c = db.get(m.Cliente, cid)
    if c is None:
        return ir("/painel/clientes")
    prog = sv.progresso_cliente(db, c)
    pagamentos = sorted(
        db.scalars(select(m.Pagamento).where(m.Pagamento.cliente_id == c.id)), key=lambda p: p.pago_em, reverse=True
    )
    return render(
        request,
        "painel/cliente.html",
        config=sv.config(db),
        c=c,
        freq=sv.frequencia_cliente(c),
        prog=prog,
        pacote=sv.pacote_ativo(c),
        agendamentos=sorted(c.agendamentos, key=lambda a: a.inicio, reverse=True),
        pagamentos=pagamentos,
        total_pago=sum(p.valor for p in pagamentos),
        msg_saudade=msg_saudade(c.nome),
        msg_promo=msg_promocao(c.nome, prog.faltam),
    )


@router.post("/clientes/{cid}")
def cliente_editar(
    request: Request,
    cid: int,
    nome: str = Form(""),
    whatsapp: str = Form(""),
    observacoes: str = Form(""),
    db: Session = Depends(get_db),
):
    if (r := _exigir(request)) is not None:
        return r
    c = db.get(m.Cliente, cid)
    if c is None:
        return ir("/painel/clientes")
    zap = so_digitos(whatsapp)
    outra = sv.cliente_por_whatsapp(db, zap)
    if not nome.strip() or not whatsapp_valido(zap) or (outra and outra.id != c.id):
        recado(request, "Nome e WhatsApp válidos (e que não seja de outra cliente).", "erro")
        return ir(f"/painel/clientes/{cid}")
    c.nome, c.whatsapp, c.observacoes = nome.strip(), zap, observacoes.strip()
    db.commit()
    recado(request, "Dados salvos.")
    return ir(f"/painel/clientes/{cid}")


# ---------------- Financeiro ----------------


@router.get("/financeiro")
def financeiro(request: Request, mes: str | None = None, db: Session = Depends(get_db)):
    if (r := _exigir(request)) is not None:
        return r
    hoje = agora_loja().date()
    try:
        ano, mm = (int(x) for x in (mes or f"{hoje:%Y-%m}").split("-"))
        ini = datetime(ano, mm, 1)
    except ValueError:
        ano, mm = hoje.year, hoje.month
        ini = datetime(ano, mm, 1)
    fim = datetime(ano + (mm == 12), mm % 12 + 1, 1)
    pagamentos = list(
        db.scalars(
            select(m.Pagamento)
            .where(m.Pagamento.pago_em >= ini, m.Pagamento.pago_em < fim)
            .order_by(m.Pagamento.pago_em.desc())
        )
    )
    por_forma: dict[str, int] = defaultdict(int)
    por_tipo: dict[str, int] = defaultdict(int)
    por_cliente: dict[int, dict] = {}
    for p in pagamentos:
        por_forma[p.forma] += p.valor
        por_tipo[p.tipo] += p.valor
        linha = por_cliente.setdefault(p.cliente_id, {"cliente": p.cliente, "total": 0, "qtd": 0})
        linha["total"] += p.valor
        linha["qtd"] += 1
    atendimentos = db.scalar(
        select(func.count(m.Agendamento.id)).where(
            m.Agendamento.status == m.CONCLUIDO, m.Agendamento.inicio >= ini, m.Agendamento.inicio < fim
        )
    )
    faltas = db.scalar(
        select(func.count(m.Agendamento.id)).where(
            m.Agendamento.status == m.FALTA, m.Agendamento.inicio >= ini, m.Agendamento.inicio < fim
        )
    )
    clientes = list(db.scalars(select(m.Cliente).order_by(m.Cliente.nome)))
    return render(
        request,
        "painel/financeiro.html",
        config=sv.config(db),
        mes=f"{ano}-{mm:02d}",
        titulo_mes=f"{MESES[mm - 1].capitalize()} {ano}",
        total=sum(p.valor for p in pagamentos),
        por_forma=dict(por_forma),
        por_tipo=dict(por_tipo),
        por_cliente=sorted(por_cliente.values(), key=lambda x: -x["total"]),
        pagamentos=pagamentos,
        atendimentos=atendimentos or 0,
        faltas=faltas or 0,
        clientes=clientes,
        formas=m.FORMAS,
        hoje=hoje,
    )


@router.post("/financeiro/lancar")
def financeiro_lancar(
    request: Request,
    cliente_id: int = Form(...),
    valor: str = Form(""),
    forma: str = Form("pix"),
    descricao: str = Form(""),
    data: str = Form(""),
    db: Session = Depends(get_db),
):
    if (r := _exigir(request)) is not None:
        return r
    v = ler_valor(valor)
    c = db.get(m.Cliente, cliente_id)
    if not v or c is None:
        recado(request, "Escolha a cliente e informe o valor.", "erro")
        return ir("/painel/financeiro")
    try:
        quando = datetime.fromisoformat(f"{data}T12:00") if data else agora_loja()
    except ValueError:
        quando = agora_loja()
    db.add(
        m.Pagamento(
            cliente_id=c.id,
            tipo="outro",
            descricao=descricao.strip() or "Recebimento avulso",
            valor=v,
            forma=forma if forma in m.FORMAS else "pix",
            pago_em=quando,
        )
    )
    db.commit()
    recado(request, f"Recebimento de {c.nome} lançado.")
    return ir(f"/painel/financeiro?mes={quando:%Y-%m}")


# ---------------- Configurações ----------------


@router.get("/config")
def config_form(request: Request, db: Session = Depends(get_db)):
    if (r := _exigir(request)) is not None:
        return r
    servicos = list(db.scalars(select(m.Servico).order_by(m.Servico.ordem)))
    return render(request, "painel/config.html", config=sv.config(db), servicos=servicos)


CAMPOS_TEXTO = ("nome_negocio", "chave_pix", "endereco", "abre", "fecha", "pausas", "aviso_tabela")
CAMPOS_NUM = (
    "sinal_percentual",
    "horas_expira_sinal",
    "horas_cancelamento",
    "promo_idas",
    "passo_minutos",
    "antecedencia_minima_horas",
    "dias_maximos_agenda",
)


@router.post("/config")
async def config_salvar(request: Request, db: Session = Depends(get_db)):
    if (r := _exigir(request)) is not None:
        return r
    form = await request.form()
    c = sv.config(db)
    for campo in CAMPOS_TEXTO:
        if campo in form:
            setattr(c, campo, str(form[campo]).strip())
    for campo in CAMPOS_NUM:
        valor = str(form.get(campo, "")).strip()
        if valor.isdigit():
            setattr(c, campo, int(valor))
    zap = so_digitos(str(form.get("whatsapp", "")))
    if whatsapp_valido(zap):
        c.whatsapp = zap
    dias = [d for d in form.getlist("dias") if str(d).isdigit()]
    if dias:
        c.dias_atendimento = ",".join(sorted(set(str(d) for d in dias)))
    try:
        sv.expediente(c)
    except ValueError:
        db.rollback()
        recado(request, "Horário inválido. Use HH:MM e pausas como 11:00-12:00.", "erro")
        return ir("/painel/config")
    db.commit()
    recado(request, "Configurações salvas.")
    return ir("/painel/config")


@router.post("/servicos")
async def servicos_salvar(request: Request, db: Session = Depends(get_db)):
    """Salva a tabela inteira de uma vez (linhas existentes + uma nova opcional)."""
    if (r := _exigir(request)) is not None:
        return r
    form = await request.form()
    for s in db.scalars(select(m.Servico)):
        p = f"s{s.id}_"
        if f"{p}nome" not in form:
            continue
        s.nome = str(form[f"{p}nome"]).strip() or s.nome
        s.descricao = str(form.get(f"{p}descricao", "")).strip()
        preco = ler_valor(str(form.get(f"{p}preco", "")))
        if preco is not None:
            s.preco = preco
        dur = str(form.get(f"{p}duracao", "")).strip()
        if dur.isdigit():
            s.duracao_min = int(dur)
        s.ativo = f"{p}ativo" in form
        s.agendavel = f"{p}agendavel" in form
    novo_nome = str(form.get("novo_nome", "")).strip()
    novo_preco = ler_valor(str(form.get("novo_preco", "")))
    if novo_nome and novo_preco:
        dur = str(form.get("novo_duracao", "60")).strip()
        db.add(
            m.Servico(
                nome=novo_nome,
                descricao=str(form.get("novo_descricao", "")).strip(),
                preco=novo_preco,
                duracao_min=int(dur) if dur.isdigit() else 60,
                ordem=100,
            )
        )
    db.commit()
    recado(request, "Tabela de serviços salva.")
    return ir("/painel/config")
