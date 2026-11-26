import re
import click
from flask.cli import with_appcontext
from database import db
from models.usuario import Usuario


def _normalizar_email(email):
    return (email or "").strip().casefold()


def _email_valido(email):
    return len(email) <= 160 and bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))


@click.command("create-admin")
@click.option("--email", prompt=True, help="E-mail da conta administrativa")
@click.option("--nome", prompt=True, help="Nome do bibliotecário")
@with_appcontext
def create_admin(email, nome):
    """Cria uma conta administrativa com senha digitada de forma oculta."""
    email = _normalizar_email(email)
    if not _email_valido(email):
        raise click.ClickException("Informe um e-mail válido.")
    nome = (nome or "").strip()
    if not nome or len(nome) > 120:
        raise click.ClickException("Informe um nome válido com até 120 caracteres.")
    if Usuario.query.filter(db.func.lower(Usuario.email) == email).first():
        raise click.ClickException(
            "Já existe uma conta com esse e-mail. Para reaproveitá-la, use promote-admin."
        )
    senha = click.prompt("Senha (12 a 128 caracteres)", hide_input=True, confirmation_prompt=True)
    if not 12 <= len(senha) <= 128:
        raise click.ClickException("A senha precisa ter entre 12 e 128 caracteres.")
    usuario = Usuario(nome=nome.strip(), email=email, papel="admin")
    usuario.set_senha(senha)
    db.session.add(usuario)
    db.session.commit()
    click.echo("Conta administrativa criada.")


@click.command("promote-admin")
@click.option("--email", prompt=True, help="E-mail da conta existente a promover")
@with_appcontext
def promote_admin(email):
    """Promove uma conta existente e substitui a senha por uma nova senha forte."""
    email = _normalizar_email(email)
    if not _email_valido(email):
        raise click.ClickException("Informe um e-mail válido.")
    usuario = Usuario.query.filter(db.func.lower(Usuario.email) == email).first()
    if not usuario:
        raise click.ClickException(
            "Conta não encontrada. Para criar uma nova conta administrativa, use create-admin."
        )
    senha = click.prompt(
        "Nova senha administrativa (12 a 128 caracteres)",
        hide_input=True,
        confirmation_prompt=True,
    )
    if not 12 <= len(senha) <= 128:
        raise click.ClickException("A senha precisa ter entre 12 e 128 caracteres.")
    usuario.papel = "admin"
    usuario.set_senha(senha)
    db.session.commit()
    click.echo("Conta promovida a administradora e senha atualizada.")
