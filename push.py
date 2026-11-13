"""
Notificações no celular (Web Push / PWA).

As chaves VAPID são criadas sozinhas na primeira execução e ficam guardadas no
banco (tabela globais). Se a biblioteca pywebpush não estiver instalada, o
sistema continua funcionando — apenas sem notificação.
"""

import base64
import json

try:
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid

    DISPONIVEL = True
except Exception:  # pragma: no cover - ambiente sem as bibliotecas
    DISPONIVEL = False


def _b64(dados):
    return base64.urlsafe_b64encode(dados).decode("ascii").rstrip("=")


def garantir_chaves(con, salvar_global):
    """Cria (uma vez) o par de chaves usado nas notificações."""
    publica = _ler(con, "vapid_public")
    privada = _ler(con, "vapid_private")
    if publica and privada:
        return publica, privada
    if not DISPONIVEL:
        return "", ""

    vapid = Vapid()
    vapid.generate_keys()
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    bruta = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    publica = _b64(bruta)
    privada = vapid.private_pem().decode("ascii")

    salvar_global(con, "vapid_public", publica)
    salvar_global(con, "vapid_private", privada)
    return publica, privada


def _ler(con, chave):
    linha = con.execute("SELECT valor FROM globais WHERE chave = ?", (chave,)).fetchone()
    return linha["valor"] if linha else ""


def chave_publica(con, salvar_global):
    return garantir_chaves(con, salvar_global)[0]


def enviar_para_todos(con, titulo, corpo, url="/admin"):
    """Manda a notificação para todos os aparelhos cadastrados."""
    if not DISPONIVEL:
        return 0

    publica, privada = garantir_chaves(con, _salvar_direto)
    if not publica or not privada:
        return 0

    try:
        vapid = Vapid.from_pem(privada.encode("ascii"))
    except Exception:
        return 0

    assinaturas = con.execute("SELECT * FROM push_subscriptions").fetchall()
    enviados = 0
    for assinatura in assinaturas:
        try:
            chaves = json.loads(assinatura["chaves"])
        except Exception:
            continue
        info = {
            "endpoint": assinatura["endpoint"],
            "keys": {"p256dh": chaves.get("p256dh", ""), "auth": chaves.get("auth", "")},
        }
        try:
            webpush(
                subscription_info=info,
                data=json.dumps(
                    {"titulo": titulo, "corpo": corpo, "url": url}, ensure_ascii=False
                ),
                vapid_private_key=vapid,
                vapid_claims={"sub": "mailto:contato@barbearia.local"},
                timeout=10,
            )
            enviados += 1
        except WebPushException as erro:
            # 404/410 = aparelho desinstalou o app: remove a inscrição
            resposta = getattr(erro, "response", None)
            if resposta is not None and resposta.status_code in (404, 410):
                con.execute("DELETE FROM push_subscriptions WHERE id = ?", (assinatura["id"],))
                con.commit()
        except Exception:
            continue
    return enviados


def _salvar_direto(con, chave, valor):
    con.execute(
        "INSERT INTO globais (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (chave, valor),
    )