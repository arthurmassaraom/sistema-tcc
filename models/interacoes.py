from database import db


class ListaDesejo(db.Model):
    """Livros favoritados pelo usuário."""

    __tablename__ = "lista_desejos"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    livro_id = db.Column(
        db.Integer, db.ForeignKey("livros.id", ondelete="CASCADE"), nullable=False, index=True
    )
    criado_em = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    livro = db.relationship("Livro")
    __table_args__ = (db.UniqueConstraint("usuario_id", "livro_id", name="uq_desejo_usuario_livro"),)


class ListaEspera(db.Model):
    """Pedido de aviso quando um título indisponível voltar ao estoque."""

    __tablename__ = "lista_espera"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    livro_id = db.Column(
        db.Integer, db.ForeignKey("livros.id", ondelete="CASCADE"), nullable=False, index=True
    )
    criado_em = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    notificado_em = db.Column(db.DateTime, nullable=True)
    livro = db.relationship("Livro")
    __table_args__ = (db.UniqueConstraint("usuario_id", "livro_id", name="uq_espera_usuario_livro"),)


class Notificacao(db.Model):
    """Aviso interno exibido no perfil (sem envio de e-mail nesta fase)."""

    __tablename__ = "notificacoes"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo = db.Column(db.String(30), nullable=False, default="aviso")
    titulo = db.Column(db.String(160), nullable=False)
    mensagem = db.Column(db.String(400), nullable=False, default="")
    url = db.Column(db.String(300), nullable=True)
    # Chave de deduplicação: o mesmo evento não gera dois avisos.
    chave = db.Column(db.String(120), nullable=False)
    lida = db.Column(db.Boolean, nullable=False, default=False)
    criada_em = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    __table_args__ = (db.UniqueConstraint("usuario_id", "chave", name="uq_notificacao_chave"),)


class GeoCache(db.Model):
    """Cache de geocodificação (ViaCEP + Google Geocoding) para evitar consultas repetidas."""

    __tablename__ = "geo_cache"
    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(255), nullable=False, unique=True, index=True)
    cep = db.Column(db.String(8), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    location_type = db.Column(db.String(30), nullable=True)
    endereco_formatado = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="OK")
    criado_em = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
