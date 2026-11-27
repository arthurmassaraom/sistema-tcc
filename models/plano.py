from database import db


class Plano(db.Model):
    __tablename__ = "planos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), unique=True, nullable=False)
    preco_mensal = db.Column(db.Float, nullable=False, default=0)
    limite_alugueis = db.Column(db.Integer, nullable=False, default=1)
    beneficios = db.Column(db.Text, nullable=False, default="")
    usuarios = db.relationship("Usuario", back_populates="plano", lazy=True)
