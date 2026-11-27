from database import db


class Avaliacao(db.Model):
    __tablename__ = "avaliacoes_livros"
    id = db.Column(db.Integer, primary_key=True)
    livro_id = db.Column(
        db.Integer,
        db.ForeignKey("livros.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    estrelas = db.Column(db.Integer, nullable=False)
    comentario = db.Column(db.Text, nullable=False)
    criada_em = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    livro = db.relationship("Livro", back_populates="avaliacoes")
    usuario = db.relationship("Usuario", back_populates="avaliacoes")
    __table_args__ = (
        db.UniqueConstraint("livro_id", "usuario_id", name="uq_avaliacao_livro_usuario"),
        db.CheckConstraint("estrelas >= 1 AND estrelas <= 5", name="ck_avaliacao_estrelas_1_5"),
    )
