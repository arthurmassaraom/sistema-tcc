from database import db


class Biblioteca(db.Model):
    __tablename__ = "bibliotecas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False)
    cep = db.Column(db.String(12), nullable=False, index=True)
    endereco = db.Column(db.String(200), nullable=False)
    cidade = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(2), nullable=False)
    telefone = db.Column(db.String(30), default="")
    dias_funcionamento = db.Column(db.String(80), nullable=True)
    horario_abertura = db.Column(db.String(5), nullable=True)
    horario_fechamento = db.Column(db.String(5), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    transacoes = db.relationship("Transacao", back_populates="biblioteca", lazy=True)

    @property
    def horario(self):
        if not (self.horario_abertura and self.horario_fechamento):
            return None
        dias = f"{self.dias_funcionamento} · " if self.dias_funcionamento else ""
        return f"{dias}{self.horario_abertura}–{self.horario_fechamento}"

    def atende_periodo(self, periodo):
        """manha (até 12h), tarde (12h-18h) ou noite (após 18h)."""
        if not (self.horario_abertura and self.horario_fechamento):
            return False
        inicio, fim = self.horario_abertura, self.horario_fechamento
        faixas = {"manha": ("06:00", "12:00"), "tarde": ("12:00", "18:00"), "noite": ("18:00", "23:59")}
        if periodo not in faixas:
            return True
        a, b = faixas[periodo]
        return inicio < b and fim > a
