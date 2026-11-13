"""
Gabriel do Corte — sistema de agendamento da barbearia.
Feito em Python (Flask) + SQLite, seguindo o documento do cliente.

Rodar no computador:   py app.py      ->  http://localhost:8000
Publicar:              ver docs/COMO-PUBLICAR.md
"""

import os
import secrets
import json
from datetime import datetime, timedelta

from flask import (
    Flask, abort, flash, g, jsonify, redirect, render_template, request,
    send_from_directory, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import push
import rules
from database import (
    BASE_DIR, INSTANCE_DIR, agora, agora_iso, conectar, config_global,
    iniciar as iniciar_banco, salvar_global,
)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)


# ------------------------------------------------------------------ infraestrutura
def _segredo():
    """Chave de sessão estável (não muda a cada reinício)."""
    caminho = os.path.join(INSTANCE_DIR, "SECRET_KEY.txt")
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            return f.read().strip()
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    chave = secrets.token_urlsafe(48)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(chave)
    return chave


app.secret_key = os.environ.get("SECRET_KEY") or _segredo()


def db():
    if "db" not in g:
        g.db = conectar()
    return g.db


@app.teardown_appcontext
def _fechar_db(excecao=None):
    conexao = g.pop("db", None)
    if conexao is not None:
        conexao.close()


@app.context_processor
def _globais_template():
    con = db()
    dados = {
        "marca": config_global(con, "marca", "Gabriel do Corte"),
        "assinatura": config_global(con, "assinatura", "Azevedo Barbeiro"),
        "slogan": config_global(con, "slogan", "Precisão em cada detalhe."),
        "whatsapp": config_global(con, "whatsapp", ""),
        "instagram": config_global(con, "instagram", ""),
        "endereco": config_global(con, "endereco", ""),
        "cidade": config_global(con, "cidade", ""),
        "whatsapp_link": "https://wa.me/" + config_global(con, "whatsapp", ""),
        "whatsapp_bonito": rules.whatsapp_formatado(config_global(con, "whatsapp", "")),
        "csrf_token": _csrf(),
        "ano": agora().year,
        "status_rotulo": rules.STATUS_ROTULO,
        "admin_logado": bool(session.get("admin_id")),
    }
    return dados


def _csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


app.jinja_env.globals.update(
    moeda=rules.moeda,
    data_br=rules.data_br,
    data_longa=rules.data_longa,
    hhmm=rules.hhmm_para_min,
    min_hhmm=rules.min_para_hhmm,
    whatsapp_formatado=rules.whatsapp_formatado,
    DIAS_CURTOS=rules.DIAS_CURTOS,
    DIAS_LONGOS=rules.DIAS_LONGOS,
)


@app.before_request
def _protecoes():
    # CSRF nos formulários (as rotas /api usam JSON e checam a origem)
    if request.method == "POST" and not request.path.startswith("/api/"):
        token = session.get("csrf")
        enviado = request.form.get("csrf") or request.headers.get("X-CSRF", "")
        if not token or not secrets.compare_digest(token, enviado):
            abort(400, description="Sessão expirada. Recarregue a página e tente de novo.")

    if request.method == "POST":
        origem = request.headers.get("Origin")
        if origem and origem.rstrip("/") != request.host_url.rstrip("/"):
            abort(403)


def admin_necessario():
    return session.get("admin_id")


def exigir_login():
    if not admin_necessario():
        return redirect(url_for("login", proximo=request.path))
    return None


def _ip():
    encaminhado = request.headers.get("X-Forwarded-For", "")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.remote_addr or "?"


