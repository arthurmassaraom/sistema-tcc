import re
from datetime import date, timedelta
from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from database import db
from models.avaliacao import Avaliacao
from models.livro import Livro
from models.interacoes import ListaDesejo, ListaEspera
from models.transacao import Transacao
from services.avaliacoes import anexar_estatisticas_avaliacoes
from services.recomendacoes import mesmo_genero, quem_comprou_tambem_levou

livros_bp = Blueprint("livros", __name__)


ORDENACOES = {
    "relevancia": "Mais relevantes",
    "titulo": "Título (A–Z)",
    "autor": "Autor (A–Z)",
    "novidades": "Novidades",
    "menor_preco": "Menor preço",
    "maior_preco": "Maior preço",
}
POR_PAGINA = 12


def _isbn_digits(texto):
    """Remove hífens e espaços. Retorna os dígitos (e X final) se parecer um ISBN."""
    bruto = re.sub(r"[\s-]", "", texto or "").upper()
    return bruto if re.fullmatch(r"\d{9}[\dX]|\d{13}", bruto) else None


def _filtro_busca(q):
    termo = _like_pattern(q)
    condicoes = [
        Livro.titulo.ilike(termo, escape="\\"),
        Livro.autor.ilike(termo, escape="\\"),
        Livro.isbn.ilike(termo, escape="\\"),
    ]
    isbn = _isbn_digits(q)
    if isbn:
        normalizado = func.upper(func.replace(func.replace(Livro.isbn, "-", ""), " ", ""))
        condicoes.append(normalizado == isbn)
    return or_(*condicoes)


@livros_bp.get("/livros")
def catalogo():
    q = request.args.get("q", "").strip()[:120]
    genero = request.args.get("genero", "").strip()
    categoria = request.args.get("categoria", "").strip()
    modalidade = request.args.get("modalidade", "").strip()
    ordem = request.args.get("ordem", "relevancia")
    if ordem not in ORDENACOES:
        ordem = "relevancia"
    incluir_indisponiveis = request.args.get("indisponiveis") == "1"
    try:
        pagina = max(1, int(request.args.get("pagina", "1")))
    except ValueError:
        pagina = 1

    query = Livro.query.filter_by(ativo=True)
    if not incluir_indisponiveis:
        query = query.filter(Livro.estoque > 0)
    if q:
        query = query.filter(_filtro_busca(q))
    if genero:
        query = query.filter_by(genero=genero)
    if categoria:
        query = query.filter_by(categoria=categoria)
    if modalidade in ("Venda", "Aluguel"):
        query = query.filter(Livro.modalidade.in_([modalidade, "Ambos"]))

    preco = func.coalesce(
        func.nullif(Livro.preco_aluguel, 0), Livro.preco_venda
    )
    ordem_sql = {
        "relevancia": [(Livro.estoque > 0).desc(), Livro.titulo],
        "titulo": [Livro.titulo],
        "autor": [Livro.autor, Livro.titulo],
        "novidades": [Livro.criado_em.desc(), Livro.id.desc()],
        "menor_preco": [preco.asc(), Livro.titulo],
        "maior_preco": [preco.desc(), Livro.titulo],
    }[ordem]
    total = query.count()
    paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    pagina = min(pagina, paginas)
    livros = anexar_estatisticas_avaliacoes(
        query.order_by(*ordem_sql).offset((pagina - 1) * POR_PAGINA).limit(POR_PAGINA).all()
    )
    generos = [
        r[0]
        for r in db.session.query(Livro.genero)
        .filter_by(ativo=True)
        .distinct()
        .order_by(Livro.genero)
        .all()
    ]
    categorias = [
        r[0]
        for r in db.session.query(Livro.categoria)
        .filter_by(ativo=True)
        .distinct()
        .order_by(Livro.categoria)
        .all()
    ]
    filtros_ativos = [
        (rotulo, chave)
        for rotulo, chave, valor in (
            (f"Busca: “{q}”", "q", q),
            (f"Gênero: {genero}", "genero", genero),
            (f"Categoria: {categoria}", "categoria", categoria),
            (f"Modalidade: {modalidade}", "modalidade", modalidade),
            ("Inclui indisponíveis", "indisponiveis", incluir_indisponiveis),
        )
        if valor
    ]
    sugestoes = []
    if not livros:
        sugestoes = anexar_estatisticas_avaliacoes(
            Livro.query.filter(Livro.ativo.is_(True), Livro.estoque > 0)
            .order_by(func.random())
            .limit(4)
            .all()
        )
    return render_template(
        "livros.html",
        livros=livros,
        q=q,
        genero=genero,
        categoria=categoria,
        modalidade=modalidade,
        ordem=ordem,
        ordenacoes=ORDENACOES,
        incluir_indisponiveis=incluir_indisponiveis,
        generos=generos,
        categorias=categorias,
        total=total,
        pagina=pagina,
        paginas=paginas,
        filtros_ativos=filtros_ativos,
        sugestoes=sugestoes,
        isbn_busca=_isbn_digits(q) if q else None,
    )


