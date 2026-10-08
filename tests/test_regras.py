from datetime import date, datetime, time

from app.regras import (
    Expediente,
    brl,
    calcular_sinal,
    frequencia,
    horarios_livres,
    ler_valor,
    link_whatsapp,
    progresso_promocao,
    semanas_do_mes,
    so_digitos,
)

EXP = Expediente(
    dias={2, 3, 4, 5, 6},
    abre=time(9),
    fecha=time(19),
    pausas=[(time(11), time(12)), (time(15), time(15, 15))],
    passo_min=30,
    antecedencia_h=2,
)
TERCA = date(2026, 10, 20)
ANTES = datetime(2026, 10, 1, 8)


def hhmm(lista):
    return [d.strftime("%H:%M") for d in lista]


def test_duas_horas_respeita_almoco_cafe_e_fechamento():
    livres = hhmm(horarios_livres(TERCA, 120, EXP, [], ANTES))
    assert "09:00" in livres and "10:30" not in livres  # 10:30-12:30 cruza o almoço
    assert "12:00" in livres and "13:00" in livres
    assert "13:30" not in livres  # 13:30-15:30 cruza o café
    assert "15:30" in livres and "17:00" in livres and "17:30" not in livres


def test_meia_hora_cabe_antes_do_almoco():
    assert "10:30" in hhmm(horarios_livres(TERCA, 30, EXP, [], ANTES))


def test_ocupado_e_dia_fechado():
    ocupado = [(datetime(2026, 10, 20, 9), datetime(2026, 10, 20, 11))]
    livres = hhmm(horarios_livres(TERCA, 60, EXP, ocupado, ANTES))
    assert "09:00" not in livres and "10:00" not in livres and "12:00" in livres
    assert horarios_livres(date(2026, 10, 19), 60, EXP, [], ANTES) == []  # segunda


def test_antecedencia_minima():
    agora = datetime(2026, 10, 20, 12, 10)
    livres = hhmm(horarios_livres(TERCA, 60, EXP, [], agora))
    assert "14:00" not in livres and "15:30" in livres


def test_sinal():
    assert calcular_sinal(6000, 50, False) == 3000
    assert calcular_sinal(4001, 50, False) == 2001
    assert calcular_sinal(16000, 50, True) == 16000


def test_valores_e_whatsapp():
    assert ler_valor("12,50") == 1250 and ler_valor("80") == 8000 and ler_valor("x") is None
    assert brl(123456) == "R$ 1.234,56"
    assert so_digitos("+55 (12) 98222-7847") == "12982227847"
    assert link_whatsapp("12982227847", "oi tudo") == "https://wa.me/5512982227847?text=oi%20tudo"


def test_promocao_reinicia_depois_da_cortesia():
    idas = [(datetime(2026, 1, i), False) for i in range(1, 11)]
    assert progresso_promocao(idas, 10).ganhou
    idas += [(datetime(2026, 2, 1), True), (datetime(2026, 2, 10), False)]
    p = progresso_promocao(idas, 10)
    assert (p.feitas, p.faltam, p.ganhou) == (1, 9, False)


def test_frequencia_e_sumida():
    datas = [date(2026, 6, 1), date(2026, 6, 21), date(2026, 7, 11)]
    f = frequencia(datas, date(2026, 10, 6))
    assert f.intervalo_medio == 20 and f.sumida
    assert not frequencia(datas, date(2026, 7, 20)).sumida


def test_calendario_comeca_no_domingo():
    semanas = semanas_do_mes(2026, 10)
    assert semanas[0][:4] == [None, None, None, None] and semanas[0][4] == date(2026, 10, 1)


def test_pe_as_9_bloqueia_pe_e_mao_na_manha():
    """Pé 9h-10h marcado: Pé + Mão (2h) não cabe mais de manhã (manhã vai até 11h)."""
    pe = [(datetime(2026, 10, 20, 9), datetime(2026, 10, 20, 10))]
    pe_e_mao = hhmm(horarios_livres(TERCA, 120, EXP, pe, ANTES))
    assert not [h for h in pe_e_mao if h < "12:00"]
    assert pe_e_mao[0] == "12:00"
    # Mas um serviço de 1h ainda cabe às 10h, e um de 30 min às 10h30.
    assert "10:00" in hhmm(horarios_livres(TERCA, 60, EXP, pe, ANTES))
    assert "10:30" in hhmm(horarios_livres(TERCA, 30, EXP, pe, ANTES))


def test_ultimo_inicio_opcional_por_servico():
    livres = hhmm(horarios_livres(TERCA, 60, EXP, [], ANTES, time(14)))
    assert livres[-1] == "14:00"


def test_pe_e_mao_as_9_fecha_a_manha():
    """Pé + Mão 9h-11h: nada mais de manhã, nem esmaltação de 30 min."""
    ocupado = [(datetime(2026, 10, 20, 9), datetime(2026, 10, 20, 11))]
    for duracao in (30, 60, 120):
        livres = hhmm(horarios_livres(TERCA, duracao, EXP, ocupado, ANTES))
        assert not [h for h in livres if h < "12:00"], duracao
        assert livres[0] == "12:00"