def _limite_ok(con, chave, tipo, maximo, minutos):
    """Controle simples de abuso: no máximo N tentativas em X minutos."""
    limite = (agora() - timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M:%S")
    total = con.execute(
        "SELECT COUNT(*) AS n FROM tentativas WHERE chave = ? AND tipo = ? AND quando >= ?",
        (chave, tipo, limite),
    ).fetchone()["n"]
    return total < maximo


def _registrar_tentativa(con, chave, tipo):
    con.execute(
        "INSERT INTO tentativas (chave, tipo, quando) VALUES (?, ?, ?)",
        (chave, tipo, agora_iso()),
    )
    con.commit()


def _codigo_agendamento(con):
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(20):
        codigo = "".join(secrets.choice(alfabeto) for _ in range(6))
        existe = con.execute(
            "SELECT 1 FROM agendamentos WHERE codigo = ?", (codigo,)
        ).fetchone()
        if not existe:
            return codigo
    return secrets.token_hex(4).upper()


def _normalizar_whatsapp(bruto):
    digitos = "".join(c for c in (bruto or "") if c.isdigit())
    if digitos.startswith("55") and len(digitos) in (12, 13):
        return digitos
    if len(digitos) == 11:  # DDD + 9 dígitos
        return "55" + digitos
    if len(digitos) == 10:  # DDD + 8 dígitos (número antigo)
        return "55" + digitos
    return None


def _criar_agendamento(con, servico, iso, hora, nome, whatsapp, origem="site", observacao=""):
    """Insere o agendamento com segurança (sem reserva dupla)."""
    ok, motivo = rules.pode_agendar(con, iso, hora, servico["duracao_min"])
    if not ok:
        return None, motivo

    inicio = rules.hhmm_para_min(hora)
    codigo = _codigo_agendamento(con)
    agora_str = agora_iso()

    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            "INSERT INTO agendamentos (codigo, servico_id, data, hora_inicio, hora_fim, "
            "cliente_nome, cliente_whatsapp, status, observacao, origem, preco_centavos, "
            "criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,'agendado',?,?,?,?,?)",
            (
                codigo, servico["id"], iso, hora,
                rules.min_para_hhmm(inicio + servico["duracao_min"]),
                nome, whatsapp, observacao, origem, servico["preco_centavos"],
                agora_str, agora_str,
            ),
        )
        con.commit()
    except Exception:
        con.rollback()
        return None, "Esse horário acabou de ser ocupado. Escolha outro."

    return {
        "codigo": codigo,
        "servico": servico["nome"],
        "data": iso,
        "hora": hora,
        "nome": nome,
    }, ""


def _avisar_novo_agendamento(con, ag):
    texto = f"{ag['nome']} | {ag['servico']} | {rules.data_br(ag['data'])} às {ag['hora']}"
    try:
        push.enviar_para_todos(con, "Novo agendamento", texto, "/admin")
    except Exception as erro:  # notificação nunca deve quebrar o agendamento
        app.logger.warning("Falha ao notificar: %s", erro)


# ------------------------------------------------------------------ área pública
@app.get("/")
def inicio():
    con = db()
    servicos = con.execute(
        "SELECT * FROM servicos WHERE ativo = 1 ORDER BY ordem, id"
    ).fetchall()
    dias = rules.gerar_dias(con)
    semana = [rules.config_do_dia(con, d) for d in range(7)]
    duracao_max = max([s["duracao_min"] for s in servicos] or [30])
    dados = {
        "servicos": [
            {
                "id": s["id"],
                "nome": s["nome"],
                "duracao": s["duracao_min"],
                "preco": rules.moeda(s["preco_centavos"]),
            }
            for s in servicos
        ],
        "dias": dias,
        "whatsapp": config_global(con, "whatsapp", ""),
        "marca": config_global(con, "marca", ""),
    }
    return render_template(
        "index.html",
        servicos=servicos,
        dias=dias,
        semana=semana,
        duracao_max=duracao_max,
        dados=dados,
        inst_globais=rules.globais(con),
    )


@app.get("/api/horarios")
def api_horarios():
    con = db()
    iso = request.args.get("data", "")
    servico_id = request.args.get("servico_id", type=int)
    try:
        datetime.strptime(iso, "%Y-%m-%d")
    except (TypeError, ValueError):
        return jsonify(ok=False, erro="Data inválida."), 400

    servico = con.execute(
        "SELECT * FROM servicos WHERE id = ? AND ativo = 1", (servico_id,)
    ).fetchone()
    if not servico:
        return jsonify(ok=False, erro="Serviço indisponível."), 400

    cfg = rules.config_do_dia(con, datetime.strptime(iso, "%Y-%m-%d").weekday())
    slots = rules.horarios_do_dia(con, iso, servico["duracao_min"])
    return jsonify(
        ok=True,
        data=iso,
        duracao=servico["duracao_min"],
        aberto=bool(cfg["aberto"]),
        slots=[{"hora": s["hora"], "estado": s["estado"]} for s in slots],
        almoco={"inicio": cfg["almoco_inicio"], "fim": cfg["almoco_fim"]},
    )


