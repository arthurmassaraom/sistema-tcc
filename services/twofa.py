"""Verificação em duas etapas (2FA) por código enviado ao e-mail do usuário.

O código tem 6 dígitos, é guardado apenas como hash, expira em VALIDADE_MINUTOS
e aceita no máximo MAX_TENTATIVAS tentativas. Um código novo invalida o anterior.
"""

import secrets
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from services.email import enviar_email

VALIDADE_MINUTOS = 10
MAX_TENTATIVAS = 5
INTERVALO_REENVIO_SEGUNDOS = 60


def _mascarar_email(email):
    usuario, _, dominio = email.partition("@")
    visivel = usuario[:2] if len(usuario) > 2 else usuario[:1]
    return f"{visivel}{'*' * max(len(usuario) - len(visivel), 3)}@{dominio}"


def email_mascarado(email):
    return _mascarar_email(email or "")


def codigo_pendente(usuario):
    """True se há um código ainda válido aguardando confirmação."""
    return bool(
        usuario.two_fa_codigo_hash
        and usuario.two_fa_expira_em
        and usuario.two_fa_expira_em > datetime.utcnow()
    )


def enviar_codigo(usuario, motivo):
    """Gera um novo código, salva o hash e envia por e-mail. Retorna True se enviado."""
    codigo = f"{secrets.randbelow(1000000):06d}"
    usuario.two_fa_codigo_hash = generate_password_hash(codigo)
    usuario.two_fa_expira_em = datetime.utcnow() + timedelta(minutes=VALIDADE_MINUTOS)
    usuario.two_fa_tentativas = 0
    db.session.commit()
    texto = (
        f"Olá, {usuario.nome.split()[0]}!\n\n"
        f"{motivo}\n\n"
        f"Seu código de verificação é: {codigo}\n\n"
        f"Ele vale por {VALIDADE_MINUTOS} minutos. Se não foi você quem pediu, "
        "ignore este e-mail e troque sua senha.\n\n"
        "Biblioteca Aberta\n"
    )
    return enviar_email(usuario.email, f"Seu código: {codigo}", texto)


def verificar_codigo(usuario, codigo):
    """Confere o código informado. Retorna (ok, mensagem_de_erro)."""
    if not codigo_pendente(usuario):
        return False, "Este código expirou. Peça um novo código."
    if (usuario.two_fa_tentativas or 0) >= MAX_TENTATIVAS:
        return False, "Muitas tentativas incorretas. Peça um novo código."
    usuario.two_fa_tentativas = (usuario.two_fa_tentativas or 0) + 1
    limpo = (codigo or "").strip().replace(" ", "")
    if limpo.isdigit() and len(limpo) == 6 and check_password_hash(usuario.two_fa_codigo_hash, limpo):
        usuario.two_fa_codigo_hash = None
        usuario.two_fa_expira_em = None
        usuario.two_fa_tentativas = 0
        db.session.commit()
        return True, None
    db.session.commit()
    restantes = MAX_TENTATIVAS - usuario.two_fa_tentativas
    if restantes <= 0:
        return False, "Muitas tentativas incorretas. Peça um novo código."
    return False, f"Código incorreto. Você ainda tem {restantes} {'tentativa' if restantes == 1 else 'tentativas'}."


def limpar_codigo(usuario):
    usuario.two_fa_codigo_hash = None
    usuario.two_fa_expira_em = None
    usuario.two_fa_tentativas = 0
