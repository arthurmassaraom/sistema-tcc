import re
import secrets
from datetime import date, datetime
from urllib.parse import unquote, urlsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.exc import IntegrityError
from database import db
from models.usuario import Usuario
from models.plano import Plano
from models.transacao import Transacao
from models.avaliacao import Avaliacao
from models.endereco import LIMITE_ENDERECOS
from models.interacoes import ListaDesejo, ListaEspera, Notificacao
from models.livro import Livro
from services.notificacoes import dias_para_devolver, gerar_notificacoes
from services.validacao import normalizar_email, validar_nome
from sqlalchemy.orm import joinedload

usuarios_bp = Blueprint("usuarios", __name__)


def _start_user_session(user):
    """Rotaciona os dados de autenticação sem descartar o carrinho anônimo."""
    cart = session.get("carrinho")
    session.clear()
    if isinstance(cart, dict) and cart:
        session["carrinho"] = cart
    session["usuario_id"] = user.id


def _safe_local_destination(destination):
    """Aceita somente caminhos locais absolutos, sem ambiguidades de URL."""
    if not destination or not isinstance(destination, str):
        return False
    decoded = unquote(destination)
    if any(ord(char) < 32 for char in decoded) or "\\" in decoded:
        return False
    if not decoded.startswith("/") or decoded.startswith("//"):
        return False
    parsed = urlsplit(decoded)
    return (
        parsed.scheme == ""
        and parsed.netloc == ""
        and parsed.path.startswith("/")
        and not parsed.path.startswith("//")
    )


@usuarios_bp.route("/login", methods=["GET", "POST"])
def login():
    login_error = None
    login_email = ""
    cadastro_erros = {}
    cadastro_form = {}
    if request.method == "POST":
        acao = request.form.get("acao", "login")
        email = request.form.get("email", "").strip().casefold()
        login_email = email
        senha = request.form.get("senha", "")
        if acao == "cadastro":
            cadastro_form = {"nome": request.form.get("nome", ""), "email": email}
            nome, erro_nome = validar_nome(request.form.get("nome", ""), completo=True)
            email_ok, erro_email = normalizar_email(email)
            if erro_nome:
                cadastro_erros["nome"] = erro_nome
            if erro_email:
                cadastro_erros["email"] = erro_email
            if not 8 <= len(senha) <= 128:
                cadastro_erros["senha"] = "A senha precisa ter entre 8 e 128 caracteres."
            if request.form.get("termos_aceitos") not in ("1", "true", "on"):
                cadastro_erros["termos_aceitos"] = "Aceite os Termos e Condições para criar a conta."
            if request.form.get("consentimento_dados") not in ("1", "true", "on"):
                cadastro_erros["consentimento_dados"] = (
                    "Autorize o tratamento dos dados para criarmos sua conta."
                )
            if not cadastro_erros and Usuario.query.filter(
                db.func.lower(Usuario.email) == email_ok
            ).first():
                cadastro_erros["email"] = "Não foi possível criar a conta com este e-mail. Se já tem cadastro, entre."
            if cadastro_erros:
                flash("Não foi possível criar a conta com os dados informados.", "erro")
            else:
                usuario = Usuario(nome=nome, email=email_ok)
                usuario.set_senha(senha)
                usuario.termos_versao_aceita = current_app.config.get("TERMS_VERSION")
                usuario.consentimento_versao = current_app.config.get("PRIVACY_VERSION")
                usuario.consentimento_em = datetime.utcnow()
                db.session.add(usuario)
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash("Não foi possível criar a conta com os dados informados.", "erro")
                else:
                    _start_user_session(usuario)
                    flash(f"Boas-vindas, {nome.split()[0]}! Sua conta foi criada.", "sucesso")
                    return redirect(url_for("usuarios.perfil"))
        else:
            # Também permite entrar em contas antigas cujo e-mail foi salvo com letras maiúsculas.
            usuario = Usuario.query.filter(db.func.lower(Usuario.email) == email).first()
            if usuario and usuario.ativo is not False and usuario.verificar_senha(senha):
                _start_user_session(usuario)
                if usuario.is_admin:
                    return redirect(url_for("admin.dashboard"))
                destino = request.args.get("next", "")
                if not _safe_local_destination(destino):
                    destino = url_for("usuarios.perfil")
                return redirect(destino)
            login_error = "E-mail ou senha inválidos."
    aba = "cadastro" if cadastro_erros or request.args.get("aba") == "cadastro" else "entrar"
    return render_template(
        "login.html",
        login_error=login_error,
        login_email=login_email,
        cadastro_erros=cadastro_erros,
        cadastro_form=cadastro_form,
        aba=aba,
    ), (400 if cadastro_erros else 200)