@app.post("/api/agendar")
def api_agendar():
    con = db()
    dados = request.get_json(silent=True) or {}

    # honeypot: campo invisível que só robô preenche
    if dados.get("site"):
        return jsonify(ok=False, erro="Não foi possível concluir o agendamento."), 400

    if not _limite_ok(con, _ip(), "agendar", 15, 10):
        return jsonify(ok=False, erro="Muitas tentativas. Aguarde alguns minutos."), 429

    servico = con.execute(
        "SELECT * FROM servicos WHERE id = ? AND ativo = 1", (dados.get("servico_id"),)
    ).fetchone()
    if not servico:
        return jsonify(ok=False, erro="Serviço indisponível."), 400

    iso = (dados.get("data") or "").strip()
    hora = (dados.get("hora") or "").strip()
    nome = " ".join((dados.get("nome") or "").split())[:80]
    whatsapp = _normalizar_whatsapp(dados.get("whatsapp"))

    if len(nome) < 3:
        return jsonify(ok=False, erro="Informe seu nome completo."), 400
    if not whatsapp:
        return jsonify(ok=False, erro="Informe um WhatsApp válido com DDD."), 400
    if not dados.get("consentimento"):
        return jsonify(ok=False, erro="É preciso aceitar o uso dos dados para agendar."), 400

    _registrar_tentativa(con, _ip(), "agendar")

    ag, motivo = _criar_agendamento(con, servico, iso, hora, nome, whatsapp)
    if not ag:
        return jsonify(ok=False, erro=motivo), 409

    _avisar_novo_agendamento(con, ag)
    app.logger.info("Novo agendamento %s %s %s", ag["codigo"], ag["data"], ag["hora"])
    return jsonify(
        ok=True,
        codigo=ag["codigo"],
        link=url_for("agendamento_publico", codigo=ag["codigo"]),
        resumo={
            "servico": ag["servico"],
            "data": rules.data_br(ag["data"]),
            "hora": ag["hora"],
            "nome": ag["nome"],
        },
    )


@app.get("/agendamento/<codigo>")
def agendamento_publico(codigo):
    con = db()
    ag = con.execute(
        "SELECT a.*, s.nome AS servico_nome FROM agendamentos a "
        "JOIN servicos s ON s.id = a.servico_id WHERE a.codigo = ?",
        (codigo.upper(),),
    ).fetchone()
    if not ag:
        abort(404)
    return render_template("sucesso.html", ag=ag, codigo=ag["codigo"])


@app.get("/agendamento/<codigo>.ics")
def agendamento_ics(codigo):
    con = db()
    ag = con.execute(
        "SELECT a.*, s.nome AS servico_nome FROM agendamentos a "
        "JOIN servicos s ON s.id = a.servico_id WHERE a.codigo = ?",
        (codigo.upper(),),
    ).fetchone()
    if not ag:
        abort(404)

    ini = f"{ag['data']}T{ag['hora_inicio'].replace(':', '')}00"
    fim = f"{ag['data']}T{ag['hora_fim'].replace(':', '')}00"
    descricao = f"{ag['servico_nome']} com {config_global(con, 'marca')}. Código {ag['codigo']}."
    conteudo = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Gabriel do Corte//Agendamento//PT-BR",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:{ag['codigo']}@barbearia",
            f"DTSTAMP:{agora().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;TZID=America/Sao_Paulo:{ini}",
            f"DTEND;TZID=America/Sao_Paulo:{fim}",
            f"SUMMARY:{ag['servico_nome']} - {config_global(con, 'marca')}",
            f"DESCRIPTION:{descricao}",
            f"LOCATION:{config_global(con, 'endereco')}",
            "BEGIN:VALARM",
            "TRIGGER:-PT2H",
            "ACTION:DISPLAY",
            "DESCRIPTION:Lembrete do seu horário",
            "END:VALARM",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
    resposta = app.response_class(conteudo, mimetype="text/calendar; charset=utf-8")
    resposta.headers["Content-Disposition"] = (
        f"attachment; filename=agendamento-{ag['codigo']}.ics"
    )
    return resposta


@app.get("/politica-de-privacidade")
def privacidade():
    return render_template("privacidade.html")


@app.get("/sw.js")
def service_worker():
    resposta = send_from_directory(app.static_folder, "sw.js")
    resposta.headers["Cache-Control"] = "no-cache"
    return resposta


