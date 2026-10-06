"""Tabelas da agenda. Dinheiro sempre em centavos (inteiro). Horários no fuso da loja, sem tz."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .regras import agora_loja


class Config(Base):
    """Uma linha só: tudo o que a Diana ajusta no painel."""

    __tablename__ = "config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    nome_negocio: Mapped[str] = mapped_column(String(120), default="Diana Ferraz")
    whatsapp: Mapped[str] = mapped_column(String(20), default="12982227847")
    chave_pix: Mapped[str] = mapped_column(String(120), default="12982227847")
    endereco: Mapped[str] = mapped_column(String(200), default="Euclides Ribeiro, nº 22, sala 2")
    sinal_percentual: Mapped[int] = mapped_column(Integer, default=50)
    horas_expira_sinal: Mapped[int] = mapped_column(Integer, default=12)
    horas_cancelamento: Mapped[int] = mapped_column(Integer, default=24)
    # Atraso tolerado; passou disso, o atendimento é reagendado.
    tolerancia_atraso_min: Mapped[int] = mapped_column(Integer, default=10)
    promo_idas: Mapped[int] = mapped_column(Integer, default=10)
    # Dias da semana ISO (1=segunda ... 7=domingo), separados por vírgula.
    dias_atendimento: Mapped[str] = mapped_column(String(20), default="2,3,4,5,6")
    abre: Mapped[str] = mapped_column(String(5), default="09:00")
    fecha: Mapped[str] = mapped_column(String(5), default="19:00")
    # Pausas "HH:MM-HH:MM" separadas por vírgula (almoço, café).
    pausas: Mapped[str] = mapped_column(String(200), default="11:00-12:00,15:00-15:15")
    passo_minutos: Mapped[int] = mapped_column(Integer, default=30)
    antecedencia_minima_horas: Mapped[int] = mapped_column(Integer, default=2)
    dias_maximos_agenda: Mapped[int] = mapped_column(Integer, default=45)
    aviso_tabela: Mapped[str] = mapped_column(String(120), default="Valores atualizados a partir de 20/10")


class Servico(Base):
    __tablename__ = "servicos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    descricao: Mapped[str] = mapped_column(String(160), default="")
    preco: Mapped[int] = mapped_column(Integer)  # centavos
    duracao_min: Mapped[int] = mapped_column(Integer, default=60)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    # False = só aparece na tabela (ex.: adesivos, avisados no atendimento).
    agendavel: Mapped[bool] = mapped_column(Boolean, default=True)
    # Pacote: paga 100% antes; quantos atendimentos de mão/pé dá direito.
    eh_pacote: Mapped[bool] = mapped_column(Boolean, default=False)
    pacote_maos: Mapped[int] = mapped_column(Integer, default=0)
    pacote_pes: Mapped[int] = mapped_column(Integer, default=0)


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    whatsapp: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # só dígitos
    senha_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    observacoes: Mapped[str] = mapped_column(Text, default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_loja)

    agendamentos: Mapped[list["Agendamento"]] = relationship(back_populates="cliente")
    pacotes: Mapped[list["Pacote"]] = relationship(back_populates="cliente")


# Situações de um agendamento.
AGUARDANDO_SINAL = "aguardando_sinal"
CONFIRMADO = "confirmado"
CONCLUIDO = "concluido"
CANCELADO = "cancelado"
FALTA = "falta"
EXPIRADO = "expirado"
OCUPA_HORARIO = (AGUARDANDO_SINAL, CONFIRMADO)

ROTULO_STATUS = {
    AGUARDANDO_SINAL: "Aguardando sinal",
    CONFIRMADO: "Confirmado",
    CONCLUIDO: "Concluído",
    CANCELADO: "Cancelado",
    FALTA: "Faltou",
    EXPIRADO: "Expirado (sem sinal)",
}


class Agendamento(Base):
    __tablename__ = "agendamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    servico_id: Mapped[int] = mapped_column(ForeignKey("servicos.id"))
    pacote_id: Mapped[int | None] = mapped_column(ForeignKey("pacotes.id"), nullable=True)
    inicio: Mapped[datetime] = mapped_column(DateTime, index=True)
    fim: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default=AGUARDANDO_SINAL, index=True)
    valor: Mapped[int] = mapped_column(Integer)  # centavos, preço na hora de agendar
    sinal: Mapped[int] = mapped_column(Integer)
    sinal_pago_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Atendimento grátis da promoção (não conta pro próximo ciclo).
    cortesia: Mapped[bool] = mapped_column(Boolean, default=False)
    origem: Mapped[str] = mapped_column(String(10), default="site")  # site | painel
    observacao: Mapped[str] = mapped_column(Text, default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_loja)

    cliente: Mapped[Cliente] = relationship(back_populates="agendamentos")
    servico: Mapped[Servico] = relationship()
    pacote: Mapped["Pacote | None"] = relationship(back_populates="agendamentos")
    pagamentos: Mapped[list["Pagamento"]] = relationship(back_populates="agendamento")


class Pacote(Base):
    __tablename__ = "pacotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    comprado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_loja)
    valor: Mapped[int] = mapped_column(Integer)
    maos_total: Mapped[int] = mapped_column(Integer, default=4)
    pes_total: Mapped[int] = mapped_column(Integer, default=2)
    maos_usadas: Mapped[int] = mapped_column(Integer, default=0)
    pes_usadas: Mapped[int] = mapped_column(Integer, default=0)
    # Atendimento perdido sem aviso de 24h (regra da Diana: perde, sem remarcar).
    perdidos: Mapped[int] = mapped_column(Integer, default=0)

    cliente: Mapped[Cliente] = relationship(back_populates="pacotes")
    agendamentos: Mapped[list[Agendamento]] = relationship(back_populates="pacote")

    @property
    def restantes(self) -> int:
        return max(0, self.maos_total + self.pes_total - self.maos_usadas - self.pes_usadas)


FORMAS = ("pix", "dinheiro", "debito", "credito")
ROTULO_FORMA = {"pix": "Pix", "dinheiro": "Dinheiro", "debito": "Débito", "credito": "Crédito"}


class Pagamento(Base):
    """Dinheiro que entrou, sempre ligado à cliente (financeiro por nome)."""

    __tablename__ = "pagamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    agendamento_id: Mapped[int | None] = mapped_column(ForeignKey("agendamentos.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String(12))  # sinal | servico | pacote | adesivo | outro
    descricao: Mapped[str] = mapped_column(String(160), default="")
    valor: Mapped[int] = mapped_column(Integer)
    forma: Mapped[str] = mapped_column(String(10), default="pix")
    pago_em: Mapped[datetime] = mapped_column(DateTime, default=agora_loja, index=True)

    cliente: Mapped[Cliente] = relationship()
    agendamento: Mapped[Agendamento | None] = relationship(back_populates="pagamentos")
