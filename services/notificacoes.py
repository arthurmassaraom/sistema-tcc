"""Notificações internas (exibidas no perfil). Nenhum e-mail é enviado nesta fase.

As notificações são geradas de forma idempotente a partir do estado real dos dados:
cada evento tem uma chave única por usuário, então recalcular nunca duplica avisos.
As preferências de notificação do usuário são respeitadas.
"""

from datetime import date, datetime

from flask import url_for
from sqlalchemy.exc import IntegrityError

from database import db
from models.interacoes import ListaEspera, Notificacao
from models.livro import Livro
from models.transacao import Transacao

DIAS_ALERTA_DEVOLUCAO = 2


def _criar(usuario_id, chave, tipo, titulo, mensagem, url=None):
    if Notificacao.query.filter_by(usuario_id=usuario_id, chave=chave).first():
        return False
    db.session.add(
        Notificacao(
            usuario_id=usuario_id, chave=chave, tipo=tipo, titulo=titulo, mensagem=mensagem, url=url
        )
    )
    return True


def dias_para_devolver(tx, hoje=None):
    if not tx.data_devolucao_prevista:
        return None
    return (tx.data_devolucao_prevista - (hoje or date.today())).days


def gerar_notificacoes(usuario, hoje=None):
    """Cria avisos de devolução, retirada e lista de espera ainda não registrados."""
    hoje = hoje or date.today()
    criadas = 0
    perfil = url_for("usuarios.perfil", aba="pedidos")
    if usuario.notif_devolucao:
        ativos = Transacao.query.filter_by(
            usuario_id=usuario.id, tipo="aluguel", status="ativa", pagamento_status="approved"
        ).all()
        for tx in ativos:
            dias = dias_para_devolver(tx, hoje)
            if dias is None:
                continue
            titulo_livro = tx.livro.titulo if tx.livro else "seu livro"
            if dias < 0:
                criadas += _criar(
                    usuario.id,
                    f"atraso:{tx.id}",
                    "alerta",
                    f"Devolução de “{titulo_livro}” em atraso",
                    f"O prazo terminou em {tx.data_devolucao_prevista:%d/%m/%Y}. A multa cresce a cada dia.",
                    perfil,
                )
            elif dias <= DIAS_ALERTA_DEVOLUCAO:
                criadas += _criar(
                    usuario.id,
                    f"devolucao:{tx.id}:{tx.data_devolucao_prevista.isoformat()}",
                    "prazo",
                    f"Faltam {dias} dia(s) para devolver “{titulo_livro}”",
                    f"Devolva até {tx.data_devolucao_prevista:%d/%m/%Y} ou renove, se houver estoque.",
                    perfil,
                )
    if usuario.notif_retirada:
        prontos = Transacao.query.filter(
            Transacao.usuario_id == usuario.id,
            Transacao.modo_entrega == "retirada",
            Transacao.status_entrega.in_(["Disponível para retirada", "Aguardando retirada"]),
            Transacao.pagamento_status == "approved",
        ).all()
        for tx in prontos:
            if tx.status_entrega != "Disponível para retirada":
                continue
            unidade = tx.biblioteca.nome if tx.biblioteca else "a unidade escolhida"
            criadas += _criar(
                usuario.id,
                f"retirada:{tx.id}",
                "retirada",
                f"“{tx.livro.titulo if tx.livro else 'Seu livro'}” está pronto para retirada",
                f"Retire em {unidade}. Leve um documento com foto.",
                perfil,
            )
    if usuario.notif_pedido:
        esperas = (
            ListaEspera.query.join(Livro)
            .filter(
                ListaEspera.usuario_id == usuario.id,
                ListaEspera.notificado_em.is_(None),
                Livro.estoque > 0,
                Livro.ativo.is_(True),
            )
            .all()
        )
        for espera in esperas:
            criadas += _criar(
                usuario.id,
                f"espera:{espera.id}",
                "estoque",
                f"“{espera.livro.titulo}” voltou ao estoque",
                "O título que você pediu para acompanhar está disponível de novo.",
                url_for("livros.detalhes", livro_id=espera.livro_id),
            )
            espera.notificado_em = datetime.utcnow()
    if criadas or db.session.dirty:
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    return criadas
