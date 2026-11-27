import uuid
from urllib.parse import urlsplit, urlunsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func

from database import db
from models.biblioteca import Biblioteca
from models.livro import Livro
from services.limites import alugueis_em_aberto, limite_alugueis, mensagem_limite
from models.usuario import Usuario

carrinho_bp = Blueprint("carrinho", __name__)

DIAS_ALUGUEL = (7, 14, 30)
MAX_POR_ITEM = 20


def frete_domicilio():
    """Valor único da entrega em domicílio, definido em config.DELIVERY_FEE."""
    return float(current_app.config.get("DELIVERY_FEE", 12.90))


def _cart():
    cart = session.get("carrinho")
    if not isinstance(cart, dict):
        cart = {}
        session["carrinho"] = cart
    return cart


def _wants_json():
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes[
        "text/html"
    ]


def _payload():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else request.form


def _safe_referrer():
    referrer = request.referrer or ""
    parsed = urlsplit(referrer)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {"http", "https"} or parsed.netloc != request.host:
            return None
    elif not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return None
    if "\\" in parsed.path or any(ord(char) < 32 for char in referrer):
        return None
    return urlunsplit(("", "", parsed.path, parsed.query, ""))


def _usuario_logado():
    user_id = session.get("usuario_id")
    return db.session.get(Usuario, user_id) if user_id else None


def _excede_limite_alugueis(cart, key_novo, qty_nova):
    """True se a sacola (com a quantidade nova) passaria do limite de aluguéis do plano."""
    usuario = _usuario_logado()
    limite = limite_alugueis(usuario)
    no_carrinho = 0
    for key, raw_qty in cart.items():
        if key == key_novo:
            continue
        try:
            _, tipo, _ = _parse_key(key)
            if tipo == "aluguel":
                no_carrinho += max(1, int(raw_qty))
        except (ValueError, TypeError):
            continue
    em_aberto = alugueis_em_aberto(usuario.id) if usuario else 0
    return em_aberto + no_carrinho + qty_nova > limite, limite


def _item_key(book_id, tipo, dias):
    return f"{int(book_id)}:{tipo}:{int(dias)}"


def _parse_key(key):
    book_id, tipo, dias = key.split(":", 2)
    return int(book_id), tipo, int(dias)


def _cart_rows():
    cart = _cart()
    parsed_items = []
    for key, raw_qty in list(cart.items()):
        try:
            book_id, tipo, dias = _parse_key(key)
            qty = max(1, int(raw_qty))
        except (ValueError, TypeError):
            cart.pop(key, None)
            continue
        if tipo not in ("aluguel", "compra"):
            cart.pop(key, None)
            continue
        parsed_items.append((key, book_id, tipo, dias, qty))

    book_ids = {item[1] for item in parsed_items}
    books = (
        {book.id: book for book in Livro.query.filter(Livro.id.in_(book_ids)).all()}
        if book_ids
        else {}
    )
    rows = []
    total = 0.0
    for key, book_id, tipo, dias, qty in parsed_items:
        book = books.get(book_id)
        if not book or not book.ativo:
            cart.pop(key, None)
            continue
        unit = book.preco_aluguel_para(dias) if tipo == "aluguel" else book.preco_venda
        subtotal = round(float(unit or 0) * qty, 2)
        total += subtotal
        rows.append(
            {
                "key": key,
                "livro": book,
                "tipo": tipo,
                "dias": dias,
                "quantidade": qty,
                "unitario": unit,
                "subtotal": subtotal,
            }
        )
    session["carrinho"] = cart
    return rows, round(total, 2)


def entrega_escolhida():
    modo = session.get("entrega_preferida")
    return modo if modo in ("domicilio", "retirada") else None


def sugestoes_para_sacola(excluir_ids=(), limite=4):
    """Livros disponíveis para sugerir quando a sacola está vazia ou pequena."""
    query = Livro.query.filter(Livro.ativo.is_(True), Livro.estoque > 0)
    if excluir_ids:
        query = query.filter(~Livro.id.in_(list(excluir_ids)))
    return query.order_by(func.random()).limit(limite).all()


def _capa(book):
    if not book.capa_arquivo:
        return None
    return url_for("static", filename=f"images/{book.capa_arquivo}")


