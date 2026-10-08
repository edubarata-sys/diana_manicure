from datetime import timedelta

from sqlalchemy import select

from app import models as m
from app import servicos as sv
from app.regras import agora_loja


def _proximo_livre(fabrica, nome="Pé + Mão"):
    with fabrica() as db:
        s = db.scalar(select(m.Servico).where(m.Servico.nome == nome))
        d = agora_loja().date()
        for _ in range(30):
            d += timedelta(days=1)
            livres = sv.livres(db, d, s)
            if livres:
                return s.id, livres[0]
    raise AssertionError("sem horário livre")


def test_home_mostra_tabela_do_layout(cliente_http):
    r = cliente_http.get("/")
    assert r.status_code == 200
    for texto in ("Tolerância de 10 minutos", "Pé + Mão", "R$ 60,00", "Spa dos Pés + Esmaltação", "R$ 100,00", "Adesivos", "20/10"):
        assert texto in r.text


def test_cliente_agenda_sem_cadastro_e_diana_confirma(fabrica, cliente_http, painel):
    servico_id, inicio = _proximo_livre(fabrica)
    pagina = cliente_http.get(f"/agendar?servico={servico_id}&dia={inicio.date().isoformat()}")
    assert inicio.strftime("%H:%M") in pagina.text

    r = cliente_http.post(
        "/agendar/confirmar",
        data={"servico": servico_id, "inicio": inicio.isoformat(timespec="minutes"),
              "nome": "Maria da Silva", "whatsapp": "(12) 99999-9999", "aceite": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"].startswith("/reserva/")
    reserva = cliente_http.get(r.headers["location"])
    assert "12982227847" in reserva.text and "R$ 30,00" in reserva.text
    assert "Tolerância de 10 minutos de atraso" in reserva.text

    # O mesmo horário some para a próxima cliente.
    dup = cliente_http.post(
        "/agendar/confirmar",
        data={"servico": servico_id, "inicio": inicio.isoformat(timespec="minutes"),
              "nome": "Outra", "whatsapp": "12988887777", "aceite": "1"},
        follow_redirects=False,
    )
    assert "/agendar?" in dup.headers["location"]

    with fabrica() as db:
        ag = db.scalar(select(m.Agendamento))
        assert ag.status == m.AGUARDANDO_SINAL and ag.sinal == 3000
        ag_id = ag.id

    painel.post(f"/painel/ag/{ag_id}/sinal", data={"forma": "pix"})
    painel.post(f"/painel/ag/{ag_id}/concluir", data={"valor": "30,00", "forma": "dinheiro", "adesivos": "2"})

    with fabrica() as db:
        ag = db.get(m.Agendamento, ag_id)
        assert ag.status == m.CONCLUIDO
        valores = sorted(p.valor for p in db.scalars(select(m.Pagamento)))
        assert valores == [700, 3000, 3000]

    fin = painel.get("/painel/financeiro?mes=" + inicio.strftime("%Y-%m"))
    assert "Maria da Silva" in fin.text and "R$ 67,00" in fin.text


def test_sem_aceite_nao_agenda(fabrica, cliente_http):
    servico_id, inicio = _proximo_livre(fabrica)
    r = cliente_http.post(
        "/agendar/confirmar",
        data={"servico": servico_id, "inicio": inicio.isoformat(timespec="minutes"),
              "nome": "Ana", "whatsapp": "12999990000"},
        follow_redirects=False,
    )
    assert "/agendar/confirmar" in r.headers["location"]
    with fabrica() as db:
        assert db.scalar(select(m.Agendamento)) is None


def test_reserva_sem_sinal_expira_e_libera_horario(fabrica, cliente_http):
    servico_id, inicio = _proximo_livre(fabrica)
    cliente_http.post(
        "/agendar/confirmar",
        data={"servico": servico_id, "inicio": inicio.isoformat(timespec="minutes"),
              "nome": "Bia", "whatsapp": "12999991111", "aceite": "1"},
    )
    with fabrica() as db:
        ag = db.scalar(select(m.Agendamento))
        ag.criado_em = agora_loja() - timedelta(hours=13)
        db.commit()
        sv.expirar_sinais(db)
        s = db.get(m.Servico, servico_id)
        assert db.get(m.Agendamento, ag.id).status == m.EXPIRADO
        assert inicio in sv.livres(db, inicio.date(), s)


def test_area_da_cliente_mostra_historico_e_promocao(fabrica, cliente_http):
    servico_id, inicio = _proximo_livre(fabrica, "Só Esmaltação")
    cliente_http.post(
        "/agendar/confirmar",
        data={"servico": servico_id, "inicio": inicio.isoformat(timespec="minutes"),
              "nome": "Carla Souza", "whatsapp": "12977776666", "aceite": "1"},
    )
    r = cliente_http.post(
        "/minha-area/cadastrar",
        data={"nome": "Carla Souza", "whatsapp": "12977776666", "senha": "segredo1"},
        follow_redirects=True,
    )
    assert "Olá, Carla" in r.text and "Só Esmaltação" in r.text and "0 de 10" in r.text
    # Não deixa outra pessoa cadastrar senha de novo no mesmo número.
    r2 = cliente_http.post(
        "/minha-area/cadastrar",
        data={"nome": "X", "whatsapp": "12977776666", "senha": "outrasenha"},
        follow_redirects=True,
    )
    assert "já tem cadastro" in r2.text


def test_painel_exige_senha(cliente_http):
    r = cliente_http.get("/painel", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/painel/entrar"
    r = cliente_http.post("/painel/entrar", data={"senha": "errada"}, follow_redirects=True)
    assert "Senha incorreta" in r.text


def test_pacote_pago_antes_e_usado_depois(fabrica, cliente_http, painel):
    pac_id, inicio = _proximo_livre(fabrica, "Pacote mensal")
    cliente_http.post(
        "/agendar/confirmar",
        data={"servico": pac_id, "inicio": inicio.isoformat(timespec="minutes"),
              "nome": "Dani", "whatsapp": "12966665555", "aceite": "1"},
    )
    with fabrica() as db:
        ag = db.scalar(select(m.Agendamento))
        assert ag.sinal == 16000
        ag_id = ag.id
    painel.post(f"/painel/ag/{ag_id}/sinal", data={"forma": "pix"})
    painel.post(f"/painel/ag/{ag_id}/concluir", data={"valor": "0", "forma": "pix", "uso_pacote": "mao"})
    with fabrica() as db:
        pac = db.scalar(select(m.Pacote))
        assert (pac.maos_usadas, pac.restantes) == (1, 5)
        cliente = db.get(m.Agendamento, ag_id).cliente
        mao = db.scalar(select(m.Servico).where(m.Servico.nome == "Só Mão"))
        d = inicio.date()
        for _ in range(30):
            d += timedelta(days=1)
            livres = sv.livres(db, d, mao)
            if livres:
                break
        novo = sv.criar_agendamento(db, cliente, mao, livres[0])
        assert novo.pacote_id == pac.id and novo.sinal == 0 and novo.status == m.CONFIRMADO


def test_clientes_sumidas_e_paginas_do_painel(fabrica, painel):
    for url in ("/painel", "/painel/novo", "/painel/clientes", "/painel/clientes?filtro=sumidas",
                "/painel/financeiro", "/painel/config"):
        assert painel.get(url).status_code == 200, url
    r = painel.post("/painel/clientes", data={"nome": "Elisa", "whatsapp": "12955554444"}, follow_redirects=True)
    assert "Elisa" in r.text


def test_config_salva_horario(painel, fabrica):
    painel.post("/painel/config", data={"abre": "10:00", "fecha": "18:00", "pausas": "12:00-13:00",
                                          "dias": ["3", "4"], "promo_idas": "8"})
    with fabrica() as db:
        c = sv.config(db)
        assert (c.abre, c.fecha, c.dias_atendimento, c.promo_idas) == ("10:00", "18:00", "3,4", 8)


def test_despesa_entra_no_lucro_do_mes(painel, fabrica):
    from app.regras import agora_loja as agora
    hoje = agora().date().isoformat()
    painel.post("/painel/financeiro/lancar", data={"cliente_id": "0", "valor": "10"})  # sem cliente: recusado
    r = painel.post("/painel/clientes", data={"nome": "Fê", "whatsapp": "12944443333"}, follow_redirects=False)
    cid = r.headers["location"].rsplit("/", 1)[1]
    painel.post("/painel/financeiro/lancar", data={"cliente_id": cid, "valor": "100,00", "forma": "pix", "data": hoje})
    painel.post("/painel/financeiro/despesa", data={"descricao": "Esmaltes", "categoria": "produtos", "valor": "35,50", "data": hoje})
    fin = painel.get("/painel/financeiro")
    assert "R$ 100,00" in fin.text and "R$ 35,50" in fin.text and "R$ 64,50" in fin.text
    with fabrica() as db:
        did = db.scalar(select(m.Despesa.id))
    painel.post(f"/painel/financeiro/despesa/{did}/apagar")
    assert "Nenhuma despesa lançada" in painel.get("/painel/financeiro").text


def test_banco_antigo_ganha_colunas_novas_sem_perder_dados():
    from sqlalchemy import create_engine, inspect as insp, text as sqltext
    from app.main import atualizar_colunas
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(sqltext("CREATE TABLE servicos (id INTEGER PRIMARY KEY, nome VARCHAR(80))"))
        c.execute(sqltext("INSERT INTO servicos (nome) VALUES ('Pé + Mão')"))
    assert atualizar_colunas(eng) == ["servicos.ultimo_inicio"]
    assert "ultimo_inicio" in {col["name"] for col in insp(eng).get_columns("servicos")}
    with eng.connect() as c:
        assert c.execute(sqltext("SELECT nome, ultimo_inicio FROM servicos")).one() == ("Pé + Mão", "")
    assert atualizar_colunas(eng) == []
