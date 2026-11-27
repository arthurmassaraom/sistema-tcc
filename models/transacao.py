from datetime import date
from database import db


class Transacao(db.Model):
    __tablename__ = "transacoes"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    livro_id = db.Column(
        db.Integer,
        db.ForeignKey("livros.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    biblioteca_id = db.Column(
        db.Integer,
        db.ForeignKey("bibliotecas.id", ondelete="RESTRICT"),
        nullable=True,
    )
    referencia_pedido = db.Column(db.String(36), nullable=True, index=True)
    payment_attempt_key = db.Column(db.String(36), nullable=True)
    payment_id = db.Column(db.String(80), nullable=True, index=True)
    pagamento_status = db.Column(db.String(32), nullable=False, default="pending", index=True)
    estoque_debitado = db.Column(db.Boolean, nullable=False, default=False)
    termos_aceitos = db.Column(db.Boolean, nullable=False, default=False)
    termos_versao = db.Column(db.String(24), nullable=True)
    consentimento_dados = db.Column(db.Boolean, nullable=False, default=False)
    renovacoes = db.Column(db.Integer, nullable=False, default=0)
    tipo = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="aguardando_pagamento", index=True)
    status_entrega = db.Column(db.String(30), nullable=False, default="Pendente")
    quantidade = db.Column(db.Integer, nullable=False, default=1)
    dias_aluguel = db.Column(db.Integer, nullable=True)
    valor_base = db.Column(db.Float, nullable=False)
    frete = db.Column(db.Float, nullable=False, default=0)
    forma_pagamento = db.Column(db.String(30), nullable=False, default="PIX")
    modo_entrega = db.Column(db.String(30), nullable=False, default="retirada")
    nome_completo = db.Column(db.String(160), nullable=True)
    cpf = db.Column(db.String(14), nullable=True)
    email_contato = db.Column(db.String(160), nullable=True)
    telefone = db.Column(db.String(30), nullable=True)
    endereco_entrega = db.Column(db.String(300), nullable=True)
    cep_entrega = db.Column(db.String(12), nullable=True)
    cidade_entrega = db.Column(db.String(100), nullable=True)
    estado_entrega = db.Column(db.String(2), nullable=True)
    data_transacao = db.Column(db.Date, nullable=False, default=date.today)
    data_devolucao_prevista = db.Column(db.Date, nullable=True)
    data_devolucao = db.Column(db.Date, nullable=True)
    multa = db.Column(db.Float, nullable=False, default=0)
    usuario = db.relationship("Usuario", back_populates="transacoes")
    livro = db.relationship("Livro", back_populates="transacoes")
    biblioteca = db.relationship("Biblioteca", back_populates="transacoes")

    def calcular_multa(self, hoje=None):
        if self.tipo != "aluguel" or not self.data_devolucao_prevista:
            return 0.0
        referencia = self.data_devolucao or hoje or date.today()
        dias = max(0, (referencia - self.data_devolucao_prevista).days)
        teto = (
            (
                self.livro.preco_venda
                * max(
                    self.quantidade or 1,
                    1,
                )
            )
            if self.livro
            else self.valor_base
        )
        return round(min(self.valor_base * 0.10 * dias, teto), 2)
