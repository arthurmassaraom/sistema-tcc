import os
import secrets
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _is_production():
    environment = os.environ.get("APP_ENV", os.environ.get("FLASK_ENV", "development"))
    return environment.strip().lower() in {"production", "prod"}


def _secret_key():
    configured_key = os.environ.get("SECRET_KEY", "").strip()
    if configured_key:
        if len(configured_key) < 32 and _is_production():
            raise RuntimeError("SECRET_KEY precisa ter pelo menos 32 caracteres em produção.")
        return configured_key
    if _is_production():
        raise RuntimeError("Defina SECRET_KEY com um valor aleatório forte em produção.")

    key_file = BASE_DIR / "instance" / ".flask_secret_key"
    try:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        if key_file.exists():
            saved_key = key_file.read_text(encoding="utf-8").strip()
            if saved_key:
                key_file.chmod(0o600)
                return saved_key
        generated_key = secrets.token_urlsafe(48)
        descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
            secret_file.write(generated_key)
        return generated_key
    except OSError as exc:
        raise RuntimeError(
            "Não foi possível persistir a chave de sessão. Defina SECRET_KEY explicitamente."
        ) from exc


def _database_uri():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return database_url
    database_name = os.environ.get("MYSQL_DATABASE", "").strip()
    if database_name:
        try:
            port = int(os.environ.get("MYSQL_PORT", "3306"))
        except ValueError as exc:
            raise RuntimeError("MYSQL_PORT precisa ser numérico.") from exc
        return URL.create(
            drivername="mysql+pymysql",
            username=os.environ.get("MYSQL_USER", "root"),
            password=os.environ.get("MYSQL_PASSWORD", ""),
            host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
            port=port,
            database=database_name,
            query={"charset": "utf8mb4"},
        )
    return f"sqlite:///{BASE_DIR / 'instance' / 'biblioteca.db'}"


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} precisa ser true/false, yes/no, on/off ou 1/0.")


class Config:
    APP_ENV = os.environ.get("APP_ENV", os.environ.get("FLASK_ENV", "development")).strip().lower()
    SECRET_KEY = _secret_key()
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _is_production() or _env_bool("SESSION_COOKIE_SECURE", False)
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    # true (padrão): cria tabelas, aplica migrações SQLite e o seed na inicialização.
    # Em deploys, use false e execute essas etapas de forma explícita.
    AUTO_INIT_DATABASE = _env_bool("AUTO_INIT_DATABASE", True)
    # Taxa única de entrega em domicílio (fonte única para carrinho e checkout).
    DELIVERY_FEE = round(float(os.environ.get("DELIVERY_FEE", "12.90")), 2)
    TERMS_VERSION = os.environ.get("TERMS_VERSION", "2026-11")
    MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "").strip()
    MP_PUBLIC_KEY = os.environ.get("MP_PUBLIC_KEY", "").strip()
    MP_WEBHOOK_SECRET = os.environ.get("MP_WEBHOOK_SECRET", "").strip()
    MP_NOTIFICATION_URL = os.environ.get("MP_NOTIFICATION_URL", "").strip()
    PAYMENT_MODE = os.environ.get("PAYMENT_MODE", "demo").strip().lower()
    if PAYMENT_MODE not in {"demo", "mercadopago", "disabled"}:
        PAYMENT_MODE = "disabled"
    DEMO_PAYMENTS_ENABLED = PAYMENT_MODE == "demo"
    MP_PAYMENTS_ENABLED = PAYMENT_MODE == "mercadopago" and bool(MP_ACCESS_TOKEN and MP_PUBLIC_KEY)
    BUSINESS_CNPJ = os.environ.get("BUSINESS_CNPJ", "").strip()
    BUSINESS_ADDRESS = os.environ.get("BUSINESS_ADDRESS", "").strip()
    BUSINESS_PHONE = os.environ.get("BUSINESS_PHONE", "").strip()
    BUSINESS_WHATSAPP = "".join(filter(str.isdigit, os.environ.get("BUSINESS_WHATSAPP", "")))
    BUSINESS_EMAIL = os.environ.get("BUSINESS_EMAIL", "").strip()
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    GOOGLE_LOGIN_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    # Geocodificação (servidor). A chave nunca é enviada ao navegador.
    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    # Área de atendimento para entrega em domicílio: UFs e cidades separadas por vírgula.
    # Vazio = sem restrição naquele nível. Ex.: DELIVERY_STATES=SP e DELIVERY_CITIES=São Paulo
    DELIVERY_STATES = [
        uf.strip().upper()
        for uf in os.environ.get("DELIVERY_STATES", "SP").split(",")
        if uf.strip()
    ]
    DELIVERY_CITIES = [
        cidade.strip()
        for cidade in os.environ.get("DELIVERY_CITIES", "").split(",")
        if cidade.strip()
    ]
    # Distância (km) a partir da qual alertamos pino distante ou biblioteca longe.
    GEO_ALERT_KM = float(os.environ.get("GEO_ALERT_KM", "2"))
    PICKUP_ALERT_KM = float(os.environ.get("PICKUP_ALERT_KM", "15"))
    # Consulta ao ViaCEP na validação do checkout (desative apenas em testes offline).
    CEP_LOOKUP_ENABLED = _env_bool("CEP_LOOKUP_ENABLED", True)
    PRIVACY_VERSION = os.environ.get("PRIVACY_VERSION", "2026-11")
    CURRENT_YEAR = date.today().year
