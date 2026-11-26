from database import db


class Livro(db.Model):
    __tablename__ = "livros"
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False, index=True)
    autor = db.Column(db.String(160), nullable=False, index=True)
    editora = db.Column(db.String(120), default="")
    ano = db.Column(db.Integer, nullable=True)
    isbn = db.Column(db.String(30), unique=True, nullable=True, index=True)
    genero = db.Column(db.String(80), nullable=False, default="Geral", index=True)
    categoria = db.Column(db.String(100), nullable=False, default="Geral", index=True)
    modalidade = db.Column(db.String(20), nullable=False, default="Ambos")
    estoque = db.Column(db.Integer, nullable=False, default=0)
    preco_venda = db.Column(db.Float, nullable=False, default=0)
    preco_aluguel = db.Column(db.Float, nullable=False, default=0)
    resumo = db.Column(
        db.Text,
        nullable=False,
        default="Uma leitura selecionada pelo acervo comunitário.",
    )
    # Legado: mantido por compatibilidade do schema, nunca utilizado como nota exibida.
    avaliacao = db.Column(db.Float, nullable=False, default=0)
    capa_arquivo = db.Column(db.String(120), nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True, index=True)
    criado_em = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    transacoes = db.relationship("Transacao", back_populates="livro", lazy=True)
    avaliacoes = db.relationship(
        "Avaliacao",
        back_populates="livro",
        cascade="all, delete-orphan",
        lazy="select",
    )

    @property
    def media_avaliacao(self):
        if not getattr(self, "_media_avaliacao", None):
            return 0.0
        return self._media_avaliacao

    @property
    def total_avaliacoes(self):
        return getattr(self, "_total_avaliacoes", 0)
