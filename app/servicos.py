"""Operações com banco usadas pelas rotas (camada fina sobre as regras puras)."""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .regras import (
    Expediente,
    agora_loja,
    calcular_sinal,
    frequencia,
    horarios_livres,
    ler_dias,
    ler_pausas,
    progresso_promocao,
    so_digitos,
    _hhmm,
)

SERVICOS_INICIAIS = [
    # nome, descricao, preco, duracao, agendavel, pacote(maos, pes)
    ("Pé + Mão", "Cuidado completo para mãos e pés", 6000, 120, True, None),
    ("Só Mão", "Cutilagem e esmaltação das mãos", 4000, 60, True, None),
    ("Só Pé", "Cuidado e esmaltação dos pés", 4000, 60, True, None),
    ("Só Esmaltação", "Renove a cor das suas unhas", 2000, 30, True, None),
    ("Pacote mensal", "4 mãos + 2 pés", 16000, 60, True, (4, 2)),
    ("Spa dos Pés + Esmaltação", "Relaxamento e cuidado especial", 10000, 120, True, None),
    ("Adesivos", "Detalhes delicados para finalizar · o par, avise no atendimento", 350, 0, False, None),
]


def semear(db: Session) -> None:
    """Cria a configuração e a tabela de serviços na primeira vez (não mexe se já existir)."""
    if db.get(m.Config, 1) is None:
        db.add(m.Config(id=1))
    if db.scalar(select(m.Servico.id).limit(1)) is None:
        for ordem, (nome, desc, preco, dur, agendavel, pacote) in enumerate(SERVICOS_INICIAIS):
            db.add(
                m.Servico(
                    nome=nome,
                    descricao=desc,
                    preco=preco,
                    duracao_min=dur,
                    ordem=ordem,
                    agendavel=agendavel,
                    eh_pacote=pacote is not None,
                    pacote_maos=pacote[0] if pacote else 0,
                    pacote_pes=pacote[1] if pacote else 0,
                )
            )
    db.commit()


def config(db: Session) -> m.Config:
    c = db.get(m.Config, 1)
    if c is None:
        semear(db)
        c = db.get(m.Config, 1)
    assert c is not None
    return c


def expediente(c: m.Config) -> Expediente:
    return Expediente(
        dias=ler_dias(c.dias_atendimento),
        abre=_hhmm(c.abre),
        fecha=_hhmm(c.fecha),
        pausas=ler_pausas(c.pausas),
        passo_min=max(5, c.passo_minutos),
        antecedencia_h=max(0, c.antecedencia_minima_horas),
    )


def servicos_ativos(db: Session) -> list[m.Servico]:
    return list(db.scalars(select(m.Servico).where(m.Servico.ativo).order_by(m.Servico.ordem)))


def expirar_sinais(db: Session) -> int:
    """Reserva sem sinal depois do prazo libera o horário sozinha."""
    c = config(db)
    limite = agora_loja() - timedelta(hours=c.horas_expira_sinal)
    vencidos = db.scalars(
        select(m.Agendamento).where(
            m.Agendamento.status == m.AGUARDANDO_SINAL,
            m.Agendamento.criado_em < limite,
            m.Agendamento.origem == "site",
        )
    ).all()
    for a in vencidos:
        a.status = m.EXPIRADO
    if vencidos:
        db.commit()
    return len(vencidos)


def ocupados_no_dia(db: Session, dia: date, ignorar_id: int | None = None) -> list[tuple[datetime, datetime]]:
    inicio = datetime.combine(dia, datetime.min.time())
    fim = inicio + timedelta(days=1)
    q = select(m.Agendamento).where(
        m.Agendamento.inicio < fim,
        m.Agendamento.fim > inicio,
        m.Agendamento.status.in_(m.OCUPA_HORARIO),
    )
    return [(a.inicio, a.fim) for a in db.scalars(q) if a.id != ignorar_id]


def livres(db: Session, dia: date, servico: m.Servico) -> list[datetime]:
    c = config(db)
    hoje = agora_loja().date()
    if dia < hoje or dia > hoje + timedelta(days=c.dias_maximos_agenda):
        return []
    return horarios_livres(dia, servico.duracao_min, expediente(c), ocupados_no_dia(db, dia), agora_loja())


def cliente_por_whatsapp(db: Session, whatsapp: str) -> m.Cliente | None:
    return db.scalar(select(m.Cliente).where(m.Cliente.whatsapp == so_digitos(whatsapp)))


def obter_ou_criar_cliente(db: Session, nome: str, whatsapp: str) -> m.Cliente:
    cli = cliente_por_whatsapp(db, whatsapp)
    if cli is None:
        cli = m.Cliente(nome=nome.strip(), whatsapp=so_digitos(whatsapp))
        db.add(cli)
        db.flush()
    return cli


class HorarioIndisponivel(Exception):
    pass


