"""Envio de e-mails transacionais via SMTP (Gmail com senha de app, sem custo).

Configuração no .env:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

Se o SMTP não estiver configurado, o envio é ignorado com um aviso no log.
Falhas de envio nunca interrompem a ação do administrador.
"""

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app


def smtp_configurado():
    cfg = current_app.config
    return bool(cfg.get("SMTP_HOST") and cfg.get("SMTP_USER") and cfg.get("SMTP_PASSWORD"))


def enviar_email(destinatario, assunto, texto):
    """Envia um e-mail em texto simples. Retorna True se enviado, False caso contrário."""
    if not destinatario:
        return False
    if not smtp_configurado():
        current_app.logger.warning("E-mail não enviado: SMTP não configurado no .env.")
        return False
    cfg = current_app.config
    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = cfg.get("SMTP_FROM") or formataddr(("Biblioteca Aberta", cfg["SMTP_USER"]))
    mensagem["To"] = destinatario
    mensagem.set_content(texto)
    porta = int(cfg.get("SMTP_PORT") or 587)
    contexto = ssl.create_default_context()
    try:
        # 465 = SSL direto; 587 (padrão) = STARTTLS. Use 465 se a 587 for bloqueada na rede.
        if porta == 465:
            servidor = smtplib.SMTP_SSL(cfg["SMTP_HOST"], porta, context=contexto, timeout=30)
        else:
            servidor = smtplib.SMTP(cfg["SMTP_HOST"], porta, timeout=30)
        with servidor:
            if porta != 465:
                servidor.starttls(context=contexto)
            servidor.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            servidor.send_message(mensagem)
        return True
    except Exception:
        current_app.logger.exception("Falha ao enviar e-mail de notificação.")
        return False
