"""Recomendações baseadas em dados reais do acervo e dos pedidos pagos."""

from sqlalchemy import func

from database import db
from models.livro import Livro
from models.transacao import Transacao


def mesmo_genero(livro, limite=4):
    return (
        Livro.query.filter(
            Livro.ativo.is_(True),
            Livro.id != livro.id,
            Livro.genero == livro.genero,
        )
        .order_by((Livro.estoque > 0).desc(), Livro.titulo)
        .limit(limite)
        .all()
    )


def quem_comprou_tambem_levou(livro, limite=4):
    """Livros que aparecem nos mesmos pedidos pagos (mesma referência) que este."""
    pedidos = (
        db.session.query(Transacao.referencia_pedido)
        .filter(
            Transacao.livro_id == livro.id,
            Transacao.pagamento_status == "approved",
            Transacao.referencia_pedido.isnot(None),
        )
        .distinct()
        .subquery()
    )
    linhas = (
        db.session.query(Transacao.livro_id, func.count(Transacao.id).label("vezes"))
        .filter(
            Transacao.referencia_pedido.in_(db.session.query(pedidos.c.referencia_pedido)),
            Transacao.livro_id != livro.id,
            Transacao.pagamento_status == "approved",
        )
        .group_by(Transacao.livro_id)
        .order_by(func.count(Transacao.id).desc())
        .limit(limite)
        .all()
    )
    ids = [livro_id for livro_id, _ in linhas]
    if not ids:
        return []
    livros = {
        item.id: item
        for item in Livro.query.filter(Livro.id.in_(ids), Livro.ativo.is_(True)).all()
    }
    return [livros[i] for i in ids if i in livros]
