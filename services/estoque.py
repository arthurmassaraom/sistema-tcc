"""Estoque por biblioteca.

O estoque de um livro é a soma dos exemplares em todas as bibliotecas. O campo
Livro.estoque guarda essa soma e é recalculado sempre que uma biblioteca muda,
para que buscas e o carrinho continuem usando um número único.
"""

from sqlalchemy import func, update

from database import db
from models.biblioteca import Biblioteca
from models.estoque import AlocacaoEstoque, EstoqueBiblioteca
from models.livro import Livro


def sincronizar_total(livro_id):
    total = (
        db.session.query(func.coalesce(func.sum(EstoqueBiblioteca.quantidade), 0))
        .filter(EstoqueBiblioteca.livro_id == livro_id)
        .scalar()
    )
    db.session.execute(update(Livro).where(Livro.id == livro_id).values(estoque=int(total or 0)))


def disponibilidade_por_biblioteca(livro_ids):
    """Retorna {biblioteca_id: {livro_id: quantidade}} apenas com quantidades > 0."""
    mapa = {}
    if not livro_ids:
        return mapa
    linhas = EstoqueBiblioteca.query.filter(
        EstoqueBiblioteca.livro_id.in_(livro_ids), EstoqueBiblioteca.quantidade > 0
    ).all()
    for linha in linhas:
        mapa.setdefault(linha.biblioteca_id, {})[linha.livro_id] = linha.quantidade
    return mapa


def debitar(livro_id, quantidade, biblioteca_id=None):
    """Tira `quantidade` exemplares do livro.

    Com biblioteca_id, tira só daquela biblioteca (retirada). Sem ele, tira das
    bibliotecas com mais exemplares (entrega em domicílio).
    Retorna a lista de (biblioteca_id, quantidade) usada. Levanta ValueError se faltar.
    """
    consulta = EstoqueBiblioteca.query.filter(
        EstoqueBiblioteca.livro_id == livro_id, EstoqueBiblioteca.quantidade > 0
    )
    if biblioteca_id is not None:
        consulta = consulta.filter(EstoqueBiblioteca.biblioteca_id == biblioteca_id)
    linhas = consulta.order_by(EstoqueBiblioteca.quantidade.desc(), EstoqueBiblioteca.id).all()
    restante, alocado = quantidade, []
    for linha in linhas:
        if restante <= 0:
            break
        tirar = min(linha.quantidade, restante)
        resultado = db.session.execute(
            update(EstoqueBiblioteca)
            .where(EstoqueBiblioteca.id == linha.id, EstoqueBiblioteca.quantidade >= tirar)
            .values(quantidade=EstoqueBiblioteca.quantidade - tirar)
        )
        if resultado.rowcount != 1:
            raise ValueError("O estoque mudou enquanto você finalizava. Revise o pedido.")
        alocado.append((linha.biblioteca_id, tirar))
        restante -= tirar
    if restante > 0:
        livro = db.session.get(Livro, livro_id)
        nome = livro.titulo if livro else "livro"
        if biblioteca_id is not None:
            raise ValueError(f"A biblioteca escolhida não tem exemplares suficientes de “{nome}”.")
        raise ValueError(f"Estoque insuficiente para “{nome}”.")
    sincronizar_total(livro_id)
    return alocado


def registrar_alocacoes(transacao_id, livro_id, alocado):
    for biblioteca_id, quantidade in alocado:
        db.session.add(
            AlocacaoEstoque(
                transacao_id=transacao_id,
                biblioteca_id=biblioteca_id,
                livro_id=livro_id,
                quantidade=quantidade,
            )
        )


def devolver_alocacoes(transacao_id):
    """Devolve à estante de origem os exemplares ligados a um pedido e apaga o vínculo."""
    alocacoes = AlocacaoEstoque.query.filter_by(transacao_id=transacao_id).all()
    livros = set()
    for alocacao in alocacoes:
        linha = EstoqueBiblioteca.query.filter_by(
            biblioteca_id=alocacao.biblioteca_id, livro_id=alocacao.livro_id
        ).first()
        if linha is None:
            linha = EstoqueBiblioteca(
                biblioteca_id=alocacao.biblioteca_id, livro_id=alocacao.livro_id, quantidade=0
            )
            db.session.add(linha)
        linha.quantidade = (linha.quantidade or 0) + alocacao.quantidade
        livros.add(alocacao.livro_id)
        db.session.delete(alocacao)
    db.session.flush()
    for livro_id in livros:
        sincronizar_total(livro_id)
    return bool(alocacoes)


def aplicar_estoques_admin(livro, form):
    """Lê os campos estoque_<biblioteca_id> do formulário do admin e grava por biblioteca."""
    if livro.id is None:
        db.session.flush()
    for biblioteca in Biblioteca.query.all():
        bruto = (form.get(f"estoque_{biblioteca.id}", "") or "").strip()
        if bruto == "":
            quantidade = 0
        else:
            try:
                quantidade = int(bruto)
            except ValueError as exc:
                raise ValueError("Estoque deve ser um número inteiro.") from exc
        if quantidade < 0:
            raise ValueError("Estoque não pode ser negativo.")
        linha = EstoqueBiblioteca.query.filter_by(biblioteca_id=biblioteca.id, livro_id=livro.id).first()
        if linha is None:
            if quantidade:
                db.session.add(EstoqueBiblioteca(biblioteca_id=biblioteca.id, livro_id=livro.id, quantidade=quantidade))
        else:
            linha.quantidade = quantidade
    db.session.flush()
    sincronizar_total(livro.id)


def migrar_estoque_legado():
    """Instalações antigas tinham um estoque único por livro.

    Se ainda não há estoque por biblioteca, o total atual vai para a primeira
    biblioteca cadastrada. Depois disso o admin redistribui pelo painel.
    """
    if EstoqueBiblioteca.query.first() is not None:
        return
    primeira = Biblioteca.query.order_by(Biblioteca.id).first()
    if primeira is None:
        return
    for livro in Livro.query.filter(Livro.estoque > 0).all():
        db.session.add(EstoqueBiblioteca(biblioteca_id=primeira.id, livro_id=livro.id, quantidade=livro.estoque))
    db.session.commit()
