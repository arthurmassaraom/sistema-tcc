def configure_google_oauth(app):
    """Registra OIDC Google somente quando há credenciais de cliente completas."""
    client_id = app.config.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = app.config.get("GOOGLE_CLIENT_SECRET", "").strip()
    app.config["GOOGLE_LOGIN_ENABLED"] = bool(client_id and client_secret)
    if not app.config["GOOGLE_LOGIN_ENABLED"]:
        app.extensions.pop("google_oauth", None)
        return

    from authlib.integrations.flask_client import OAuth

    oauth = OAuth(app)
    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    app.extensions["google_oauth"] = oauth.create_client("google")
