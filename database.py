"""
Banco de dados do sistema de agendamento (SQLite).

Tudo é criado automaticamente na primeira execução. Nada de instalação manual.
O arquivo do banco fica em  instance/barbearia.db  e NÃO vai para o GitHub.
"""

import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
DB_PATH = os.environ.get("BARBEARIA_DB") or os.path.join(INSTANCE_DIR, "barbearia.db")

FUSO = timezone(timedelta(hours=-3))  # America/Sao_Paulo (sem horário de verão desde 2019)


def agora():
    """Data/hora atual no fuso de Brasília."""
    return datetime.now(FUSO)


def agora_iso():
    return agora().strftime("%Y-%m-%d %H:%M:%S")


def conectar():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.isolation_level = None  # transações explícitas (BEGIN IMMEDIATE)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


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
        con.executescript(ESQUEMA)

        for chave, valor in GLOBAIS_PADRAO.items():
            con.execute(
                "INSERT OR IGNORE INTO globais (chave, valor) VALUES (?, ?)", (chave, valor)
            )

        for dia in range(7):
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