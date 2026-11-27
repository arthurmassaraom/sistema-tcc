from .main_routes import main_bp
from .livros_routes import livros_bp
from .doacoes_routes import doacoes_bp
from .bibliotecas_routes import bibliotecas_bp
from .usuarios_routes import usuarios_bp
from .admin_routes import admin_bp
from .carrinho_routes import carrinho_bp
from .pagamentos_routes import pagamentos_bp
from .geo_routes import geo_bp
from .conta_routes import conta_bp


def register_blueprints(app):
    for blueprint in (
        main_bp,
        livros_bp,
        doacoes_bp,
        bibliotecas_bp,
        usuarios_bp,
        admin_bp,
        carrinho_bp,
        pagamentos_bp,
        geo_bp,
        conta_bp,
    ):
        app.register_blueprint(blueprint)
