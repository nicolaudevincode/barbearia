"""
Banco de dados do sistema de agendamento.

Dois modos, escolhidos sozinho:
  • com POSTGRES_URL / DATABASE_URL no ambiente  -> PostgreSQL (Vercel / Neon)
  • sem a variável                              -> SQLite local (instance/barbearia.db)

Nada é instalado para você pelo próprio app; o banco PostgreSQL é criado no painel
da Vercel (Storage) e a URL vem como variável de ambiente.
"""

import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
DB_PATH = os.environ.get("BARBEARIA_DB") or os.path.join(INSTANCE_DIR, "barbearia.db")
PG_URL = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL") or ""

FUSO = timezone(timedelta(hours=-3))  # America/Sao_Paulo (sem horário de verão desde 2019)


def eh_postgres():
    return bool(PG_URL)


def agora():
    """Data/hora atual no fuso de Brasília."""
    return datetime.now(FUSO)


def agora_iso():
    return agora().strftime("%Y-%m-%d %H:%M:%S")


def transacao_imediata(con):
    """Abre a transação de escrita (SQLite usa BEGIN IMMEDIATE; no PostgreSQL é implícita)."""
    if eh_postgres():
        return
    con.execute("BEGIN IMMEDIATE")


def conectar():
    if eh_postgres():
        return _conectar_postgres()
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.isolation_level = None  # transações explícitas (BEGIN IMMEDIATE)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


class _CursorPg:
    def __init__(self, cursor, resultado):
        self._cursor = cursor
        self.resultado = resultado

    def fetchall(self):
        return [dict(r) for r in self._cursor.fetchall()]

    def fetchone(self):
        r = self._cursor.fetchone()
        return dict(r) if r else None

    @property
    def rowcount(self):
        return self._cursor.rowcount


class _ConexaoPg:
    """Emula o mínimo de interface do sqlite3 (execute/fetchall/fetchone/commit)."""

    def __init__(self, url):
        import psycopg
        from psycopg.rows import dict_row

        self._c = psycopg.connect(url, row_factory=dict_row)

    def execute(self, sql, parametros=()):
        sql_pg = sql.replace("?", "%s")
        cur = self._c.cursor()
        cur.execute(sql_pg, tuple(parametros))
        return _CursorPg(cur, cur.fetchall if False else None)

    def executescript(self, sql):
        for bloco in sql.split(";"):
            bloco = bloco.strip()
            if bloco:
                self._c.cursor().execute(bloco.replace("?", "%s"))

    def commit(self):
        self._c.commit()

    def rollback(self):
        self._c.rollback()

    def close(self):
        self._c.close()


def _conectar_postgres():
    return _ConexaoPg(PG_URL)


ESQUEMA = """
CREATE TABLE IF NOT EXISTS admins (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario     TEXT    NOT NULL UNIQUE,
    senha_hash  TEXT    NOT NULL,
    nome        TEXT    NOT NULL,
    criado_em   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS servicos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nome         TEXT    NOT NULL,
    descricao    TEXT    NOT NULL DEFAULT '',
    duracao_min  INTEGER NOT NULL DEFAULT 30,
    preco_centavos INTEGER NOT NULL DEFAULT 0,
    ativo        INTEGER NOT NULL DEFAULT 1,
    ordem        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agendamentos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo            TEXT    NOT NULL UNIQUE,
    servico_id        INTEGER NOT NULL REFERENCES servicos(id),
    data              TEXT    NOT NULL,              -- AAAA-MM-DD
    hora_inicio       TEXT    NOT NULL,              -- HH:MM
    hora_fim          TEXT    NOT NULL,              -- HH:MM
    cliente_nome      TEXT    NOT NULL,
    cliente_whatsapp  TEXT    NOT NULL,              -- só dígitos
    status            TEXT    NOT NULL DEFAULT 'agendado',
    observacao        TEXT    NOT NULL DEFAULT '',
    origem            TEXT    NOT NULL DEFAULT 'site',   -- site | manual
    preco_centavos    INTEGER NOT NULL DEFAULT 0,
    criado_em         TEXT    NOT NULL,
    atualizado_em     TEXT    NOT NULL
);

-- Um horário por data, exceto cancelados: impede reserva dupla no banco.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ag_data_hora
    ON agendamentos (data, hora_inicio)
    WHERE status <> 'cancelado';

CREATE INDEX IF NOT EXISTS ix_ag_data   ON agendamentos (data);
CREATE INDEX IF NOT EXISTS ix_ag_status ON agendamentos (status);
CREATE INDEX IF NOT EXISTS ix_ag_fone   ON agendamentos (cliente_whatsapp);

CREATE TABLE IF NOT EXISTS bloqueios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    data         TEXT NOT NULL,          -- AAAA-MM-DD
    hora_inicio  TEXT,                   -- NULL = dia inteiro
    hora_fim     TEXT,
    motivo       TEXT NOT NULL DEFAULT '',
    criado_em    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS configuracoes (
    dia_semana    INTEGER PRIMARY KEY,   -- 0=segunda ... 6=domingo
    aberto        INTEGER NOT NULL DEFAULT 1,
    abre          TEXT    NOT NULL DEFAULT '08:00',
    fecha         TEXT    NOT NULL DEFAULT '18:00',
    almoco_inicio TEXT    NOT NULL DEFAULT '11:00',
    almoco_fim    TEXT    NOT NULL DEFAULT '13:00'
);

CREATE TABLE IF NOT EXISTS globais (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id    INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
    endpoint    TEXT    NOT NULL UNIQUE,
    chaves      TEXT    NOT NULL,        -- JSON {p256dh, auth}
    dispositivo TEXT    NOT NULL DEFAULT '',
    criado_em   TEXT    NOT NULL
);

-- Controle simples de abuso (login e agendamento)
CREATE TABLE IF NOT EXISTS tentativas (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    chave   TEXT NOT NULL,
    tipo    TEXT NOT NULL,
    quando  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tentativas ON tentativas (chave, tipo, quando);
"""


