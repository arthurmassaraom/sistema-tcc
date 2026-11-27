from database import db

LIMITE_ENDERECOS = 3


class Endereco(db.Model):
    """Endereço salvo pelo usuário (até três, com um padrão)."""

    __tablename__ = "enderecos"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rotulo = db.Column(db.String(40), nullable=False, default="Casa")
    cep = db.Column(db.String(9), nullable=False)
    logradouro = db.Column(db.String(160), nullable=False)
    numero = db.Column(db.String(20), nullable=True)
    sem_numero = db.Column(db.Boolean, nullable=False, default=False)
    complemento = db.Column(db.String(80), nullable=True)
    bairro = db.Column(db.String(100), nullable=False)
    cidade = db.Column(db.String(100), nullable=False)
    uf = db.Column(db.String(2), nullable=False)
    padrao = db.Column(db.Boolean, nullable=False, default=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    location_type = db.Column(db.String(30), nullable=True)
    criado_em = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    usuario = db.relationship("Usuario", back_populates="enderecos")

    @property
    def numero_exibicao(self):
        return "s/n" if self.sem_numero or not self.numero else self.numero

    @property
    def linha(self):
        partes = [f"{self.logradouro}, {self.numero_exibicao}"]
        if self.complemento:
            partes.append(self.complemento)
        return " — ".join([", ".join(partes), self.bairro])

    def as_dict(self):
        return {
            "id": self.id,
            "rotulo": self.rotulo,
            "cep": self.cep,
            "logradouro": self.logradouro,
            "numero": self.numero or "",
            "sem_numero": bool(self.sem_numero),
            "complemento": self.complemento or "",
            "bairro": self.bairro,
            "cidade": self.cidade,
            "uf": self.uf,
            "padrao": bool(self.padrao),
        }