def _like_pattern(term):
    """Padrão LIKE com curingas do usuário escapados (% e _ viram literais)."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@livros_bp.get("/api/livros/sugestoes")
def sugestoes():
    """Sugestões de busca do cabeçalho: até 6 títulos e 3 autores do acervo ativo."""
    q = " ".join(request.args.get("q", "").split())[:80]
    if len(q) < 2:
        return jsonify(q=q, livros=[], autores=[])
    pattern = _like_pattern(q)
    livros = (
        Livro.query.filter(Livro.ativo.is_(True))
        .filter(
            or_(
                Livro.titulo.ilike(pattern, escape="\\"),
                Livro.autor.ilike(pattern, escape="\\"),
                Livro.isbn.ilike(pattern, escape="\\"),
            )
        )
        .order_by((Livro.estoque > 0).desc(), Livro.titulo)
        .limit(6)
        .all()
    )
    autores = [
        row[0]
        for row in db.session.query(Livro.autor)
        .filter(Livro.ativo.is_(True), Livro.autor.ilike(pattern, escape="\\"))
        .distinct()
        .order_by(Livro.autor)
        .limit(3)
        .all()
    ]
    return jsonify(
        q=q,
        livros=[
            {
                "titulo": livro.titulo,
                "autor": livro.autor,
                "disponivel": livro.estoque > 0,
                "url": url_for("livros.detalhes", livro_id=livro.id),
                "capa": (
                    url_for("static", filename=f"images/{livro.capa_arquivo}")
                    if livro.capa_arquivo
                    else None
                ),
            }
            for livro in livros
        ],
        autores=[
            {"nome": autor, "url": url_for("livros.catalogo", q=autor)} for autor in autores
        ],
    )


@livros_bp.get("/livros/<int:livro_id>")
def detalhes(livro_id):
    livro = db.session.get(Livro, livro_id)
    if not livro or not livro.ativo:
        abort(404)
    anexar_estatisticas_avaliacoes([livro])
    avaliacoes = (
        Avaliacao.query.filter_by(livro_id=livro.id).order_by(Avaliacao.criada_em.desc()).all()
    )
    distribuicao = {n: 0 for n in range(5, 0, -1)}
    for review in avaliacoes:
        distribuicao[review.estrelas] = distribuicao.get(review.estrelas, 0) + 1
    usuario_id = session.get("usuario_id")
    ja_comprou = bool(
        usuario_id
        and Transacao.query.filter_by(
            usuario_id=usuario_id, livro_id=livro.id, pagamento_status="approved"
        )
        .filter(Transacao.status.in_(["ativa", "concluida", "devolvida"]))
        .first()
    )
    minha_avaliacao = (
        Avaliacao.query.filter_by(
            livro_id=livro.id,
            usuario_id=usuario_id,
        ).first()
        if usuario_id
        else None
    )
    favorito = bool(
        usuario_id and ListaDesejo.query.filter_by(usuario_id=usuario_id, livro_id=livro.id).first()
    )
    em_espera = bool(
        usuario_id
        and ListaEspera.query.filter_by(
            usuario_id=usuario_id, livro_id=livro.id, notificado_em=None
        ).first()
    )
    relacionados = anexar_estatisticas_avaliacoes(mesmo_genero(livro))
    tambem_levaram = anexar_estatisticas_avaliacoes(quem_comprou_tambem_levou(livro))
    return render_template(
        "livro_detalhe.html",
        livro=livro,
        avaliacoes=avaliacoes,
        distribuicao=distribuicao,
        pode_avaliar=ja_comprou,
        minha_avaliacao=minha_avaliacao,
        favorito=favorito,
        em_espera=em_espera,
        relacionados=relacionados,
        tambem_levaram=tambem_levaram,
    )


def _exigir_login(destino):
    if session.get("usuario_id"):
        return None
    if request.is_json or request.accept_mimetypes.best == "application/json":
        return jsonify(ok=False, mensagem="Entre na sua conta para continuar."), 401
    flash("Entre na sua conta para continuar.", "erro")
    return redirect(url_for("usuarios.login", next=destino))


@livros_bp.post("/livros/<int:livro_id>/favorito")
def favoritar(livro_id):
    destino = url_for("livros.detalhes", livro_id=livro_id)
    bloqueio = _exigir_login(destino)
    if bloqueio:
        return bloqueio
    livro = db.session.get(Livro, livro_id)
    if not livro or not livro.ativo:
        abort(404)
    usuario_id = session["usuario_id"]
    existente = ListaDesejo.query.filter_by(usuario_id=usuario_id, livro_id=livro.id).first()
    if existente:
        db.session.delete(existente)
        mensagem, favorito = f"“{livro.titulo}” saiu dos seus favoritos.", False
    else:
        db.session.add(ListaDesejo(usuario_id=usuario_id, livro_id=livro.id))
        mensagem, favorito = f"“{livro.titulo}” foi salvo nos seus favoritos.", True
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        favorito = True
    if request.is_json or request.accept_mimetypes.best == "application/json":
        return jsonify(ok=True, favorito=favorito, mensagem=mensagem)
    flash(mensagem, "sucesso")
    voltar = request.form.get("voltar", "")
    return redirect(voltar if voltar.startswith("/") and not voltar.startswith("//") else destino)


@livros_bp.post("/livros/<int:livro_id>/avise-me")
def avise_me(livro_id):
    destino = url_for("livros.detalhes", livro_id=livro_id)
    bloqueio = _exigir_login(destino)
    if bloqueio:
        return bloqueio
    livro = db.session.get(Livro, livro_id)
    if not livro or not livro.ativo:
        abort(404)
    usuario_id = session["usuario_id"]
    existente = ListaEspera.query.filter_by(usuario_id=usuario_id, livro_id=livro.id).first()
    if existente and existente.notificado_em is None:
        db.session.delete(existente)
        mensagem = "Você não será mais avisado sobre este título."
    elif livro.estoque > 0:
        mensagem = "Este título já está disponível. Adicione-o à sacola!"
    else:
        if existente:
            existente.notificado_em = None
        else:
            db.session.add(ListaEspera(usuario_id=usuario_id, livro_id=livro.id))
        mensagem = "Combinado! Avisaremos no seu perfil quando o título voltar ao estoque."
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    flash(mensagem, "sucesso")
    return redirect(destino)


@livros_bp.post("/livros/<int:livro_id>/avaliacoes")
def avaliar(livro_id):
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        flash("Entre na sua conta para avaliar esta obra.", "erro")
        return redirect(
            url_for(
                "usuarios.login",
                next=url_for("livros.detalhes", livro_id=livro_id),
            )
        )
    livro = db.session.get(Livro, livro_id)
    if not livro or not livro.ativo:
        abort(404)
    elegivel = (
        Transacao.query.filter_by(
            usuario_id=usuario_id, livro_id=livro.id, pagamento_status="approved"
        )
        .filter(Transacao.status.in_(["ativa", "concluida", "devolvida"]))
        .first()
    )
    if not elegivel:
        flash("A avaliação fica disponível após uma compra ou aluguel pago desta obra.", "erro")
        return redirect(url_for("livros.detalhes", livro_id=livro_id))
    try:
        estrelas = int(request.form.get("estrelas", "0"))
    except (ValueError, TypeError):
        estrelas = 0
    comentario = request.form.get("comentario", "").strip()
    if estrelas not in range(1, 6) or not comentario or len(comentario) > 1500:
        flash("Escolha de 1 a 5 estrelas e escreva um comentário de até 1.500 caracteres.", "erro")
        return redirect(url_for("livros.detalhes", livro_id=livro_id))
    review = Avaliacao.query.filter_by(livro_id=livro.id, usuario_id=usuario_id).first()
    if review:
        review.estrelas, review.comentario = estrelas, comentario
    else:
        db.session.add(
            Avaliacao(
                livro_id=livro.id, usuario_id=usuario_id, estrelas=estrelas, comentario=comentario
            )
        )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        review = Avaliacao.query.filter_by(livro_id=livro.id, usuario_id=usuario_id).first()
        if review is None:
            raise
        review.estrelas = estrelas
        review.comentario = comentario
        db.session.commit()
    return redirect(url_for("livros.detalhes", livro_id=livro_id) + "#avaliacoes")


@livros_bp.post("/livros/transacoes/<int:transacao_id>/devolver")
def devolver(transacao_id):
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("usuarios.login", next=url_for("usuarios.perfil")))
    tx = db.session.get(Transacao, transacao_id)
    if (
        not tx
        or tx.usuario_id != usuario_id
        or tx.tipo != "aluguel"
        or tx.status != "ativa"
        or tx.pagamento_status != "approved"
    ):
        flash("Aluguel não encontrado ou indisponível para devolução.", "erro")
        return redirect(url_for("usuarios.perfil"))
    returned_on = date.today()
    fine = tx.calcular_multa(hoje=returned_on)
    transition = db.session.execute(
        update(Transacao)
        .where(
            Transacao.id == tx.id,
            Transacao.usuario_id == usuario_id,
            Transacao.tipo == "aluguel",
            Transacao.status == "ativa",
            Transacao.pagamento_status == "approved",
        )
        .values(
            data_devolucao=returned_on,
            multa=fine,
            status="devolvida",
            estoque_debitado=False,
        )
    )
    if transition.rowcount != 1:
        db.session.rollback()
        flash("Este aluguel já foi devolvido ou não está mais disponível.", "erro")
        return redirect(url_for("usuarios.perfil"))
    db.session.execute(
        update(Livro)
        .where(Livro.id == tx.livro_id)
        .values(estoque=Livro.estoque + (tx.quantidade or 1))
    )
    db.session.commit()
    return redirect(url_for("usuarios.perfil"))


@livros_bp.post("/livros/transacoes/<int:transacao_id>/renovar")
def renovar(transacao_id):
    """Renova um aluguel ativo pelo mesmo prazo, quando há estoque livre do título."""
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("usuarios.login", next=url_for("usuarios.perfil", aba="pedidos")))
    tx = db.session.get(Transacao, transacao_id)
    destino = url_for("usuarios.perfil", aba="pedidos")
    if (
        not tx
        or tx.usuario_id != usuario_id
        or tx.tipo != "aluguel"
        or tx.status != "ativa"
        or tx.pagamento_status != "approved"
    ):
        flash("Aluguel não encontrado ou indisponível para renovação.", "erro")
        return redirect(destino)
    if not tx.livro or tx.livro.estoque <= 0:
        flash("Não há exemplares livres deste título agora, então a renovação não é possível.", "erro")
        return redirect(destino)
    if tx.data_devolucao_prevista and tx.data_devolucao_prevista < date.today():
        flash("Aluguéis em atraso não podem ser renovados. Registre a devolução.", "erro")
        return redirect(destino)
    if (tx.renovacoes or 0) >= 2:
        flash("Este aluguel já foi renovado o número máximo de vezes (2).", "erro")
        return redirect(destino)
    dias = tx.dias_aluguel or 14
    base = max(tx.data_devolucao_prevista or date.today(), date.today())
    tx.data_devolucao_prevista = base + timedelta(days=dias)
    tx.renovacoes = (tx.renovacoes or 0) + 1
    db.session.commit()
    flash(
        f"Aluguel renovado por mais {dias} dias. Nova data: {tx.data_devolucao_prevista:%d/%m/%Y}. "
        "Renovação demonstrativa, sem cobrança.",
        "sucesso",
    )
    return redirect(destino)


@livros_bp.post("/avaliacoes/<int:avaliacao_id>/remover")
def remover_avaliacao(avaliacao_id):
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("usuarios.login"))
    review = db.session.get(Avaliacao, avaliacao_id)
    if not review or review.usuario_id != usuario_id:
        abort(404)
    db.session.delete(review)
    db.session.commit()
    flash("Sua avaliação foi removida.", "sucesso")
    return redirect(url_for("usuarios.perfil", aba="avaliacoes"))