# ------------------------------------------------------------------ login
@app.route("/login", methods=["GET", "POST"])
def login():
    if admin_necessario():
        return redirect(url_for("admin_hoje"))

    if request.method == "POST":
        con = db()
        usuario = (request.form.get("usuario") or "").strip()
        senha = request.form.get("senha") or ""
        chave = f"{_ip()}|{usuario}"

        if not _limite_ok(con, chave, "login", 5, 15):
            flash("Muitas tentativas. Aguarde 15 minutos e tente novamente.", "erro")
            return render_template("login.html"), 429

        admin = con.execute(
            "SELECT * FROM admins WHERE usuario = ?", (usuario,)
        ).fetchone()
        if admin and check_password_hash(admin["senha_hash"], senha):
            _registrar_tentativa(con, chave, "login_ok")
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_nome"] = admin["nome"]
            session["csrf"] = secrets.token_urlsafe(24)
            session.permanent = True
            destino = request.args.get("proximo") or url_for("admin_hoje")
            if not destino.startswith("/"):
                destino = url_for("admin_hoje")
            return redirect(destino)

        _registrar_tentativa(con, chave, "login")
        flash("Usuário ou senha inválidos.", "erro")

    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("inicio"))


# ------------------------------------------------------------------ painel: hoje
@app.get("/admin")
def admin_hoje():
    redirecionar = exigir_login()
    if redirecionar:
        return redirecionar

    con = db()
    iso = agora().date().isoformat()
    agendamentos = rules.agendamentos_do_dia(con, iso)
    agendamentos.sort(key=lambda a: a["hora_inicio"])

    cfg = rules.config_do_dia(con, agora().weekday())
    slots = rules.horarios_do_dia(con, iso, rules.globais(con)["intervalo"])
    livres = [s for s in slots if s["estado"] == "livre"]

    minuto_agora = agora().hour * 60 + agora().minute
    proximo = None
    for a in agendamentos:
        if a["status"] in ("cancelado", "faltou", "concluido"):
            continue
        if rules.hhmm_para_min(a["hora_inicio"]) >= minuto_agora:
            proximo = a
            break

    hoje = agora().date()
    segunda = hoje - timedelta(days=hoje.weekday())
    semana = rules.resumo_semana(con, segunda)

    hora = agora().hour
    saudacao = "Bom dia" if hora < 12 else ("Boa tarde" if hora < 18 else "Boa noite")

    return render_template(
        "admin_hoje.html",
        hoje=iso,
        agendamentos=agendamentos,
        proximo=proximo,
        livres=len(livres),
        cfg=cfg,
        semana=semana,
        saudacao=saudacao,
        total_hoje=len([a for a in agendamentos if a["status"] not in ("cancelado",)]),
    )


