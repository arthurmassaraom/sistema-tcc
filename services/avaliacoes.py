from sqlalchemy import func
from database import db
from models.avaliacao import Avaliacao


def anexar_estatisticas_avaliacoes(livros):
    livros = list(livros or [])
    if not livros:
        return livros
    ids = [livro.id for livro in livros]
    resultados = (
        db.session.query(Avaliacao.livro_id, func.avg(Avaliacao.estrelas), func.count(Avaliacao.id))
        .filter(Avaliacao.livro_id.in_(ids))
        .group_by(Avaliacao.livro_id)
        .all()
    )
    estatisticas = {livro_id: (float(media), int(total)) for livro_id, media, total in resultados}
    for livro in livros:
        media, total = estatisticas.get(livro.id, (0.0, 0))
        livro._media_avaliacao = round(media, 2)
        livro._total_avaliacoes = total
    return livros