def cart_state():
    """Estado serializável da sacola, usado pelo painel lateral."""
    rows, subtotal = _cart_rows()
    entrega = entrega_escolhida()
    frete = frete_domicilio() if rows and entrega == "domicilio" else 0.0
    quantidade_total = sum(row["quantidade"] for row in rows)
    state = {
        "ok": True,
        "itens": [
            {
                "key": row["key"],
                "livro_id": row["livro"].id,
                "titulo": row["livro"].titulo,
                "autor": row["livro"].autor,
                "capa": _capa(row["livro"]),
                "url": url_for("livros.detalhes", livro_id=row["livro"].id),
                "tipo": row["tipo"],
                "dias": row["dias"],
                "quantidade": row["quantidade"],
                "maximo": max(1, min(MAX_POR_ITEM, row["livro"].estoque or 1)),
                "unitario": round(float(row["unitario"] or 0), 2),
                "subtotal": row["subtotal"],
            }
            for row in rows
        ],
        "quantidade_total": quantidade_total,
        "subtotal": subtotal,
        "entrega": entrega,
        "frete_domicilio": frete_domicilio(),
        "frete": round(frete, 2),
        "total": round(subtotal + frete, 2),
        "checkout_url": url_for("carrinho.checkout"),
        "sugestoes": [],
    }
    if len(rows) < 2:
        state["sugestoes"] = [
            {
                "livro_id": book.id,
                "titulo": book.titulo,
                "autor": book.autor,
                "capa": _capa(book),
                "url": url_for("livros.detalhes", livro_id=book.id),
                "tipo": "compra" if book.modalidade == "Venda" else "aluguel",
                "preco": round(
                    float(book.preco_venda if book.modalidade == "Venda" else book.preco_aluguel)
                    or 0,
                    2,
                ),
            }
            for book in sugestoes_para_sacola({row["livro"].id for row in rows}, 4 if not rows else 3)
        ]
    return state


def _respond(message=None, category="erro", status=200, redirect_to=None):
    """Resposta JSON para o painel lateral ou redirecionamento para formulários."""
    if _wants_json():
        body = cart_state()
        if message:
            body["mensagem"] = message
            body["ok"] = category != "erro"
        return jsonify(body), status
    if message:
        flash(message, category)
    return redirect(redirect_to or url_for("carrinho.ver_carrinho"))


@carrinho_bp.get("/api/carrinho")
def estado():
    return jsonify(cart_state())


@carrinho_bp.get("/carrinho")
def ver_carrinho():
    rows, subtotal = _cart_rows()
    entrega = request.args.get("entrega") or entrega_escolhida() or "domicilio"
    if entrega not in ("domicilio", "retirada"):
        entrega = "domicilio"
    frete = frete_domicilio() if entrega == "domicilio" and rows else 0
    sugestoes = sugestoes_para_sacola({row["livro"].id for row in rows}, 4)
    return render_template(
        "carrinho.html",
        rows=rows,
        subtotal=subtotal,
        frete=frete,
        frete_domicilio=frete_domicilio(),
        entrega=entrega,
        total=round(subtotal + frete, 2),
        sugestoes=sugestoes,
    )


@carrinho_bp.post("/carrinho/entrega")
def escolher_entrega():
    modo = str(_payload().get("modo", ""))
    if modo not in ("domicilio", "retirada"):
        return _respond("Escolha entrega em domicílio ou retirada.", status=400)
    session["entrega_preferida"] = modo
    return _respond(redirect_to=url_for("carrinho.ver_carrinho", entrega=modo))


@carrinho_bp.post("/carrinho/adicionar")
def adicionar():
    data = _payload()
    fallback = url_for("livros.catalogo")
    try:
        book_id = int(data.get("livro_id", ""))
        tipo = str(data.get("tipo", "aluguel"))
        dias = int(data.get("dias", "14") or 14) if tipo == "aluguel" else 0
        qty = int(data.get("quantidade", "1") or 1)
    except (ValueError, TypeError):
        return _respond("Os dados do item não são válidos.", status=400, redirect_to=fallback)
    book = db.session.get(Livro, book_id)
    if not book or not book.ativo or book.estoque <= 0:
        return _respond("Livro indisponível no momento.", status=409, redirect_to=fallback)
    if tipo not in ("aluguel", "compra") or qty < 1 or qty > MAX_POR_ITEM:
        return _respond("Selecione uma quantidade válida.", status=400, redirect_to=fallback)
    if tipo == "aluguel" and (dias not in DIAS_ALUGUEL or book.modalidade not in ("Aluguel", "Ambos")):
        return _respond("Modalidade ou período de aluguel inválido.", status=400, redirect_to=fallback)
    if tipo == "compra" and book.modalidade not in ("Venda", "Ambos"):
        return _respond("Este livro não está disponível para compra.", status=400, redirect_to=fallback)
    key = _item_key(book_id, tipo, dias)
    cart = dict(_cart())
    nova_qty = min(int(cart.get(key, 0)) + qty, book.estoque, MAX_POR_ITEM)
    if tipo == "aluguel":
        excede, limite = _excede_limite_alugueis(cart, key, nova_qty)
        if excede:
            return _respond(mensagem_limite(limite), status=409, redirect_to=fallback)
    cart[key] = nova_qty
    session["carrinho"] = cart
    session.pop("checkout_reference", None)
    if _wants_json():
        body = cart_state()
        body["mensagem"] = f"“{book.titulo}” foi adicionado à sacola."
        body["adicionado"] = key
        return jsonify(body)
    return redirect(_safe_referrer() or url_for("carrinho.ver_carrinho"))