@usuarios_bp.get("/login/google")
def google_login():
    google = current_app.extensions.get("google_oauth")
    if not google:
        flash("O acesso com Google ainda não está configurado.", "erro")
        return redirect(url_for("usuarios.login"))

    destination = request.args.get("next", "")
    session["google_login_next"] = destination if _safe_local_destination(destination) else ""
    session["google_vincular"] = bool(request.args.get("vincular") and session.get("usuario_id"))
    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI") or url_for(
        "usuarios.google_callback", _external=True
    )
    parsed_redirect = urlsplit(redirect_uri)
    is_production = current_app.config.get("APP_ENV") in {"production", "prod"}
    if not parsed_redirect.netloc or parsed_redirect.scheme not in {"http", "https"}:
        session.pop("google_login_next", None)
        flash("A URL de retorno do login Google está inválida.", "erro")
        return redirect(url_for("usuarios.login"))
    if is_production and parsed_redirect.scheme != "https":
        session.pop("google_login_next", None)
        flash("O login Google em produção exige um redirect URI HTTPS.", "erro")
        return redirect(url_for("usuarios.login"))
    try:
        return google.authorize_redirect(redirect_uri, prompt="select_account")
    except Exception:
        session.pop("google_login_next", None)
        current_app.logger.exception("Não foi possível iniciar o login OIDC Google.")
        flash("Não foi possível iniciar o acesso com Google. Tente novamente.", "erro")
        return redirect(url_for("usuarios.login"))


@usuarios_bp.get("/login/google/callback")
def google_callback():
    google = current_app.extensions.get("google_oauth")
    if not google:
        flash("O acesso com Google ainda não está configurado.", "erro")
        return redirect(url_for("usuarios.login"))
    if request.args.get("error"):
        session.pop("google_login_next", None)
        flash("O acesso com Google foi cancelado ou não foi autorizado.", "erro")
        return redirect(url_for("usuarios.login"))

    try:
        token = google.authorize_access_token()
        profile = token.get("userinfo")
        if not isinstance(profile, dict):
            raise ValueError("A resposta OIDC não contém userinfo validado.")
    except Exception:
        session.pop("google_login_next", None)
        current_app.logger.warning("A resposta OIDC Google não pôde ser validada.", exc_info=True)
        flash("Não foi possível validar sua conta Google. Tente novamente.", "erro")
        return redirect(url_for("usuarios.login"))

    subject = profile.get("sub")
    email = profile.get("email")
    email_verified = profile.get("email_verified") is True
    if (
        not isinstance(subject, str)
        or not subject
        or len(subject) > 255
        or not isinstance(email, str)
        or len(email) > 160
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        or not email_verified
    ):
        session.pop("google_login_next", None)
        flash("A conta Google não forneceu uma identidade e um e-mail verificado válidos.", "erro")
        return redirect(url_for("usuarios.login"))

    email = email.strip().casefold()
    if session.pop("google_vincular", False) and session.get("usuario_id"):
        atual = db.session.get(Usuario, session["usuario_id"])
        outro = Usuario.query.filter_by(google_sub=subject).first()
        session.pop("google_login_next", None)
        if not atual:
            return redirect(url_for("usuarios.login"))
        if outro and outro.id != atual.id:
            flash("Esta conta Google já está vinculada a outro cadastro.", "erro")
        else:
            atual.google_sub = subject
            db.session.commit()
            flash("Conta Google vinculada. Agora você pode entrar com ela.", "sucesso")
        return redirect(url_for("usuarios.perfil", aba="dados"))
    google_domain = profile.get("hd")
    google_is_authoritative = email.endswith("@gmail.com") or (
        isinstance(google_domain, str) and bool(google_domain.strip())
    )
    usuario = Usuario.query.filter_by(google_sub=subject).first()
    if usuario is None:
        usuario = Usuario.query.filter(db.func.lower(Usuario.email) == email).first()
        if usuario:
            if usuario.google_sub and usuario.google_sub != subject:
                session.pop("google_login_next", None)
                flash(
                    "Este e-mail já está associado a outra identidade Google. "
                    "Entre com o método já cadastrado.",
                    "erro",
                )
                return redirect(url_for("usuarios.login"))
            if not usuario.google_sub and not google_is_authoritative:
                session.pop("google_login_next", None)
                flash(
                    "Já existe uma conta com este e-mail. Por segurança, entre nela "
                    "com o método de acesso já cadastrado.",
                    "erro",
                )
                return redirect(url_for("usuarios.login"))
            usuario.google_sub = subject
        else:
            name = profile.get("name")
            if not isinstance(name, str) or not name.strip():
                name = email.split("@", 1)[0]
            usuario = Usuario(nome=name.strip()[:120], email=email, google_sub=subject)
            usuario.set_senha(secrets.token_urlsafe(48))
            usuario.senha_definida = False
            db.session.add(usuario)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            usuario = Usuario.query.filter_by(google_sub=subject).first()
            if not usuario:
                session.pop("google_login_next", None)
                flash(
                    "Não foi possível associar essa conta Google a um cadastro.",
                    "erro",
                )
                return redirect(url_for("usuarios.login"))

    destination = session.pop("google_login_next", "")
    _start_user_session(usuario)
    if usuario.is_admin:
        return redirect(url_for("admin.dashboard"))
    if _safe_local_destination(destination):
        return redirect(destination)
    return redirect(url_for("usuarios.perfil"))