# ------------------------------------------------------------------ painel: semana
@app.get("/admin/semana")
def admin_semana():
    redirecionar = exigir_login()
    if redirecionar:
        return redirecionar

    con = db()
    referencia = request.args.get("ini")
    try:
        base = datetime.strptime(referencia, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        base = agora().date()
    segunda = base - timedelta(days=base.weekday())

    dias = []
    for i in range(7):
        d = segunda + timedelta(days=i)
        iso = d.isoformat()
        grade = rules.grade_do_dia(con, iso)
        ags = {a["hora_inicio"]: a for a in rules.agendamentos_do_dia(con, iso)}
        bloqueios = rules.bloqueios_do_dia(con, iso)
        bloqueado_dia = any(not b["hora_inicio"] for b in bloqueios)
        dias.append(
            {
                "iso": iso,
                "data": d,
                "config": grade["config"],
                "faixas": grade["faixas"],
                "fechado": grade["fechado"] or bloqueado_dia,
                "agendamentos": ags,
                "hoje": iso == agora().date().isoformat(),
            }
        )

    return render_template(
        "admin_semana.html",
        dias=dias,
        horas=sorted({f["hora"] for d in dias for f in d["faixas"]}),
        segunda=segunda,
        anterior=(segunda - timedelta(days=7)).isoformat(),
        proxima=(segunda + timedelta(days=7)).isoformat(),
        resumo=rules.resumo_semana(con, segunda),
    )


# ------------------------------------------------------------------ painel: todos
@app.get("/admin/agendamentos")
def admin_agendamentos():
    redirecionar = exigir_login()
    if redirecionar:
        return redirecionar

    con = db()
    busca = (request.args.get("busca") or "").strip()
    status = request.args.get("status") or ""
    servico_id = request.args.get("servico_id", type=int)
    de = request.args.get("de") or ""
    ate = request.args.get("ate") or ""
    pagina = max(1, request.args.get("pagina", type=int) or 1)
    por_pagina = 20

    condicoes = []
    parametros = []
    if busca:
        condicoes.append("(a.cliente_nome LIKE ? OR a.cliente_whatsapp LIKE ? OR a.codigo LIKE ?)")
        filtro = f"%{busca}%"
        parametros += [filtro, filtro, filtro]
    if status in rules.STATUS_VALIDOS:
        condicoes.append("a.status = ?")
        parametros.append(status)
    if servico_id:
        condicoes.append("a.servico_id = ?")
        parametros.append(servico_id)
    if de:
        condicoes.append("a.data >= ?")
        parametros.append(de)
    if ate:
        condicoes.append("a.data <= ?")
        parametros.append(ate)

    onde = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    total = con.execute(
        f"SELECT COUNT(*) AS n FROM agendamentos a {onde}", parametros
    ).fetchone()["n"]
    paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = min(pagina, paginas)

    linhas = con.execute(
        f"SELECT a.*, s.nome AS servico_nome FROM agendamentos a "
        f"JOIN servicos s ON s.id = a.servico_id {onde} "
        f"ORDER BY a.data DESC, a.hora_inicio DESC LIMIT ? OFFSET ?",
        parametros + [por_pagina, (pagina - 1) * por_pagina],
    ).fetchall()

    servicos = con.execute("SELECT * FROM servicos ORDER BY ordem, id").fetchall()
    return render_template(
        "admin_agendamentos.html",
        agendamentos=linhas,
        servicos=servicos,
        busca=busca,
        status=status,
        servico_id=servico_id,
        de=de,
        ate=ate,
        pagina=pagina,
        paginas=paginas,
        total=total,
    )


# ------------------------------------------------------------------ painel: detalhe
@app.get("/admin/agendamento/<int:agendamento_id>")
def admin_detalhe(agendamento_id):
    redirecionar = exigir_login()
    if redirecionar:
        return redirecionar

    con = db()
    ag = con.execute(
        "SELECT a.*, s.nome AS servico_nome, s.duracao_min FROM agendamentos a "
        "JOIN servicos s ON s.id = a.servico_id WHERE a.id = ?",
        (agendamento_id,),
    ).fetchone()
    if not ag:
        abort(404)

    return render_template("admin_detalhe.html", ag=ag)


@app.post("/admin/agendamento/<int:agendamento_id>/status")
def admin_status(agendamento_id):
    redirecionar = exigir_login()
    if redirecionar:
        return redirecionar

    con = db()
    novo = request.form.get("status")
    if novo not in rules.STATUS_VALIDOS:
        abort(400)

    motivo = (request.form.get("motivo") or "").strip()[:200]
    agora_str = agora_iso()

    con.execute(
        "UPDATE agendamentos SET status = ?, atualizado_em = ? WHERE id = ?",
        (novo, agora_str, agendamento_id),
    )
    if motivo:
        con.execute(
            "UPDATE agendamentos SET observacao = TRIM(observacao || char(10) || ?) WHERE id = ?",
            (f"[{rules.STATUS_ROTULO[novo]}] {motivo}", agendamento_id),
        )
    con.commit()

    if novo == "cancelado":
        ag = con.execute(
            "SELECT cliente_nome, data, hora_inicio FROM agendamentos WHERE id = ?",
            (agendamento_id,),
        ).fetchone()
        if ag:
            try:
                push.enviar_para_todos(
                    con,
                    "Agendamento cancelado",
                    f"{ag['cliente_nome']} | {rules.data_br(ag['data'])} às {ag['hora_inicio']}",
                    "/admin",
                )
            except Exception:
                pass

    flash("Status atualizado.", "ok")
    return redirect(request.form.get("voltar") or url_for("admin_detalhe", agendamento_id=agendamento_id))


@app.post("/admin/agendamento/<int:agendamento_id>/remarcar")
def admin_remarcar(agendamento_id):
    redirecionar = exigir_login()
    if redirecionar:
        return redirecionar

    con = db()
    ag = con.execute("SELECT * FROM agendamentos WHERE id = ?", (agendamento_id,)).fetchone()
    if not ag:
        abort(404)

    nova_data = request.form.get("data") or ""
    nova_hora = request.form.get("hora") or ""
    duracao = con.execute(
        "SELECT duracao_min FROM servicos WHERE id = ?", (ag["servico_id"],)
    ).fetchone()["duracao_min"]

    ok, motivo = rules.pode_agendar(con, nova_data, nova_hora, duracao, ignorar_id=agendamento_id)
    if not ok:
        flash(motivo, "erro")
        return redirect(url_for("admin_detalhe", agendamento_id=agendamento_id))

    inicio = rules.hhmm_para_min(nova_hora)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            "UPDATE agendamentos SET data = ?, hora_inicio = ?, hora_fim = ?, "
            "atualizado_em = ? WHERE id = ?",
            (
                nova_data,
                nova_hora,
                rules.min_para_hhmm(inicio + duracao),
                agora_iso(),
                agendamento_id,
            ),
        )
        con.commit()
    except Exception:
        con.rollback()
        flash("Não deu para remarcar: horário já ocupado.", "erro")
        return redirect(url_for("admin_detalhe", agendamento_id=agendamento_id))

    flash("Agendamento remarcado.", "ok")
    return redirect(url_for("admin_detalhe", agendamento_id=agendamento_id))


