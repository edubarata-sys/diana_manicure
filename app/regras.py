"""Regras puras da agenda (sem banco): horários livres, sinal, promoção, frequência, mensagens."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")

DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def agora_loja() -> datetime:
    """Agora no horário de Brasília, sem tz (é como gravamos no banco)."""
    return datetime.now(FUSO).replace(tzinfo=None, microsecond=0)


def brl(centavos: int) -> str:
    negativo = centavos < 0
    c = abs(int(centavos))
    inteiro = f"{c // 100:,}".replace(",", ".")
    return f"{'-' if negativo else ''}R$ {inteiro},{c % 100:02d}"


def ler_valor(texto: str) -> int | None:
    """'80' -> 8000; '12,50' -> 1250; '1.234,56' -> 123456; vazio/inválido -> None."""
    t = (texto or "").strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.search(r"\.\d{3}$", t):
        t = t.replace(".", "")
    try:
        v = round(float(t) * 100)
    except ValueError:
        return None
    return v if v >= 0 else None


def so_digitos(texto: str) -> str:
    d = re.sub(r"\D", "", texto or "")
    # Guarda sem o 55 do país; o link do WhatsApp põe de volta.
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    return d


def whatsapp_valido(digitos: str) -> bool:
    return len(digitos) in (10, 11)


def formatar_whatsapp(digitos: str) -> str:
    d = so_digitos(digitos)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return digitos


def link_whatsapp(digitos: str, mensagem: str = "") -> str:
    url = f"https://wa.me/55{so_digitos(digitos)}"
    return f"{url}?text={quote(mensagem)}" if mensagem else url


def calcular_sinal(preco: int, percentual: int, eh_pacote: bool) -> int:
    """Pacote é pago inteiro antes; demais, o percentual (arredonda pra cima no centavo)."""
    if eh_pacote:
        return preco
    return -(-preco * percentual // 100)


def _hhmm(texto: str) -> time:
    h, m = texto.strip().split(":")
    return time(int(h), int(m))


def ler_pausas(texto: str) -> list[tuple[time, time]]:
    pausas = []
    for parte in (texto or "").split(","):
        parte = parte.strip()
        if not parte or "-" not in parte:
            continue
        a, b = parte.split("-", 1)
        try:
            pausas.append((_hhmm(a), _hhmm(b)))
        except ValueError:
            continue
    return pausas


def ler_dias(texto: str) -> set[int]:
    return {int(x) for x in (texto or "").split(",") if x.strip().isdigit()}


@dataclass(frozen=True)
class Expediente:
    dias: set[int]
    abre: time
    fecha: time
    pausas: list[tuple[time, time]]
    passo_min: int = 30
    antecedencia_h: int = 2


def _sobrepoe(a_ini: datetime, a_fim: datetime, b_ini: datetime, b_fim: datetime) -> bool:
    return a_ini < b_fim and b_ini < a_fim


def horarios_livres(
    dia: date,
    duracao_min: int,
    exp: Expediente,
    ocupados: list[tuple[datetime, datetime]],
    agora: datetime,
) -> list[datetime]:
    """Inícios possíveis no dia: dentro do expediente, sem cruzar pausa nem outro horário,
    e com a antecedência mínima. Passo fixo a partir da abertura."""
    if dia.isoweekday() not in exp.dias:
        return []
    inicio_dia = datetime.combine(dia, exp.abre)
    fim_dia = datetime.combine(dia, exp.fecha)
    limite = agora + timedelta(hours=exp.antecedencia_h)
    pausas = [(datetime.combine(dia, a), datetime.combine(dia, b)) for a, b in exp.pausas]
    dur = timedelta(minutes=duracao_min)
    livres = []
    t = inicio_dia
    while t + dur <= fim_dia:
        fim = t + dur
        if t >= limite and not any(_sobrepoe(t, fim, a, b) for a, b in pausas + ocupados):
            livres.append(t)
        t += timedelta(minutes=exp.passo_min)
    return livres


def semanas_do_mes(ano: int, mes: int) -> list[list[date | None]]:
    """Grade do calendário começando no domingo (como no layout: D S T Q Q S S)."""
    primeiro = date(ano, mes, 1)
    proximo = date(ano + (mes == 12), mes % 12 + 1, 1)
    deslocamento = primeiro.isoweekday() % 7  # domingo = 0
    celulas: list[date | None] = [None] * deslocamento
    d = primeiro
    while d < proximo:
        celulas.append(d)
        d += timedelta(days=1)
    while len(celulas) % 7:
        celulas.append(None)
    return [celulas[i : i + 7] for i in range(0, len(celulas), 7)]


def data_extenso(d: datetime | date) -> str:
    return f"{DIAS_SEMANA[d.isoweekday() - 1].capitalize()}, {d.day:02d}/{d.month:02d}"


@dataclass(frozen=True)
class Progresso:
    feitas: int
    meta: int
    ganhou: bool

    @property
    def faltam(self) -> int:
        return max(0, self.meta - self.feitas)


def progresso_promocao(idas: list[tuple[datetime, bool]], meta: int) -> Progresso:
    """idas = (quando, foi_cortesia) dos atendimentos concluídos.
    Conta as idas pagas depois da última cortesia; chegou na meta = próxima é grátis."""
    feitas = 0
    for _, cortesia in sorted(idas):
        feitas = 0 if cortesia else feitas + 1
    if meta <= 0:
        return Progresso(feitas, 0, False)
    return Progresso(min(feitas, meta), meta, feitas >= meta)


@dataclass(frozen=True)
class Frequencia:
    visitas: int
    ultima: date | None
    intervalo_medio: int | None
    dias_sem_vir: int | None
    sumida: bool


def frequencia(datas: list[date], hoje: date) -> Frequencia:
    """Sazonalidade da cliente. 'Sumida' = passou bem do ritmo dela (1,5x o intervalo médio,
    mínimo 30 dias; com uma visita só, 45 dias)."""
    datas = sorted(set(datas))
    if not datas:
        return Frequencia(0, None, None, None, False)
    ultima = datas[-1]
    dias_sem = (hoje - ultima).days
    intervalo = None
    if len(datas) >= 2:
        intervalo = round((datas[-1] - datas[0]).days / (len(datas) - 1))
    limite = max(30, round(intervalo * 1.5)) if intervalo else 45
    return Frequencia(len(datas), ultima, intervalo, dias_sem, dias_sem > limite)


def primeiro_nome(nome: str) -> str:
    return (nome or "").strip().split(" ")[0].capitalize()


def msg_lembrete(nome: str, servico: str, inicio: datetime, tolerancia_min: int = 10) -> str:
    return (
        f"Oi, {primeiro_nome(nome)}! 💅 Passando pra lembrar do seu horário: "
        f"{servico}, {data_extenso(inicio)} às {inicio:%H:%M}. "
        f"Lembrando: tolerância de {tolerancia_min} minutos de atraso; passou disso, o atendimento é reagendado. "
        "Te espero! Diana"
    )


def msg_sinal_recebido(nome: str, servico: str, inicio: datetime) -> str:
    return (
        f"Oi, {primeiro_nome(nome)}! Recebi seu sinal 💖 Seu horário está confirmado: "
        f"{servico}, {data_extenso(inicio)} às {inicio:%H:%M}. Obrigada!"
    )


def msg_saudade(nome: str) -> str:
    return (
        f"Oi, {primeiro_nome(nome)}! Tudo bem? 💖 Faz um tempinho que você não vem. "
        "Que tal cuidar das unhas essa semana? É só escolher o horário no meu site ou me chamar aqui."
    )


def msg_promocao(nome: str, faltam: int) -> str:
    if faltam <= 0:
        return (
            f"Oi, {primeiro_nome(nome)}! 🎉 Você completou suas idas e ganhou um atendimento grátis! "
            "Me chama pra agendar."
        )
    return (
        f"Oi, {primeiro_nome(nome)}! 💅 Falta(m) só {faltam} ida(s) pra você ganhar um atendimento grátis. "
        "Bora agendar?"
    )


def msg_comprovante(nome: str, servico: str, inicio: datetime, sinal: int) -> str:
    return (
        f"Oi, Diana! Sou {nome}. Agendei {servico} para {data_extenso(inicio)} às {inicio:%H:%M} "
        f"e paguei o sinal de {brl(sinal)}. Segue o comprovante:"
    )