@usuarios_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.home"))


ABAS_PERFIL = ("pedidos", "favoritos", "avaliacoes", "enderecos", "dados", "preferencias")


@usuarios_bp.get("/perfil")
def perfil():
    if not session.get("usuario_id"):
        flash("Entre na sua conta para acessar o perfil.", "erro")
        return redirect(url_for("usuarios.login", next=url_for("usuarios.perfil")))
    usuario = db.session.get(Usuario, session["usuario_id"])
    if usuario is None:
        session.pop("usuario_id", None)
        flash("Sua sessão expirou. Entre novamente.", "erro")
        return redirect(url_for("usuarios.login", next=url_for("usuarios.perfil")))
    gerar_notificacoes(usuario)
    transacoes = (
        Transacao.query.options(joinedload(Transacao.livro), joinedload(Transacao.biblioteca))
        .filter_by(usuario_id=usuario.id)
        .order_by(Transacao.data_transacao.desc(), Transacao.id.desc())
        .all()
    )
    hoje = date.today()
    multas = sum(
        tx.multa if tx.status != "ativa" else tx.calcular_multa()
        for tx in transacoes
        if tx.tipo == "aluguel"
    )
    ativos = [
        tx
        for tx in transacoes
        if tx.tipo == "aluguel" and tx.status == "ativa" and tx.pagamento_status == "approved"
    ]
    prazos = {tx.id: dias_para_devolver(tx, hoje) for tx in ativos}
    favoritos = (
        ListaDesejo.query.options(joinedload(ListaDesejo.livro))
        .filter_by(usuario_id=usuario.id)
        .order_by(ListaDesejo.criado_em.desc())
        .all()
    )
    espera = (
        ListaEspera.query.options(joinedload(ListaEspera.livro))
        .filter_by(usuario_id=usuario.id, notificado_em=None)
        .all()
    )
    avaliacoes = (
        Avaliacao.query.options(joinedload(Avaliacao.livro))
        .filter_by(usuario_id=usuario.id)
        .order_by(Avaliacao.criada_em.desc())
        .all()
    )
    avaliados = {a.livro_id for a in avaliacoes}
    para_avaliar = []
    vistos = set()
    for tx in transacoes:
        if (
            tx.pagamento_status == "approved"
            and tx.status in ("ativa", "concluida", "devolvida")
            and tx.livro_id not in avaliados
            and tx.livro_id not in vistos
            and tx.livro
        ):
            para_avaliar.append(tx.livro)
            vistos.add(tx.livro_id)
    notificacoes = (
        Notificacao.query.filter_by(usuario_id=usuario.id)
        .order_by(Notificacao.lida, Notificacao.criada_em.desc())
        .limit(12)
        .all()
    )
    aba = request.args.get("aba", "pedidos")
    if aba not in ABAS_PERFIL:
        aba = "pedidos"
    sugestoes = []
    if not transacoes or not favoritos:
        sugestoes = (
            Livro.query.filter(Livro.ativo.is_(True), Livro.estoque > 0)
            .order_by(db.func.random())
            .limit(4)
            .all()
        )
    return render_template(
        "perfil.html",
        usuario=usuario,
        transacoes=transacoes,
        multas=multas,
        ativos=ativos,
        prazos=prazos,
        favoritos=favoritos,
        espera=espera,
        avaliacoes=avaliacoes,
        para_avaliar=para_avaliar[:6],
        enderecos=sorted(usuario.enderecos, key=lambda e: (not e.padrao, e.id)),
        limite_enderecos=LIMITE_ENDERECOS,
        notificacoes=notificacoes,
        nao_lidas=sum(1 for n in notificacoes if not n.lida),
        aba=aba,
        sugestoes=sugestoes,
        google_ativo=bool(current_app.config.get("GOOGLE_LOGIN_ENABLED")),
        mapas_ativos=bool(current_app.config.get("GOOGLE_MAPS_API_KEY")),
        hoje=hoje,
    )


@usuarios_bp.post("/planos/<int:plano_id>/contratar")
def contratar(plano_id):
    if not session.get("usuario_id"):
        return redirect(url_for("usuarios.login", next=url_for("main.planos")))
    usuario = db.session.get(Usuario, session["usuario_id"])
    if usuario is None:
        session.pop("usuario_id", None)
        flash("Sua sessão expirou. Entre novamente.", "erro")
        return redirect(url_for("usuarios.login"))
    if usuario.is_admin:
        return redirect(url_for("admin.dashboard"))
    plano = db.session.get(Plano, plano_id)
    if not plano:
        flash("Plano não encontrado.", "erro")
    else:
        usuario.plano_id = plano.id
        db.session.commit()
        flash(f"Plano {plano.nome} ativado (demonstração, sem cobrança).", "sucesso")
    return redirect(url_for("main.planos"))
