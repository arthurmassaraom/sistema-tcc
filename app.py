from datetime import date
import hmac
from pathlib import Path
import secrets

from flask import Flask, abort, g, redirect, request, session, url_for

from config import Config
from create_admin import create_admin, promote_admin
from database import db
from routes import register_blueprints
from seed import seed_database
from services.google_oauth import configure_google_oauth
from services.sqlite_migrations import upgrade_interface_columns, upgrade_legacy_sqlite
from services.erros import register_error_handlers
from services.ui import register_ui_helpers

SENSIVEIS = {"geo.geo_cep", "geo.distancia_biblioteca"}


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    configure_google_oauth(app)
    db.init_app(app)
    register_blueprints(app)
    app.cli.add_command(create_admin)
    app.cli.add_command(promote_admin)

    def csrf_token():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    app.jinja_env.globals["csrf_token"] = csrf_token
    register_ui_helpers(app)

    @app.before_request
    def security_and_admin_boundary():
        is_payment_webhook = request.endpoint == "pagamentos.webhook"
        if request.method == "POST" and not app.testing and not is_payment_webhook:
            expected = session.get("_csrf_token", "")
            supplied = request.form.get("_csrf_token", "") or request.headers.get(
                "X-CSRF-Token", ""
            )
            if (
                not expected
                or not supplied
                or not hmac.compare_digest(str(expected), str(supplied))
            ):
                abort(
                    400,
                    description=(
                        "A sessão do formulário expirou. Atualize a página e tente novamente."
                    ),
                )

        g.usuario = None
        user_id = session.get("usuario_id")
        if user_id:
            from models.usuario import Usuario

            # Uma única consulta por requisição; o resultado é reaproveitado pelo
            # context processor e pelas rotas. A conta é relida a cada requisição,
            # então exclusão ou desativação revogam a sessão imediatamente.
            user = db.session.get(Usuario, user_id)
            if user is None or user.ativo is False:
                session.pop("usuario_id", None)
            else:
                g.usuario = user
                if (
                    user.is_admin
                    and request.endpoint not in (None, "static", "usuarios.logout")
                    and not request.endpoint.startswith("admin.")
                    and not is_payment_webhook
                ):
                    return redirect(url_for("admin.dashboard"))
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if request.endpoint != "static":
            if _pagina_com_dados_do_usuario():
                response.headers["Cache-Control"] = "private, no-store, max-age=0"
                response.headers["Pragma"] = "no-cache"
            else:
                # Páginas públicas: o navegador pode reaproveitar, mas sempre revalida,
                # e nenhum cache compartilhado guarda a resposta (ela contém o token CSRF).
                response.headers["Cache-Control"] = "private, no-cache"
            response.headers["Vary"] = "Cookie"
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    def _pagina_com_dados_do_usuario():
        endpoint = request.endpoint or ""
        return (
            bool(session.get("usuario_id"))
            or bool(session.get("carrinho"))
            or endpoint.startswith(("admin.", "conta.", "pagamentos.", "carrinho.", "usuarios."))
            or endpoint in SENSIVEIS
        )

    @app.context_processor
    def inject_context():
        usuario = g.get("usuario")
        return {
            "usuario_atual": usuario,
            "pagamentos_habilitados": app.config.get("MP_PAYMENTS_ENABLED", False),
            "modo_demo": app.config.get("DEMO_PAYMENTS_ENABLED", False),
            "versao_termos": app.config.get("TERMS_VERSION", "2026-11"),
            "current_year": date.today().year,
            "mapas_configurados": bool(app.config.get("GOOGLE_MAPS_API_KEY")),
        }

    register_error_handlers(app)

    # Mantém a inicialização automática para instalações existentes. Deploys podem
    # desativá-la e executar migrações/seed como uma etapa explícita.
    if app.config.get("AUTO_INIT_DATABASE", True):
        with app.app_context():
            from models import (  # noqa: F401
                AlocacaoEstoque,
                Avaliacao,
                Biblioteca,
                EstoqueBiblioteca,
                Doacao,
                Endereco,
                GeoCache,
                ListaDesejo,
                ListaEspera,
                Livro,
                Notificacao,
                Plano,
                Transacao,
                Usuario,
            )

            db.create_all()
            upgrade_legacy_sqlite()
            upgrade_interface_columns()
            seed_database()
            from services.estoque import migrar_estoque_legado

            migrar_estoque_legado()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", False))