# ------------------------------------------------------------------ painel: manual
@app.route("/admin/novo", methods=["GET", "POST"])
def admin_novo():
    redirecionar = exigir_login()
    if redirecionar:
        return redirecionar

    con = db()
    servicos = con.execute("SELECT * FROM servicos WHERE ativo = 1 ORDER BY ordem, id").fetchall()
    dias = rules.gerar_dias(con)

    if request.method == "POST":
        servico = con.execute(
            "SELECT * FROM servicos WHERE id = ?", (request.form.get("servico_id"),)
        ).fetchone()
        nome = " ".join((request.form.get("nome") or "").split())[:80]
        whatsapp = _normalizar_whatsapp(request.form.get("whatsapp"))
        iso = request.form.get("data") or ""
        hora = request.form.get("hora") or ""

        if not servico or len(nome) < 3 or not whatsapp:
            flash("Preencha serviço, nome e WhatsApp.", "erro")
        else:
            ag, motivo = _criar_agendamento(
                con, servico, iso, hora, nome, whatsapp, origem="manual",
                observacao=(request.form.get("observacao") or "").strip()[:300],
            )
            if ag:
                flash(f"Agendamento criado para {nome}.", "ok")
                return redirect(
                    url_for("admin_detalhe", agendamento_id=_id_por_codigo(con, ag["codigo"]))
                )
            flash(motivo, "erro")

    return render_template(
        "admin_novo.html",
        servicos=servicos,
        dias=dias,
        pre_data=request.args.get("data") or "",
        pre_hora=request.args.get("hora") or "",
    )


def _id_por_codigo(con, codigo):
    linha = con.execute("SELECT id FROM agendamentos WHERE codigo = ?", (codigo,)).fetchone()
    return linha["id"] if linha else 0


# ------------------------------------------------------------------ painel: bloqueios
@app.route("/admin/bloqueios", methods=["GET", "POST"])
def admin_bloqueios():
    redirecionar = exigir_login()
    if redirecionar:
        return redirecionar

    con = db()
    if request.method == "POST":
        iso = request.form.get("data") or ""
        dia_inteiro = request.form.get("dia_inteiro") == "1"
        hora_inicio = None if dia_inteiro else (request.form.get("hora_inicio") or None)
        hora_fim = None if dia_inteiro else (request.form.get("hora_fim") or None)
        motivo = (request.form.get("motivo") or "").strip()[:120]

        try:
            datetime.strptime(iso, "%Y-%m-%d")
        except (TypeError, ValueError):
            flash("Informe uma data válida.", "erro")
        else:
            if not dia_inteiro:
                if not hora_inicio or not hora_fim:
                    flash("Informe o horário de início e fim do bloqueio.", "erro")
                    return redirect(url_for("admin_bloqueios"))
                if rules.hhmm_para_min(hora_fim) <= rules.hhmm_para_min(hora_inicio):
                    flash("O fim do bloqueio deve ser depois do início.", "erro")
                    return redirect(url_for("admin_bloqueios"))
            con.execute(
                "INSERT INTO bloqueios (data, hora_inicio, hora_fim, motivo, criado_em) "
                "VALUES (?, ?, ?, ?, ?)",
                (iso, hora_inicio, hora_fim, motivo, agora_iso()),
            )
            con.commit()
            flash("Horário bloqueado. Já não aparece para os clientes.", "ok")
        return redirect(url_for("admin_bloqueios"))

    hoje = agora().date().isoformat()
    bloqueios = con.execute(
        "SELECT * FROM bloqueios WHERE data >= ? ORDER BY data, hora_inicio",
        (hoje,),
    ).fetchall()
    return render_template("admin_bloqueios.html", bloqueios=bloqueios, hoje=hoje)


@app.post("/admin/bloqueios/<int:bloqueio_id>/excluir")
def admin_bloqueio_excluir(bloqueio_id):
    redirecionar = exigir_login()
    if redirecionar:
        return redirecionar
    con = db()
    con.execute("DELETE FROM bloqueios WHERE id = ?", (bloqueio_id,))
    con.commit()
    flash("Bloqueio removido.", "ok")
    return redirect(url_for("admin_bloqueios"))


