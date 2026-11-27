"""Helpers de interface expostos ao Jinja: ícones do sprite SVG e avatares."""

import hashlib

from flask import url_for
from markupsafe import Markup, escape


def icon(name, cls="", label=None):
    """Renderiza um ícone do sprite Lucide (static/icons/sprite.svg).

    Por padrão o ícone é decorativo (aria-hidden). Informe ``label`` quando o
    ícone for o único conteúdo significativo do elemento.
    """
    href = f"{url_for('static', filename='icons/sprite.svg')}#i-{escape(name)}"
    classes = f"icon {escape(cls)}".strip()
    if label:
        a11y = f'role="img" aria-label="{escape(label)}"'
    else:
        a11y = 'aria-hidden="true"'
    return Markup(
        f'<svg class="{classes}" {a11y} focusable="false"><use href="{href}"></use></svg>'
    )


def iniciais(nome):
    """Até duas iniciais (primeiro e último nome), em maiúsculas."""
    partes = [p for p in str(nome or "").split() if p[:1].isalpha()]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:1].upper()
    return (partes[0][:1] + partes[-1][:1]).upper()


def avatar_hue(nome):
    """Matiz estável (0-359) derivado do nome, para a cor do avatar sem foto."""
    digest = hashlib.sha1(str(nome or "").strip().casefold().encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "big") % 360


def avatar(usuario, size="", decorative=True):
    """Foto do usuário ou iniciais em uma cor derivada do nome."""
    nome = getattr(usuario, "nome", "") or ""
    classes = f"avatar {escape(size)}".strip()
    foto = getattr(usuario, "foto", None)
    alt = "" if decorative else f"Foto de {escape(nome)}"
    if foto:
        src = url_for("static", filename=f"uploads/avatars/{foto}")
        return Markup(
            f'<span class="{classes}"><img src="{escape(src)}" alt="{alt}" '
            f'width="112" height="112" loading="lazy" decoding="async"></span>'
        )
    hidden = ' aria-hidden="true"' if decorative else f' role="img" aria-label="{escape(nome)}"'
    return Markup(
        f'<span class="{classes}" style="--avatar-hue:{avatar_hue(nome)}"{hidden}>'
        f"{escape(iniciais(nome))}</span>"
    )


def brl(valor):
    """Formata como moeda brasileira: 1234.5 -> 'R$ 1.234,50'."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0
    texto = f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def data_br(valor):
    return valor.strftime("%d/%m/%Y") if valor else ""


STATUS_PEDIDO = {
    "aguardando_pagamento": ("Aguardando pagamento", "warning", "clock"),
    "ativa": ("Aluguel ativo", "success", "book-open"),
    "concluida": ("Concluído", "success", "circle-check"),
    "devolvida": ("Devolvido", "info", "rotate-ccw"),
    "cancelada": ("Cancelado", "danger", "circle-x"),
}


def status_pedido(status):
    return STATUS_PEDIDO.get(status, (str(status or "").replace("_", " ").capitalize(), "", "info"))


def dict_without(dados, *chaves):
    """Cópia do dicionário sem as chaves informadas (ex.: remover um filtro da URL)."""
    return {k: v for k, v in dict(dados).items() if k not in chaves and v not in ("", None)}


def register_ui_helpers(app):
    app.jinja_env.globals.update(icon=icon, avatar=avatar, status_pedido=status_pedido)
    app.jinja_env.filters["iniciais"] = iniciais
    app.jinja_env.filters["brl"] = brl
    app.jinja_env.filters["data_br"] = data_br
    app.jinja_env.filters["dict_without"] = dict_without
