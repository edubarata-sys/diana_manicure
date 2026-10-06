# Agenda Diana Ferraz — Manicure & Pedicure

Site de agendamento (cliente) + painel da Diana. FastAPI + Postgres, feito para o Railway.

## O que tem
- **Site da cliente** (`/`): tabela de serviços → dia e horário livre → confirma com nome e WhatsApp → tela do Pix com a chave, valor do sinal e botão "Enviar comprovante no WhatsApp". Agendar **não exige cadastro**.
- Horários calculados pela duração do serviço, respeitando dias de atendimento, abertura/fechamento, pausas (almoço/café) e outros agendamentos. Reserva sem sinal expira sozinha (padrão 12h).
- **Minha área** (`/minha-area`, opcional): cliente cria senha com o WhatsApp dela e vê histórico, pacote e a promoção (padrão: 10 idas = 1 grátis).
- **Painel da Diana** (`/painel`, senha `ADMIN_SENHA`):
  - Agenda do dia: sinal recebido, concluir (valor recebido, forma, adesivos, uso do pacote, cortesia da promoção), faltou, cancelar, lembrete pronto no WhatsApp.
  - Agendar para uma cliente (pode encaixar fora da grade, nunca em cima de outro horário).
  - Clientes: cadastro interno, frequência (visitas, ritmo, dias sem vir, "sumidas") e mensagens prontas (saudade, promoção).
  - Financeiro do mês com nome da cliente (por cliente, por forma, lançamentos, recebimento avulso).
  - Ajustes: dias/horários, pausas, sinal %, expiração, promoção, Pix, contato e tabela de serviços.
- Mensagens do WhatsApp saem **prontas** (link wa.me); a Diana só toca em enviar. Envio 100% automático exigiria a API paga do WhatsApp.

## Regras implementadas
- Sinal de 50% (configurável); pacote mensal é pago inteiro antes e vira saldo de 4 mãos + 2 pés.
- Cliente com pacote que agenda "Só Mão"/"Só Pé" usa o pacote (sem sinal). Falta no pacote = atendimento perdido.
- Falta: o sinal fica. Adesivos (R$ 3,50 o par) são lançados na conclusão, não no agendamento.

## Rodar local
```bash
pip install -r requirements-dev.txt
ADMIN_SENHA=teste uvicorn app.main:app --reload     # SQLite em agenda.db
python -m pytest -q
```

## Publicar no Railway
1. Suba esta pasta para um repositório no GitHub (ex.: `agenda-diana`).
2. Railway → **New Project** (separado da adega) → **Deploy from GitHub repo** → escolha o repositório.
3. No mesmo projeto: **+ New → Database → PostgreSQL**.
4. No serviço do app, aba **Variables**:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
   - `ADMIN_SENHA` = senha do painel da Diana
   - `SECRET_KEY` = texto longo aleatório
   - `HTTPS_ONLY` = `1`
5. **Settings → Networking → Generate Domain** (ou domínio próprio, ex.: agendadianaferraz.com.br).
As tabelas e a tabela de serviços são criadas sozinhas na primeira subida. O start vem do `Procfile`.
