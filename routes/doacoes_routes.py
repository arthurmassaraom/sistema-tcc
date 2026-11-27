from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func

from database import db
from models.biblioteca import Biblioteca
from models.doacao import Doacao
from models.livro import Livro
from models.usuario import Usuario

doacoes_bp = Blueprint("doacoes", __name__)

CONSERVACOES = ("Como novo", "Boa", "Usado", "Precisa de reparos")


@doacoes_bp.route("/doe", methods=["GET", "POST"])
def doe():
    usuario_id = session.get("usuario_id")
    usuario = db.session.get(Usuario, usuario_id) if usuario_id else None
    if usuario_id and not usuario:
        session.pop("usuario_id", None)
    bibliotecas = Biblioteca.query.order_by(Biblioteca.nome).all()
    if request.method == "POST":
        if not usuario:
            flash("Entre na sua conta para registrar uma doação.", "erro")
            return redirect(url_for("usuarios.login", next=url_for("doacoes.doe")))
        titulo = request.form.get("titulo", "").strip()
        autor = request.form.get("autor", "").strip()
        editora = request.form.get("editora", "").strip()
        isbn = request.form.get("isbn", "").strip() or None
        entrega = request.form.get("biblioteca_entrega", "").strip()
        conservacao = request.form.get("conservacao", "Boa").strip()
        ano_raw = request.form.get("ano", "").strip()
        biblioteca = Biblioteca.query.filter_by(nome=entrega).first()
        try:
            ano = int(ano_raw) if ano_raw else None
        except ValueError:
            ano = -1
        erros = {}
        if not titulo or len(titulo) > 200:
            erros["titulo"] = "Informe o título (até 200 caracteres)."
        if not autor or len(autor) > 160:
            erros["autor"] = "Informe o autor (até 160 caracteres)."
        if len(editora) > 120:
            erros["editora"] = "A editora deve ter até 120 caracteres."
        if isbn is not None and len(isbn) > 30:
            erros["isbn"] = "O ISBN deve ter até 30 caracteres."
        if conservacao not in CONSERVACOES:
            erros["conservacao"] = "Escolha o estado de conservação."
        if ano is not None and not 1000 <= ano <= date.today().year + 5:
            erros["ano"] = "Informe um ano válido."
        if not biblioteca:
            erros["biblioteca_entrega"] = "Escolha a unidade parceira para a entrega."
        if erros:
            flash("Revise os dados do livro, o ano e a unidade parceira selecionada.", "erro")
            return render_template(
                "doe.html",
                minhas=_minhas(usuario.id),
                bibliotecas=bibliotecas,
                erros=erros,
                form=request.form,
                conservacoes=CONSERVACOES,
                impacto=_impacto(),
            ), 400
        doacao = Doacao(
            titulo=titulo,
            autor=autor,
            editora=editora,
            ano=ano,
            isbn=isbn,
            conservacao=conservacao,
            biblioteca_entrega=entrega,
            usuario_id=usuario.id,
        )
        try:
            db.session.add(doacao)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Não foi possível registrar a doação. Tente novamente.", "erro")
        else:
            flash("Doação enviada para análise da equipe.", "sucesso")
            return redirect(url_for("doacoes.doe", enviada=doacao.id) + "#confirmacao")
    enviada = None
    if usuario and request.args.get("enviada", "").isdigit():
        enviada = Doacao.query.filter_by(
            id=int(request.args["enviada"]), usuario_id=usuario.id
        ).first()
    return render_template(
        "doe.html",
        minhas=_minhas(usuario.id) if usuario else [],
        bibliotecas=bibliotecas,
        erros={},
        form={},
        conservacoes=CONSERVACOES,
        enviada=enviada,
        impacto=_impacto(),
    )


def _minhas(usuario_id):
    return Doacao.query.filter_by(usuario_id=usuario_id).order_by(Doacao.criada_em.desc()).all()


def _impacto():
    """Números reais da curadoria (sem dados pessoais)."""
    por_status = dict(
        db.session.query(Doacao.status, func.count(Doacao.id)).group_by(Doacao.status).all()
    )
    return {
        "recebidas": sum(por_status.values()),
        "aprovadas": por_status.get("Aprovada", 0),
        "em_analise": por_status.get("Aguardando Análise", 0),
        "recusadas": por_status.get("Recusada", 0),
    }


@doacoes_bp.get("/doacoes/transparencia")
def transparencia():
    """Transparência: livros recebidos e ações da curadoria, sem identificar doadores."""
    impacto = _impacto()
    aprovadas = (
        Doacao.query.filter_by(status="Aprovada").order_by(Doacao.criada_em.desc()).limit(24).all()
    )
    titulos_aprovados = {d.titulo for d in aprovadas}
    no_acervo = {
        livro.titulo: livro
        for livro in Livro.query.filter(
            Livro.titulo.in_(titulos_aprovados), Livro.ativo.is_(True)
        ).all()
    } if titulos_aprovados else {}
    por_unidade = (
        db.session.query(Doacao.biblioteca_entrega, func.count(Doacao.id))
        .group_by(Doacao.biblioteca_entrega)
        .order_by(func.count(Doacao.id).desc())
        .limit(6)
        .all()
    )
    por_conservacao = (
        db.session.query(Doacao.conservacao, func.count(Doacao.id))
        .group_by(Doacao.conservacao)
        .all()
    )
    return render_template(
        "transparencia.html",
        impacto=impacto,
        aprovadas=aprovadas,
        no_acervo=no_acervo,
        por_unidade=por_unidade,
        por_conservacao=dict(por_conservacao),
        conservacoes=CONSERVACOES,
    )
