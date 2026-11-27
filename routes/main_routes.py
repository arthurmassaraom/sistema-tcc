from flask import Blueprint, current_app, render_template
from sqlalchemy import and_, func

from database import db
from models.biblioteca import Biblioteca
from models.livro import Livro
from models.plano import Plano
from models.transacao import Transacao
from services.avaliacoes import anexar_estatisticas_avaliacoes

main_bp = Blueprint("main", __name__)


def _categorias(limite=6):
    """Gêneros do acervo ativo com contagem real e uma capa de exemplo."""
    linhas = (
        db.session.query(Livro.genero, func.count(Livro.id))
        .filter(Livro.ativo.is_(True))
        .group_by(Livro.genero)
        .order_by(func.count(Livro.id).desc(), Livro.genero)
        .limit(limite)
        .all()
    )
    categorias = []
    for genero, total in linhas:
        capa = (
            Livro.query.filter(
                Livro.ativo.is_(True), Livro.genero == genero, Livro.capa_arquivo.isnot(None)
            )
            .order_by(Livro.titulo)
            .first()
        )
        categorias.append({"nome": genero, "total": total, "capa": capa})
    return categorias


@main_bp.get("/")
def home():
    popular = (
        Livro.query.outerjoin(
            Transacao,
            and_(Transacao.livro_id == Livro.id, Transacao.pagamento_status == "approved"),
        )
        .filter(Livro.ativo.is_(True), Livro.estoque > 0)
        .group_by(Livro.id)
        .order_by(func.count(Transacao.id).desc(), Livro.titulo)
        .limit(9)
        .all()
    )
    hero = popular[0] if popular else Livro.query.filter_by(ativo=True).first()
    activity = (
        Transacao.query.filter_by(livro_id=hero.id, pagamento_status="approved").count()
        if hero
        else 0
    )
    novidades = (
        Livro.query.filter(Livro.ativo.is_(True), Livro.estoque > 0)
        .order_by(Livro.criado_em.desc(), Livro.id.desc())
        .limit(4)
        .all()
    )
    alugados = (
        Livro.query.filter_by(ativo=True)
        .filter(Livro.estoque > 0)
        .order_by(Livro.titulo)
        .limit(8)
        .all()
    )
    anexar_estatisticas_avaliacoes(([hero] if hero else []) + popular + alugados + novidades)
    totais = {
        "titulos": Livro.query.filter_by(ativo=True).count(),
        "exemplares": int(
            db.session.query(func.coalesce(func.sum(Livro.estoque), 0))
            .filter(Livro.ativo.is_(True))
            .scalar()
            or 0
        ),
        "bibliotecas": Biblioteca.query.count(),
    }
    return render_template(
        "home.html",
        hero=hero,
        atividade=activity,
        destaques=popular[1:5],
        alugados=alugados,
        novidades=novidades,
        categorias=_categorias(),
        planos=Plano.query.order_by(Plano.preco_mensal).all(),
        totais=totais,
    )


@main_bp.get("/planos")
def planos():
    return render_template("planos.html", planos=Plano.query.order_by(Plano.preco_mensal).all())


@main_bp.get("/termos")
def termos():
    return render_template("termos.html")


@main_bp.get("/privacidade")
def privacidade():
    return render_template(
        "privacidade.html", maps_ativo=bool(current_app.config.get("GOOGLE_MAPS_API_KEY"))
    )


@main_bp.get("/cookies")
def cookies():
    return render_template("cookies.html")