# ------------------------------------------------------------------ painel: configurações
@app.route("/admin/configuracoes", methods=["GET", "POST"])
def admin_configuracoes():
    redirecionar = exigir_login()
    if redirecionar:
        return redirecionar

    con = db()

    if request.method == "POST":
        acao = request.form.get("acao")

        if acao == "horarios":
            for dia in range(7):
                aberto = 1 if request.form.get(f"aberto_{dia}") == "1" else 0
                abre = request.form.get(f"abre_{dia}") or "08:00"
                fecha = request.form.get(f"fecha_{dia}") or "18:00"
                almoco_ini = request.form.get(f"almoco_inicio_{dia}") or "11:00"
                almoco_fim = request.form.get(f"almoco_fim_{dia}") or "13:00"
                con.execute(
                    "UPDATE configuracoes SET aberto = ?, abre = ?, fecha = ?, "
                    "almoco_inicio = ?, almoco_fim = ? WHERE dia_semana = ?",
                    (aberto, abre, fecha, almoco_ini, almoco_fim, dia),
                )
            flash("Horários de funcionamento atualizados.", "ok")

        elif acao == "globais":
            for chave in (
                "marca", "assinatura", "slogan", "whatsapp", "instagram",
                "endereco", "cidade",
            ):
                valor = (request.form.get(chave) or "").strip()[:160]
                if valor:
                    salvar_global(con, chave, valor)
            for chave, padrao, minimo, maximo in (
                ("intervalo_min", "30", 10, 120),
                ("antecedencia_min", "60", 0, 1440),
                ("janela_dias", "30", 1, 180),
            ):
                bruto = request.form.get(chave) or padrao
                try:
                    numero = max(minimo, min(maximo, int(bruto)))
                except ValueError:
                    numero = int(padrao)
                salvar_global(con, chave, numero)
            flash("Configurações gerais salvas.", "ok")

        elif acao == "servico_novo":
            nome = (request.form.get("nome") or "").strip()[:80]
            if nome:
                con.execute(
                    "INSERT INTO servicos (nome, descricao, duracao_min, preco_centavos, ativo, ordem) "
                    "VALUES (?, ?, ?, ?, 1, ?)",
                    (
                        nome,
                        (request.form.get("descricao") or "").strip()[:160],
                        max(10, int(request.form.get("duracao_min") or 30)),
                        _para_centavos(request.form.get("preco")),
                        int(request.form.get("ordem") or 99),
                    ),
                )
                flash("Serviço adicionado.", "ok")
            else:
                flash("Dê um nome ao serviço.", "erro")

        elif acao == "servico_editar":
            try:
                servico_id = int(request.form.get("servico_id"))
            except (TypeError, ValueError):
                abort(400)
            con.execute(
                "UPDATE servicos SET nome = ?, descricao = ?, duracao_min = ?, "
                "preco_centavos = ?, ativo = ?, ordem = ? WHERE id = ?",
                (
                    (request.form.get("nome") or "").strip()[:80],
                    (request.form.get("descricao") or "").strip()[:160],
                    max(10, int(request.form.get("duracao_min") or 30)),
                    _para_centavos(request.form.get("preco")),
                    1 if request.form.get("ativo") == "1" else 0,
                    int(request.form.get("ordem") or 99),
                    servico_id,
                ),
            )
            flash("Serviço atualizado.", "ok")

        elif acao == "servico_excluir":
            try:
                servico_id = int(request.form.get("servico_id"))
            except (TypeError, ValueError):
                abort(400)
            usado = con.execute(
                "SELECT COUNT(*) AS n FROM agendamentos WHERE servico_id = ?", (servico_id,)
            ).fetchone()["n"]
            if usado:
                con.execute("UPDATE servicos SET ativo = 0 WHERE id = ?", (servico_id,))
                flash("Serviço tem agendamentos: foi desativado (não apagado).", "ok")
            else:
                con.execute("DELETE FROM servicos WHERE id = ?", (servico_id,))
                flash("Serviço removido.", "ok")

        elif acao == "senha":
            atual = request.form.get("senha_atual") or ""
            nova = request.form.get("senha_nova") or ""
            confirma = request.form.get("senha_confirma") or ""
            admin = con.execute(
                "SELECT * FROM admins WHERE id = ?", (session.get("admin_id"),)
            ).fetchone()
            if not admin or not check_password_hash(admin["senha_hash"], atual):
                flash("Senha atual incorreta.", "erro")
            elif len(nova) < 8:
                flash("A nova senha precisa ter pelo menos 8 caracteres.", "erro")
            elif nova != confirma:
                flash("A confirmação não confere.", "erro")
            else:
                con.execute(
                    "UPDATE admins SET senha_hash = ? WHERE id = ?",
                    (generate_password_hash(nova), admin["id"]),
                )
                flash("Senha alterada.", "ok")

        con.commit()
        return redirect(url_for("admin_configuracoes"))

    servicos = con.execute("SELECT * FROM servicos ORDER BY ordem, id").fetchall()
    semana = [rules.config_do_dia(con, d) for d in range(7)]
    gerais = {c: config_global(con, c, "") for c in (
        "marca", "assinatura", "slogan", "whatsapp", "instagram", "endereco",
        "cidade", "intervalo_min", "antecedencia_min", "janela_dias",
    )}
    chave_push = push.chave_publica(con, salvar_global)
    aparelhos = con.execute("SELECT COUNT(*) AS n FROM push_subscriptions").fetchone()["n"]
    return render_template(
        "admin_configuracoes.html",
        servicos=servicos,
        semana=semana,
        gerais=gerais,
        chave_push=chave_push,
        push_disponivel=push.DISPONIVEL,
        aparelhos=aparelhos,
    )


