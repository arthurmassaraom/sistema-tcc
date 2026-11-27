from database import db


class Doacao(db.Model):
    __tablename__ = "doacoes"
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    autor = db.Column(db.String(160), nullable=False)
    editora = db.Column(db.String(120), default="")
    ano = db.Column(db.Integer, nullable=True)
    isbn = db.Column(db.String(30), nullable=True)
    conservacao = db.Column(db.String(50), nullable=False)
    biblioteca_entrega = db.Column(db.String(160), nullable=False)
    status = db.Column(db.String(40), nullable=False, default="Aguardando Análise", index=True)
    justificativa = db.Column(db.Text, nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    criada_em = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    usuario = db.relationship("Usuario", back_populates="doacoes")