def criar_agendamento(
    db: Session,
    cliente: m.Cliente,
    servico: m.Servico,
    inicio: datetime,
    origem: str = "site",
    validar_expediente: bool = True,
    observacao: str = "",
) -> m.Agendamento:
    """Cria a reserva. Pelo site, só em horário livre de verdade (revalida aqui, não confia na tela)."""
    c = config(db)
    fim = inicio + timedelta(minutes=max(servico.duracao_min, 15))
    if validar_expediente:
        if inicio not in livres(db, inicio.date(), servico):
            raise HorarioIndisponivel("Esse horário acabou de ser ocupado. Escolha outro, por favor.")
    elif any(a < fim and inicio < b for a, b in ocupados_no_dia(db, inicio.date())):
        raise HorarioIndisponivel("Já tem atendimento nesse horário.")
    ag = m.Agendamento(
        codigo=secrets.token_urlsafe(9),
        cliente_id=cliente.id,
        servico_id=servico.id,
        inicio=inicio,
        fim=fim,
        valor=servico.preco,
        sinal=calcular_sinal(servico.preco, c.sinal_percentual, servico.eh_pacote),
        origem=origem,
        observacao=observacao,
    )
    # Cliente com pacote ativo agendando mão/pé: usa o pacote, sem sinal.
    pacote = pacote_ativo(cliente)
    if pacote and not servico.eh_pacote and servico.nome.lower() in ("só mão", "só pé"):
        ag.pacote_id = pacote.id
        ag.valor = 0
        ag.sinal = 0
        ag.status = m.CONFIRMADO
    db.add(ag)
    db.commit()
    return ag


def pacote_ativo(cliente: m.Cliente) -> m.Pacote | None:
    ativos = [p for p in cliente.pacotes if p.restantes > 0]
    return sorted(ativos, key=lambda p: p.comprado_em)[0] if ativos else None


def confirmar_sinal(db: Session, ag: m.Agendamento, forma: str = "pix") -> None:
    if ag.status not in (m.AGUARDANDO_SINAL, m.EXPIRADO):
        return
    ag.status = m.CONFIRMADO
    ag.sinal_pago_em = agora_loja()
    if ag.sinal > 0:
        tipo = "pacote" if ag.servico.eh_pacote else "sinal"
        db.add(
            m.Pagamento(
                cliente_id=ag.cliente_id,
                agendamento_id=ag.id,
                tipo=tipo,
                descricao=f"{'Pacote' if tipo == 'pacote' else 'Sinal'} · {ag.servico.nome}",
                valor=ag.sinal,
                forma=forma,
            )
        )
    if ag.servico.eh_pacote and ag.pacote_id is None:
        pac = m.Pacote(
            cliente_id=ag.cliente_id,
            valor=ag.valor,
            maos_total=ag.servico.pacote_maos,
            pes_total=ag.servico.pacote_pes,
        )
        db.add(pac)
        db.flush()
        ag.pacote_id = pac.id
    db.commit()


def concluir(
    db: Session,
    ag: m.Agendamento,
    valor_recebido: int,
    forma: str,
    adesivos_pares: int = 0,
    cortesia: bool = False,
    uso_pacote: str = "",
) -> None:
    """Fecha o atendimento: lança o restante pago, adesivos e baixa o pacote se for o caso."""
    ag.status = m.CONCLUIDO
    ag.concluido_em = agora_loja()
    ag.cortesia = cortesia
    if valor_recebido > 0:
        db.add(
            m.Pagamento(
                cliente_id=ag.cliente_id,
                agendamento_id=ag.id,
                tipo="servico",
                descricao=ag.servico.nome,
                valor=valor_recebido,
                forma=forma,
            )
        )
    if adesivos_pares > 0:
        adesivo = db.scalar(select(m.Servico).where(m.Servico.nome == "Adesivos"))
        preco = adesivo.preco if adesivo else 350
        db.add(
            m.Pagamento(
                cliente_id=ag.cliente_id,
                agendamento_id=ag.id,
                tipo="adesivo",
                descricao=f"Adesivos ({adesivos_pares} par{'es' if adesivos_pares > 1 else ''})",
                valor=preco * adesivos_pares,
                forma=forma,
            )
        )
    if ag.pacote is not None and uso_pacote in ("mao", "pe"):
        if uso_pacote == "mao":
            ag.pacote.maos_usadas += 1
        else:
            ag.pacote.pes_usadas += 1
    db.commit()


def marcar_falta(db: Session, ag: m.Agendamento) -> None:
    """Falta: sinal fica (regra da Diana). No pacote, o atendimento é perdido."""
    ag.status = m.FALTA
    if ag.pacote is not None and not ag.servico.eh_pacote:
        ag.pacote.perdidos += 1
        if "mão" in ag.servico.nome.lower():
            ag.pacote.maos_usadas += 1
        else:
            ag.pacote.pes_usadas += 1
    db.commit()


def progresso_cliente(db: Session, cliente: m.Cliente):
    c = config(db)
    idas = [(a.concluido_em or a.inicio, a.cortesia) for a in cliente.agendamentos if a.status == m.CONCLUIDO]
    return progresso_promocao(idas, c.promo_idas)


def frequencia_cliente(cliente: m.Cliente):
    datas = [a.inicio.date() for a in cliente.agendamentos if a.status == m.CONCLUIDO]
    return frequencia(datas, agora_loja().date())


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def senha_confere(senha: str, hash_: str | None) -> bool:
    if not hash_:
        return False
    try:
        return bcrypt.checkpw(senha.encode(), hash_.encode())
    except ValueError:
        return False
