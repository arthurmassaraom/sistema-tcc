"""Limite de aluguéis simultâneos definido pelo plano do usuário.

Conta as unidades de aluguel que ainda não foram devolvidas: as aguardando
pagamento (reservadas) e as ativas. Visitantes e contas sem plano usam o
limite do plano Básico (1 aluguel por vez).
"""

from sqlalchemy import func

from database import db
from models.transacao import Transacao

LIMITE_SEM_PLANO = 1
STATUS_EM_ABERTO = ("aguardando_pagamento", "ativa")


def limite_alugueis(usuario):
    if usuario is not None and usuario.plano is not None:
        return int(usuario.plano.limite_alugueis or LIMITE_SEM_PLANO)
    return LIMITE_SEM_PLANO


def alugueis_em_aberto(usuario_id):
    total = (
        db.session.query(func.coalesce(func.sum(Transacao.quantidade), 0))
        .filter(
            Transacao.usuario_id == usuario_id,
            Transacao.tipo == "aluguel",
            Transacao.status.in_(STATUS_EM_ABERTO),
        )
        .scalar()
    )
    return int(total or 0)


def mensagem_limite(limite):
    if limite <= 1:
        return "Seu plano permite 1 aluguel por vez. Devolva o livro atual ou troque de plano para alugar mais."
    return f"Seu plano permite até {limite} aluguéis simultâneos. Devolva algum livro ou troque de plano para alugar mais."
