"""
Regras de horário — a única fonte de verdade do sistema.

Regras do documento do cliente:
  • funciona das 08:00 às 18:00, de 30 em 30 minutos (último horário 17:30)
  • almoço das 11:00 às 13:00 nunca aparece como disponível
  • serviço de 60 min ocupa dois horários seguidos
  • antecedência mínima (padrão 1 h) e janela máxima (padrão 30 dias)
  • ninguém consegue dois agendamentos no mesmo horário
"""

from datetime import date, datetime, timedelta

from database import agora, config_global

DIAS_CURTOS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
DIAS_LONGOS = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

STATUS_VALIDOS = ["agendado", "confirmado", "concluido", "cancelado", "faltou"]
STATUS_ROTULO = {
    "agendado": "Agendado",
    "confirmado": "Confirmado",
    "concluido": "Concluído",
    "cancelado": "Cancelado",
    "faltou": "Faltou",
}


# ----------------------------------------------------------------- conversão
def hhmm_para_min(texto):
    """'08:30' -> 510"""
    if not texto:
        return None
    h, m = texto.strip().split(":")[:2]
    return int(h) * 60 + int(m)


def min_para_hhmm(minutos):
    """510 -> '08:30'"""
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def data_iso(valor):
    """date ou 'AAAA-MM-DD' -> 'AAAA-MM-DD'"""
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def data_br(iso):
    """'2026-11-20' -> '20/11/2026'"""
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    return d.strftime("%d/%m/%Y")


def data_longa(iso):
    """'2026-11-20' -> 'sexta-feira, 20 de novembro'"""
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    return f"{DIAS_LONGOS[d.weekday()]}, {d.day} de {MESES[d.month - 1]}"


def moeda(centavos):
    """6500 -> 'R$ 65,00'"""
    valor = (centavos or 0) / 100
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def whatsapp_formatado(numero):
    """'5573998553599' -> '(73) 99855-3599'"""
    n = "".join(c for c in (numero or "") if c.isdigit())
    if len(n) == 13 and n.startswith("55"):
        return f"({n[2:4]}) {n[4:9]}-{n[9:]}"
    if len(n) == 11:
        return f"({n[0:2]}) {n[2:7]}-{n[7:]}"
    return n or "[A CONFIRMAR]"


# ----------------------------------------------------------------- configuração
def config_do_dia(con, dia_semana):
    linha = con.execute(
        "SELECT * FROM configuracoes WHERE dia_semana = ?", (dia_semana,)
    ).fetchone()
    if not linha:
        return {
            "dia_semana": dia_semana,
            "aberto": 0,
            "abre": "08:00",
            "fecha": "18:00",
            "almoco_inicio": "11:00",
            "almoco_fim": "13:00",
        }
    return dict(linha)


def globais(con):
    return {
        "intervalo": int(config_global(con, "intervalo_min", "30") or 30),
        "antecedencia": int(config_global(con, "antecedencia_min", "60") or 60),
        "janela": int(config_global(con, "janela_dias", "30") or 30),
    }


def eh_hoje(iso):
    return iso == agora().date().isoformat()


def dentro_da_janela(iso):
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    hoje = agora().date()
    return 0 <= (d - hoje).days


def gerar_dias(con, janela_dias=None):
    """Próximos N dias (incluindo hoje) com a informação se o dia abre."""
    g = globais(con)
    janela = janela_dias or g["janela"]
    hoje = agora().date()
    dias = []
    for i in range(janela):
        d = hoje + timedelta(days=i)
        cfg = config_do_dia(con, d.weekday())
        dias.append(
            {
                "iso": d.isoformat(),
                "dia": d.day,
                "mes": MESES[d.month - 1][:3],
                "dia_semana_curto": DIAS_CURTOS[d.weekday()],
                "dia_semana": d.weekday(),
                "aberto": bool(cfg["aberto"]),
                "hoje": i == 0,
            }
        )
    return dias


# ----------------------------------------------------------------- conflitos
def agendamentos_do_dia(con, iso, ignorar_id=None):
    sql = (
        "SELECT a.*, s.nome AS servico_nome, s.duracao_min "
        "FROM agendamentos a JOIN servicos s ON s.id = a.servico_id "
        "WHERE a.data = ? AND a.status <> 'cancelado'"
    )
    parametros = [iso]
    if ignorar_id:
        sql += " AND a.id <> ?"
        parametros.append(ignorar_id)
    return [dict(l) for l in con.execute(sql, parametros).fetchall()]


def bloqueios_do_dia(con, iso):
    return [
        dict(l)
        for l in con.execute("SELECT * FROM bloqueios WHERE data = ?", (iso,)).fetchall()
    ]


def _intervalos_ocupados(con, iso, ignorar_id=None):
    """Lista de (inicio, fim) em minutos já usados no dia."""
    ocupados = []
    for a in agendamentos_do_dia(con, iso, ignorar_id):
        ocupados.append((hhmm_para_min(a["hora_inicio"]), hhmm_para_min(a["hora_fim"])))
    for b in bloqueios_do_dia(con, iso):
        ini = hhmm_para_min(b["hora_inicio"]) if b["hora_inicio"] else 0
        fim = hhmm_para_min(b["hora_fim"]) if b["hora_fim"] else 24 * 60
        ocupados.append((ini, fim))
    return ocupados


def _cruza(inicio, fim, intervalos):
    return any(inicio < f and fim > i for i, f in intervalos)