GLOBAIS_PADRAO = {
    "marca": "Gabriel do Corte",
    "assinatura": "Azevedo Barbeiro",
    "slogan": "Precisão em cada detalhe.",
    "whatsapp": "5573998553599",
    "instagram": "gbr_barbeiro73",
    "endereco": "[A CONFIRMAR]",
    "cidade": "[A CONFIRMAR]",
    "intervalo_min": "30",
    "antecedencia_min": "60",
    "janela_dias": "30",
    "vapid_public": "",
    "vapid_private": "",
}

SERVICOS_PADRAO = [
    # TROCAR: valores de exemplo. O barbeiro edita em /admin/configuracoes.
    ("Corte masculino", "Máquina, tesoura e acabamento na navalha.", 30, 4000, 1),
    ("Barba", "Toalha quente, navalha e finalização.", 30, 3000, 2),
    ("Corte + barba", "O combo completo, com tempo de sobra.", 60, 6500, 3),
    ("Sobrancelha", "Design no alinhamento do rosto.", 30, 1500, 4),
]


def config_global(con, chave, padrao=""):
    linha = con.execute("SELECT valor FROM globais WHERE chave = ?", (chave,)).fetchone()
    return linha["valor"] if linha else padrao


def salvar_global(con, chave, valor):
    con.execute(
        "INSERT INTO globais (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (chave, str(valor)),
    )


def gerar_senha(tamanho=10):
    """Senha legível (sem caracteres que se confundem)."""
    alfabeto = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(tamanho))


def criar_admin_inicial(con):
    """Cria o usuário do barbeiro. Usa ADMIN_USUARIO/ADMIN_SENHA do ambiente."""
    existe = con.execute("SELECT COUNT(*) AS n FROM admins").fetchone()["n"]
    if existe:
        return None

    usuario = (os.environ.get("ADMIN_USUARIO") or "gabriel").strip()
    senha = (os.environ.get("ADMIN_SENHA") or "").strip()
    gerada = False
    if not senha:
        senha = gerar_senha(10)
        gerada = True

    con.execute(
        "INSERT INTO admins (usuario, senha_hash, nome, criado_em) VALUES (?, ?, ?, ?)",
        (usuario, generate_password_hash(senha), "Gabriel Azevedo", agora_iso()),
    )

    if gerada:
        caminho = os.path.join(INSTANCE_DIR, "PRIMEIRO-ACESSO.txt")
        try:
            os.makedirs(INSTANCE_DIR, exist_ok=True)
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(
                    "ACESSO INICIAL AO PAINEL\n"
                    "========================\n\n"
                    f"Endereço : /login\n"
                    f"Usuário  : {usuario}\n"
                    f"Senha    : {senha}\n\n"
                    "Troque a senha em Configurações > Senha, na primeira vez que entrar.\n"
                    "Este arquivo é local e não vai para o GitHub.\n"
                )
        except OSError:
            # Vercel/servidor sem disco gravável: a senha fica nos logs
            print("\n" + "=" * 58)
            print(f" PRIMEIRO ACESSO  usuario={usuario}  senha={senha}")
            print("=" * 58 + "\n")
        print("\n" + "=" * 58)
        print(" PRIMEIRO ACESSO AO PAINEL")
        print(f"   usuário: {usuario}")
        print(f"   senha  : {senha}")
        print("   (também salvo em instance/PRIMEIRO-ACESSO.txt)")
        print("=" * 58 + "\n")
    return {"usuario": usuario, "senha": senha if gerada else None}


def iniciar():
    """Cria o banco, as tabelas, a configuração padrão e o primeiro admin."""
    con = conectar()
    try:
        esquema = ESQUEMA.replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
        ) if eh_postgres() else ESQUEMA
        con.executescript(esquema)

        for chave, valor in GLOBAIS_PADRAO.items():
            if eh_postgres():
                con.execute(
                    "INSERT INTO globais (chave, valor) VALUES (?, ?) "
                    "ON CONFLICT (chave) DO NOTHING",
                    (chave, valor),
                )
            else:
                con.execute(
                    "INSERT OR IGNORE INTO globais (chave, valor) VALUES (?, ?)",
                    (chave, valor),
                )

        for dia in range(7):
            if eh_postgres():
                con.execute(
                    "INSERT INTO configuracoes "
                    "(dia_semana, aberto, abre, fecha, almoco_inicio, almoco_fim) "
                    "VALUES (?, ?, '08:00', '18:00', '11:00', '13:00') "
                    "ON CONFLICT (dia_semana) DO NOTHING",
                    (dia, 0 if dia == 6 else 1),  # domingo fechado
                )
            else:
                con.execute(
                    "INSERT OR IGNORE INTO configuracoes "
                    "(dia_semana, aberto, abre, fecha, almoco_inicio, almoco_fim) "
                    "VALUES (?, ?, '08:00', '18:00', '11:00', '13:00')",
                    (dia, 0 if dia == 6 else 1),  # domingo fechado
                )

        if con.execute("SELECT COUNT(*) AS n FROM servicos").fetchone()["n"] == 0:
            for nome, desc, dur, preco, ordem in SERVICOS_PADRAO:
                con.execute(
                    "INSERT INTO servicos (nome, descricao, duracao_min, preco_centavos, ativo, ordem) "
                    "VALUES (?, ?, ?, ?, 1, ?)",
                    (nome, desc, dur, preco, ordem),
                )

        criar_admin_inicial(con)
        con.commit()
    finally:
        con.close()