def _para_centavos(texto):
    """'65,00' ou '65.00' -> 6500"""
    if texto is None:
        return 0
    limpo = str(texto).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return int(round(float(limpo) * 100))
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------------ notificações
@app.get("/api/push/chave")
def push_chave():
    if not admin_necessario():
        return jsonify(ok=False), 401
    con = db()
    return jsonify(ok=True, chave=push.chave_publica(con, salvar_global))


@app.post("/api/push/inscrever")
def push_inscrever():
    if not admin_necessario():
        return jsonify(ok=False), 401

    con = db()
    dados = request.get_json(silent=True) or {}
    endpoint = dados.get("endpoint")
    chaves = dados.get("keys") or {}
    if not endpoint or not chaves.get("p256dh") or not chaves.get("auth"):
        return jsonify(ok=False, erro="Inscrição inválida."), 400

    con.execute(
        "INSERT INTO push_subscriptions (admin_id, endpoint, chaves, dispositivo, criado_em) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(endpoint) DO UPDATE SET chaves = excluded.chaves, "
        "admin_id = excluded.admin_id, dispositivo = excluded.dispositivo",
        (
            session["admin_id"],
            endpoint,
            json.dumps(chaves),
            (request.headers.get("User-Agent") or "")[:120],
            agora_iso(),
        ),
    )
    con.commit()
    return jsonify(ok=True)


@app.post("/api/push/teste")
def push_teste():
    if not admin_necessario():
        return jsonify(ok=False), 401
    con = db()
    enviados = push.enviar_para_todos(
        con, "Teste de notificação", "Se você está vendo isso, deu certo!", "/admin"
    )
    return jsonify(ok=True, enviados=enviados, disponivel=push.DISPONIVEL)


@app.get("/api/admin/novidades")
def admin_novidades():
    if not admin_necessario():
        return jsonify(ok=False), 401

    con = db()
    desde = request.args.get("desde") or ""
    iso = agora().date().isoformat()
    resultado = {"ok": True, "agora": agora_iso(), "hoje": 0, "novos": 0}
    try:
        resultado["hoje"] = con.execute(
            "SELECT COUNT(*) AS n FROM agendamentos WHERE data = ? AND status <> 'cancelado'",
            (iso,),
        ).fetchone()["n"]
        if desde:
            resultado["novos"] = con.execute(
                "SELECT COUNT(*) AS n FROM agendamentos WHERE criado_em > ?",
                (desde,),
            ).fetchone()["n"]
    except Exception:
        pass
    return jsonify(resultado)


# ------------------------------------------------------------------ erros
@app.errorhandler(404)
def nao_encontrado(_):
    return render_template("erro.html", codigo=404,
                           mensagem="Página não encontrada."), 404


@app.errorhandler(500)
def erro_interno(_):
    return render_template("erro.html", codigo=500,
                           mensagem="Algo deu errado por aqui."), 500


# ------------------------------------------------------------------ inicialização
iniciar_banco()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", "8000"))
    print(f"\n  {config_global(conectar(), 'marca', 'Barbearia')} — http://localhost:{porta}\n")
    app.run(host="0.0.0.0", port=porta, debug=os.environ.get("DEBUG") == "1")