def duracoes_do_dia(con):
    linhas = con.execute(
        "SELECT DISTINCT duracao_min FROM servicos WHERE ativo = 1 ORDER BY duracao_min"
    ).fetchall()
    return [l["duracao_min"] for l in linhas] or [30]


def _slots_base(cfg, intervalo):
    abre = hhmm_para_min(cfg["abre"])
    fecha = hhmm_para_min(cfg["fecha"])
    almoco_ini = hhmm_para_min(cfg["almoco_inicio"])
    almoco_fim = hhmm_para_min(cfg["almoco_fim"])
    return abre, fecha, almoco_ini, almoco_fim


def horarios_do_dia(con, iso, duracao_min, ignorar_id=None):
    """
    Devolve a lista de horários do dia com o estado de cada um.
    estado: livre | ocupado | passou | bloqueado | nao_cabe
    """
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    cfg = config_do_dia(con, d.weekday())
    g = globais(con)

    if not cfg["aberto"]:
        return []

    abre, fecha, almoco_ini, almoco_fim = _slots_base(cfg, g["intervalo"])
    ocupados = _intervalos_ocupados(con, iso, ignorar_id)

    agora_min = None
    if iso == agora().date().isoformat():
        a = agora()
        agora_min = a.hour * 60 + a.minute

    limite_antecedencia = None
    if iso == agora().date().isoformat():
        limite_antecedencia = agora_min + g["antecedencia"]
    elif iso == (agora().date() + timedelta(days=1)).isoformat():
        # amanhã: respeita antecedência mínima contada a partir de agora
        limite_antecedencia = None

    lista = []
    minuto = abre
    while minuto + duracao_min <= fecha:
        inicio = minuto
        fim = minuto + duracao_min
        hora = min_para_hhmm(inicio)

        # cabe sem invadir o almoço? (o almoço nunca é exibido como livre)
        invade_almoco = inicio < almoco_fim and fim > almoco_ini
        cabe_no_dia = fim <= fecha

        if not cabe_no_dia or invade_almoco:
            estado = "nao_cabe"
        elif _cruza(inicio, fim, ocupados):
            # se cruza um bloqueio de dia inteiro ou agendamento
            estado = "ocupado"
        elif iso == agora().date().isoformat() and inicio < limite_antecedencia:
            estado = "passou"
        else:
            estado = "livre"

        lista.append(
            {
                "hora": hora,
                "inicio": inicio,
                "fim": fim,
                "estado": estado,
                "rotulo": hora,
            }
        )
        minuto += g["intervalo"]

    return lista


def grade_do_dia(con, iso, ignorar_id=None):
    """Grade fixa do dia (para o painel), usando o menor intervalo configurado."""
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    cfg = config_do_dia(con, d.weekday())
    g = globais(con)
    abre, fecha, almoco_ini, almoco_fim = _slots_base(cfg, g["intervalo"])

    if not cfg["aberto"]:
        return {"config": cfg, "faixas": [], "fechado": True}

    faixas = []
    minuto = abre
    while minuto + g["intervalo"] <= fecha:
        dentro_almoco = minuto >= almoco_ini and minuto < almoco_fim
        faixas.append(
            {"hora": min_para_hhmm(minuto), "inicio": minuto, "almoco": dentro_almoco}
        )
        minuto += g["intervalo"]

    return {"config": cfg, "faixas": faixas, "fechado": False}


def pode_agendar(con, iso, hora_inicio, duracao_min, ignorar_id=None):
    """
    Validação final no servidor. Devolve (ok, motivo).
    Nunca confiar apenas na tela.
    """
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False, "Data inválida."

    hoje = agora().date()
    if d < hoje:
        return False, "Essa data já passou."
    if (d - hoje).days >= globais(con)["janela"]:
        return False, "Data fora do período de agendamento."

    cfg = config_do_dia(con, d.weekday())
    if not cfg["aberto"]:
        return False, "A barbearia não abre nesse dia."

    inicio = hhmm_para_min(hora_inicio)
    fim = inicio + duracao_min
    abre = hhmm_para_min(cfg["abre"])
    fecha = hhmm_para_min(cfg["fecha"])
    almoco_ini = hhmm_para_min(cfg["almoco_inicio"])
    almoco_fim = hhmm_para_min(cfg["almoco_fim"])
    intervalo = globais(con)["intervalo"]

    if inicio < abre or inicio >= fecha or fim > fecha:
        return False, "Horário fora do funcionamento."
    if (inicio - abre) % intervalo != 0:
        return False, "Horário fora da grade de atendimento."
    if inicio < almoco_fim and fim > almoco_ini:
        return False, "Esse horário é o intervalo de almoço."

    if iso == hoje.isoformat():
        a = agora()
        if inicio < a.hour * 60 + a.minute + globais(con)["antecedencia"]:
            return False, "Escolha um horário com pelo menos 1 hora de antecedência."

    if _cruza(inicio, fim, _intervalos_ocupados(con, iso, ignorar_id)):
        return False, "Esse horário acabou de ser ocupado. Escolha outro."

    return True, ""


def resumo_semana(con, inicio_semana):
    """Receita e contagem dos 7 dias, para o painel."""
    total = 0
    contagem = 0
    for i in range(7):
        iso = (inicio_semana + timedelta(days=i)).isoformat()
        for a in agendamentos_do_dia(con, iso):
            if a["status"] in ("cancelado", "faltou"):
                continue
            total += a["preco_centavos"] or 0
            contagem += 1
    return {"total_centavos": total, "quantidade": contagem}