@carrinho_bp.post("/carrinho/atualizar")
def atualizar():
    data = _payload()
    key = str(data.get("key", ""))
    cart = dict(_cart())
    if key not in cart:
        return _respond("Item não encontrado no carrinho.", status=404)
    message = None
    status = 200
    try:
        qty = int(data.get("quantidade", "0"))
        book_id, _, _ = _parse_key(key)
        book = db.session.get(Livro, book_id)
        if qty <= 0:
            cart.pop(key, None)
        elif not book or qty > book.estoque:
            message = "A quantidade solicitada supera o estoque disponível."
            status = 409
        elif _parse_key(key)[1] == "aluguel" and _excede_limite_alugueis(cart, key, min(qty, MAX_POR_ITEM))[0]:
            limite = _excede_limite_alugueis(cart, key, 0)[1]
            message = mensagem_limite(limite)
            status = 409
        else:
            cart[key] = min(qty, MAX_POR_ITEM)
    except (ValueError, TypeError):
        message = "Quantidade inválida."
        status = 400
    session["carrinho"] = cart
    session.pop("checkout_reference", None)
    return _respond(message, status=status)


@carrinho_bp.post("/carrinho/remover")
def remover():
    data = _payload()
    cart = dict(_cart())
    removed = cart.pop(str(data.get("key", "")), None)
    session["carrinho"] = cart
    session.pop("checkout_reference", None)
    if _wants_json() and removed is None:
        return _respond("Item não encontrado no carrinho.", status=404)
    return _respond()


@carrinho_bp.get("/checkout")
def checkout():
    user_id = session.get("usuario_id")
    if not user_id:
        flash("Entre na sua conta antes de finalizar o pedido.", "erro")
        return redirect(url_for("usuarios.login", next=url_for("carrinho.checkout")))
    user = db.session.get(Usuario, user_id)
    if not user or user.is_admin:
        return redirect(url_for("admin.dashboard"))
    rows, subtotal = _cart_rows()
    if not rows:
        flash("Seu carrinho está vazio.", "erro")
        return redirect(url_for("carrinho.ver_carrinho"))
    session.setdefault("checkout_reference", str(uuid.uuid4()))
    from models.endereco import Endereco
    from services.estoque import disponibilidade_por_biblioteca

    bibliotecas_todas = Biblioteca.query.order_by(
        Biblioteca.estado,
        Biblioteca.cidade,
        Biblioteca.nome,
    ).all()
    disponibilidade = disponibilidade_por_biblioteca([row["livro"].id for row in rows])
    opcoes_biblioteca = []
    for biblioteca in bibliotecas_todas:
        estoque_local = disponibilidade.get(biblioteca.id, {})
        faltas, detalhes = [], []
        for row in rows:
            qtd = estoque_local.get(row["livro"].id, 0)
            detalhes.append(f"{row['livro'].titulo}: {qtd}")
            if qtd < row["quantidade"]:
                faltas.append(row["livro"].titulo)
        opcoes_biblioteca.append(
            {"biblioteca": biblioteca, "disponivel": not faltas, "faltas": faltas, "detalhes": detalhes}
        )

    return render_template(
        "checkout.html",
        rows=rows,
        opcoes_biblioteca=opcoes_biblioteca,
        subtotal=subtotal,
        user=user,
        bibliotecas=bibliotecas_todas,
        frete=frete_domicilio(),
        entrega=entrega_escolhida() or "domicilio",
        enderecos=Endereco.query.filter_by(usuario_id=user.id)
        .order_by(Endereco.padrao.desc(), Endereco.id)
        .all(),
    )
