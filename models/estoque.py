from database import db


class EstoqueBiblioteca(db.Model):
    """Quantos exemplares de um livro estão em cada biblioteca parceira."""

    __tablename__ = "estoque_bibliotecas"
    __table_args__ = (
        db.UniqueConstraint("biblioteca_id", "livro_id", name="uq_estoque_biblioteca_livro"),
    )
    id = db.Column(db.Integer, primary_key=True)
    biblioteca_id = db.Column(db.Integer, db.ForeignKey("bibliotecas.id"), nullable=False, index=True)
    livro_id = db.Column(db.Integer, db.ForeignKey("livros.id"), nullable=False, index=True)
    quantidade = db.Column(db.Integer, nullable=False, default=0)
    biblioteca = db.relationship("Biblioteca")
    livro = db.relationship("Livro", backref=db.backref("estoques", lazy="select"))


class AlocacaoEstoque(db.Model):
    """De qual biblioteca saiu cada exemplar de um pedido (para devolver ao cancelar)."""

    __tablename__ = "alocacoes_estoque"
    id = db.Column(db.Integer, primary_key=True)
    transacao_id = db.Column(db.Integer, db.ForeignKey("transacoes.id"), nullable=False, index=True)
    biblioteca_id = db.Column(db.Integer, db.ForeignKey("bibliotecas.id"), nullable=False)
    livro_id = db.Column(db.Integer, db.ForeignKey("livros.id"), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
