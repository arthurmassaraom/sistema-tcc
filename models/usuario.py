from werkzeug.security import generate_password_hash, check_password_hash
import unicodedata
from sqlalchemy import Index
from database import db


class Usuario(db.Model):
    __tablename__ = "usuarios"
    __table_args__ = (Index("uq_usuarios_google_sub", "google_sub", unique=True),)
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    google_sub = db.Column(db.String(255), nullable=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.String(20), nullable=False, default="cliente")
    cpf = db.Column(db.String(14), nullable=True)
    telefone = db.Column(db.String(30), nullable=True)
    plano_id = db.Column(db.Integer, db.ForeignKey("planos.id"), nullable=True)
    foto = db.Column(db.String(80), nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    notif_pedido = db.Column(db.Boolean, nullable=False, default=True)
    notif_devolucao = db.Column(db.Boolean, nullable=False, default=True)
    notif_retirada = db.Column(db.Boolean, nullable=False, default=True)
    termos_versao_aceita = db.Column(db.String(24), nullable=True)
    consentimento_versao = db.Column(db.String(24), nullable=True)
    consentimento_em = db.Column(db.DateTime, nullable=True)
    senha_definida = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    transacoes = db.relationship("Transacao", back_populates="usuario", lazy=True)
    doacoes = db.relationship("Doacao", back_populates="usuario", lazy=True)
    avaliacoes = db.relationship(
        "Avaliacao",
        back_populates="usuario",
        cascade="all, delete-orphan",
        lazy="select",
    )
    plano = db.relationship("Plano", back_populates="usuarios")
    enderecos = db.relationship(
        "Endereco", back_populates="usuario", cascade="all, delete-orphan", lazy="select"
    )

    @property
    def is_admin(self):
        """Reconhece nomes de papel administrativos das versões atuais e antigas."""
        raw_role = (self.papel or "").strip().casefold()
        role = unicodedata.normalize("NFKD", raw_role).encode("ascii", "ignore").decode("ascii")
        return role in {
            "admin",
            "administrador",
            "administradora",
            "bibliotecario",
            "bibliotecaria",
        }

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha):
        if not self.senha_hash or not isinstance(senha, str):
            return False
        try:
            return check_password_hash(self.senha_hash, senha)
        except (TypeError, ValueError):
            return False
