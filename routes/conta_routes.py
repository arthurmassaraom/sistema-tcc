"""Ações da conta do usuário: foto, dados, segurança, endereços, preferências e exclusão."""

import secrets
from functools import wraps

from flask import Blueprint, current_app, flash, g, redirect, request, session, url_for
from sqlalchemy.exc import IntegrityError

from database import db
from models.avaliacao import Avaliacao
from models.endereco import LIMITE_ENDERECOS, Endereco
from models.interacoes import ListaDesejo, ListaEspera, Notificacao
from models.transacao import Transacao
from models.usuario import Usuario
from services.avatar import AvatarErro, processar_avatar, remover_arquivo
from services.email import enviar_email
from services.geo import GeoErro, consultar_viacep
from services.twofa import enviar_codigo, limpar_codigo, verificar_codigo
from services.validacao import (
    UFS,
    formatar_cep,
    formatar_telefone,
    normalizar_email,
    normalizar_texto,
    validar_cep,
    validar_nome,
    validar_numero,
    validar_telefone,
)

conta_bp = Blueprint("conta", __name__, url_prefix="/conta")
ROTULOS = ("Casa", "Trabalho", "Outro")


def login_obrigatorio(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        usuario = db.session.get(Usuario, session.get("usuario_id")) if session.get("usuario_id") else None
        if not usuario or usuario.ativo is False:
            session.pop("usuario_id", None)
            flash("Entre na sua conta para continuar.", "erro")
            return redirect(url_for("usuarios.login", next=url_for("usuarios.perfil")))
        g.conta = usuario
        return fn(*args, **kwargs)

    return wrapper


def _voltar(aba):
    return redirect(url_for("usuarios.perfil", aba=aba))


# ---------------------------------------------------------------- foto
@conta_bp.post("/foto")
@login_obrigatorio
def enviar_foto():
    usuario = g.conta
    try:
        nome = processar_avatar(request.files.get("foto"))
    except AvatarErro as exc:
        flash(str(exc), "erro")
        return _voltar("dados")
    antiga = usuario.foto
    usuario.foto = nome
    db.session.commit()
    remover_arquivo(antiga)
    flash("Foto de perfil atualizada.", "sucesso")
    return _voltar("dados")


@conta_bp.post("/foto/remover")
@login_obrigatorio
def remover_foto():
    usuario = g.conta
    antiga = usuario.foto
    usuario.foto = None
    db.session.commit()
    remover_arquivo(antiga)
    flash("Foto removida. Exibiremos suas iniciais.", "sucesso")
    return _voltar("dados")


# ---------------------------------------------------------------- dados
@conta_bp.post("/dados")
@login_obrigatorio
def atualizar_dados():
    usuario = g.conta
    nome, erro_nome = validar_nome(request.form.get("nome", ""))
    telefone_bruto = request.form.get("telefone", "").strip()
    telefone = None
    erro_tel = None
    if telefone_bruto:
        telefone, erro_tel = validar_telefone(telefone_bruto)
    if erro_nome or erro_tel:
        flash(erro_nome or erro_tel, "erro")
        return _voltar("dados")
    usuario.nome = nome
    usuario.telefone = formatar_telefone(telefone) if telefone else None
    db.session.commit()
    flash("Dados atualizados.", "sucesso")
    return _voltar("dados")


@conta_bp.post("/email")
@login_obrigatorio
def alterar_email():
    usuario = g.conta
    if usuario.google_sub:
        flash("Conta vinculada ao Google: o e-mail é o da sua conta Google e não pode ser alterado aqui.", "erro")
        return _voltar("dados")
    email, erro = normalizar_email(request.form.get("email", ""))
    if erro:
        flash(erro, "erro")
        return _voltar("dados")
    if not usuario.verificar_senha(request.form.get("senha_atual", "")):
        flash("Senha atual incorreta. O e-mail não foi alterado.", "erro")
        return _voltar("dados")
    if email == usuario.email:
        flash("Este já é o seu e-mail.", "aviso")
        return _voltar("dados")
    if Usuario.query.filter(db.func.lower(Usuario.email) == email).first():
        flash("Este e-mail já está em uso por outra conta.", "erro")
        return _voltar("dados")
    usuario.email = email
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Este e-mail já está em uso por outra conta.", "erro")
        return _voltar("dados")
    flash("E-mail alterado. Use o novo endereço no próximo acesso.", "sucesso")
    return _voltar("dados")


@conta_bp.post("/senha")
@login_obrigatorio
def alterar_senha():
    usuario = g.conta
    if usuario.google_sub:
        flash("Conta vinculada ao Google: a senha é gerenciada pelo Google e não pode ser alterada aqui.", "erro")
        return _voltar("seguranca")
    atual = request.form.get("senha_atual", "")
    nova = request.form.get("nova_senha", "")
    confirmacao = request.form.get("confirmacao", "")
    # Contas criadas pelo Google não têm senha conhecida: podem definir a primeira.
    if usuario.senha_definida is not False and not usuario.verificar_senha(atual):
        flash("Senha atual incorreta.", "erro")
        return _voltar("seguranca")
    if not 8 <= len(nova) <= 128:
        flash("A nova senha precisa ter entre 8 e 128 caracteres.", "erro")
        return _voltar("seguranca")
    if nova != confirmacao:
        flash("A confirmação não confere com a nova senha.", "erro")
        return _voltar("seguranca")
    if usuario.senha_definida is not False and usuario.verificar_senha(nova):
        flash("A nova senha deve ser diferente da atual.", "erro")
        return _voltar("seguranca")
    usuario.set_senha(nova)
    usuario.senha_definida = True
    db.session.commit()
    flash("Senha alterada com sucesso.", "sucesso")
    return _voltar("seguranca")


@conta_bp.post("/google/desvincular")
@login_obrigatorio
def desvincular_google():
    usuario = g.conta
    if not usuario.google_sub:
        return _voltar("seguranca")
    if usuario.senha_definida is False:
        flash("Defina uma senha antes de desvincular o Google, para não perder o acesso à conta.", "erro")
        return _voltar("seguranca")
    usuario.google_sub = None
    db.session.commit()
    flash("Conta Google desvinculada. Entre com e-mail e senha.", "sucesso")
    return _voltar("seguranca")


# ---------------------------------------------------------------- 2FA
# Ativar e desativar usam só o código enviado ao e-mail: quem recebe o código é o dono da conta.

@conta_bp.post("/2fa/ativar")
@login_obrigatorio
def ativar_2fa():
    usuario = g.conta
    if usuario.two_fa_ativo:
        flash("A verificação em duas etapas já está ativa.", "aviso")
        return _voltar("seguranca")
    if enviar_codigo(usuario, "Você começou a ativar a verificação em duas etapas. Use o código abaixo para confirmar."):
        flash(f"Enviamos um código de 6 dígitos para {usuario.email}.", "sucesso")
    else:
        flash("Não conseguimos enviar o código por e-mail. Tente novamente em instantes.", "erro")
    return _voltar("seguranca")


@conta_bp.post("/2fa/confirmar")
@login_obrigatorio
def confirmar_2fa():
    usuario = g.conta
    if usuario.two_fa_ativo:
        return _voltar("seguranca")
    ok, erro = verificar_codigo(usuario, request.form.get("codigo", ""))
    if not ok:
        flash(erro, "erro")
        return _voltar("seguranca")
    usuario.two_fa_ativo = True
    db.session.commit()
    enviar_email(
        usuario.email,
        "Verificação em duas etapas ativada",
        f"Olá, {usuario.nome.split()[0]}!\n\nA verificação em duas etapas foi ativada na sua conta. "
        "A partir de agora, enviaremos um código para este e-mail sempre que alguém entrar.\n\n"
        "Se não foi você, troque sua senha imediatamente.\n\nBiblioteca Aberta\n",
    )
    flash("Verificação em duas etapas ativada. Sua conta está mais protegida.", "sucesso")
    return _voltar("seguranca")


@conta_bp.post("/2fa/cancelar")
@login_obrigatorio
def cancelar_ativacao_2fa():
    usuario = g.conta
    if not usuario.two_fa_ativo:
        limpar_codigo(usuario)
        db.session.commit()
        flash("Ativação cancelada.", "aviso")
    return _voltar("seguranca")


@conta_bp.post("/2fa/desativar/enviar")
@login_obrigatorio
def enviar_codigo_desativacao_2fa():
    usuario = g.conta
    if not usuario.two_fa_ativo:
        return _voltar("seguranca")
    if enviar_codigo(usuario, "Você pediu para desativar a verificação em duas etapas. Use o código abaixo para confirmar."):
        flash(f"Enviamos um código de 6 dígitos para {usuario.email}.", "sucesso")
    else:
        flash("Não conseguimos enviar o código por e-mail. Tente novamente em instantes.", "erro")
    return _voltar("seguranca")


@conta_bp.post("/2fa/desativar/confirmar")
@login_obrigatorio
def confirmar_desativacao_2fa():
    usuario = g.conta
    if not usuario.two_fa_ativo:
        return _voltar("seguranca")
    ok, erro = verificar_codigo(usuario, request.form.get("codigo", ""))
    if not ok:
        flash(erro, "erro")
        return _voltar("seguranca")
    usuario.two_fa_ativo = False
    limpar_codigo(usuario)
    db.session.commit()
    enviar_email(
        usuario.email,
        "Verificação em duas etapas desativada",
        f"Olá, {usuario.nome.split()[0]}!\n\nA verificação em duas etapas foi desativada na sua conta. "
        "Se não foi você, troque sua senha e reative a proteção.\n\nBiblioteca Aberta\n",
    )
    flash("Verificação em duas etapas desativada.", "sucesso")
    return _voltar("seguranca")


# ---------------------------------------------------------------- preferências
@conta_bp.post("/preferencias")
@login_obrigatorio
def preferencias():
    usuario = g.conta
    usuario.notif_pedido = request.form.get("notif_pedido") == "1"
    usuario.notif_devolucao = request.form.get("notif_devolucao") == "1"
    usuario.notif_retirada = request.form.get("notif_retirada") == "1"
    db.session.commit()
    flash("Preferências de aviso salvas.", "sucesso")
    return _voltar("preferencias")


@conta_bp.post("/notificacoes/lidas")
@login_obrigatorio
def marcar_lidas():
    Notificacao.query.filter_by(usuario_id=g.conta.id, lida=False).update({"lida": True})
    db.session.commit()
    return redirect(request.form.get("voltar") or url_for("usuarios.perfil"))


# ---------------------------------------------------------------- endereços
def validar_endereco(form):
    """Valida o formulário de endereço. Retorna (dados, erro)."""
    cep, erro = validar_cep(form.get("cep", ""))
    if erro:
        return None, erro
    sem_numero = form.get("sem_numero") in ("1", "true", "on")
    numero, erro = validar_numero(form.get("numero", ""), sem_numero)
    if erro:
        return None, erro
    dados = {
        "cep": formatar_cep(cep),
        "logradouro": " ".join(form.get("logradouro", "").split())[:160],
        "numero": numero or None,
        "sem_numero": sem_numero,
        "complemento": " ".join(form.get("complemento", "").split())[:80] or None,
        "bairro": " ".join(form.get("bairro", "").split())[:100],
        "cidade": " ".join(form.get("cidade", "").split())[:100],
        "uf": form.get("uf", "").strip().upper(),
        "rotulo": form.get("rotulo", "Casa") if form.get("rotulo") in ROTULOS else "Casa",
    }
    if not dados["logradouro"] or not dados["bairro"] or not dados["cidade"] or dados["uf"] not in UFS:
        return None, "Preencha logradouro, bairro, cidade e UF."
    if current_app.config.get("CEP_LOOKUP_ENABLED", True):
        try:
            oficial = consultar_viacep(cep)
        except GeoErro as exc:
            if exc.codigo == "cep_inexistente":
                return None, exc.mensagem
        else:
            if oficial["estado"] != dados["uf"] or normalizar_texto(oficial["cidade"]) != normalizar_texto(dados["cidade"]):
                return None, f"O CEP pertence a {oficial['cidade']}/{oficial['estado']}. Confira cidade e UF."
    return dados, None


@conta_bp.post("/enderecos")
@login_obrigatorio
def salvar_endereco():
    usuario = g.conta
    endereco_id = request.form.get("endereco_id", "")
    endereco = None
    if endereco_id.isdigit():
        endereco = Endereco.query.filter_by(id=int(endereco_id), usuario_id=usuario.id).first()
        if not endereco:
            flash("Endereço não encontrado.", "erro")
            return _voltar("enderecos")
    elif Endereco.query.filter_by(usuario_id=usuario.id).count() >= LIMITE_ENDERECOS:
        flash(f"Você pode salvar até {LIMITE_ENDERECOS} endereços. Remova um para adicionar outro.", "erro")
        return _voltar("enderecos")
    dados, erro = validar_endereco(request.form)
    if erro:
        flash(erro, "erro")
        return _voltar("enderecos")
    novo = endereco is None
    endereco = endereco or Endereco(usuario_id=usuario.id)
    for chave, valor in dados.items():
        setattr(endereco, chave, valor)
    endereco.latitude = endereco.longitude = None
    existentes = Endereco.query.filter_by(usuario_id=usuario.id).count()
    if novo:
        db.session.add(endereco)
    if request.form.get("padrao") in ("1", "on") or existentes == 0:
        Endereco.query.filter_by(usuario_id=usuario.id).update({"padrao": False})
        endereco.padrao = True
    db.session.commit()
    flash("Endereço salvo." if novo else "Endereço atualizado.", "sucesso")
    return _voltar("enderecos")


@conta_bp.post("/enderecos/<int:endereco_id>/padrao")
@login_obrigatorio
def endereco_padrao(endereco_id):
    endereco = Endereco.query.filter_by(id=endereco_id, usuario_id=g.conta.id).first_or_404()
    Endereco.query.filter_by(usuario_id=g.conta.id).update({"padrao": False})
    endereco.padrao = True
    db.session.commit()
    flash(f"“{endereco.rotulo}” agora é o endereço padrão.", "sucesso")
    return _voltar("enderecos")


@conta_bp.post("/enderecos/<int:endereco_id>/remover")
@login_obrigatorio
def remover_endereco(endereco_id):
    endereco = Endereco.query.filter_by(id=endereco_id, usuario_id=g.conta.id).first_or_404()
    era_padrao = endereco.padrao
    db.session.delete(endereco)
    db.session.flush()
    if era_padrao:
        proximo = Endereco.query.filter_by(usuario_id=g.conta.id).order_by(Endereco.id).first()
        if proximo:
            proximo.padrao = True
    db.session.commit()
    flash("Endereço removido.", "sucesso")
    return _voltar("enderecos")


# ---------------------------------------------------------------- exclusão
@conta_bp.post("/excluir/enviar-codigo")
@login_obrigatorio
def enviar_codigo_exclusao():
    usuario = g.conta
    if not usuario.google_sub or not usuario.two_fa_ativo:
        return _voltar("preferencias")
    if enviar_codigo(usuario, "Você pediu para excluir sua conta na Biblioteca Aberta. Esta ação não pode ser desfeita. Use o código abaixo para confirmar."):
        flash(f"Enviamos um código de 6 dígitos para {usuario.email}.", "sucesso")
    else:
        flash("Não conseguimos enviar o código por e-mail. Tente novamente em instantes.", "erro")
    return _voltar("preferencias")


@conta_bp.post("/excluir")
@login_obrigatorio
def excluir_conta():
    usuario = g.conta
    if usuario.is_admin:
        flash("Contas administrativas não podem ser excluídas por aqui.", "erro")
        return _voltar("preferencias")
    if usuario.google_sub:
        # Conta vinculada ao Google não usa senha: exige 2FA ativo e o código enviado ao e-mail.
        if not usuario.two_fa_ativo:
            flash("Para excluir uma conta vinculada ao Google, ative antes a verificação em duas etapas.", "erro")
            return _voltar("seguranca")
        ok, erro = verificar_codigo(usuario, request.form.get("codigo", ""))
        if not ok:
            flash(erro, "erro")
            return _voltar("preferencias")
    elif usuario.senha_definida is False:
        confirmado = request.form.get("confirmacao", "").strip().casefold() == usuario.email
        if not confirmado:
            flash("Confirmação incorreta. Sua conta não foi excluída.", "erro")
            return _voltar("preferencias")
    elif not usuario.verificar_senha(request.form.get("senha_atual", "")):
        flash("Confirmação incorreta. Sua conta não foi excluída.", "erro")
        return _voltar("preferencias")
    pendentes = Transacao.query.filter(
        Transacao.usuario_id == usuario.id,
        db.or_(
            db.and_(Transacao.tipo == "aluguel", Transacao.status == "ativa"),
            Transacao.status == "aguardando_pagamento",
        ),
    ).count()
    if pendentes:
        flash("Devolva os aluguéis ativos e conclua os pagamentos pendentes antes de excluir a conta.", "erro")
        return _voltar("preferencias")

    # Pedidos são mantidos (obrigações fiscais e estoque), mas sem dados pessoais.
    for tx in Transacao.query.filter_by(usuario_id=usuario.id).all():
        tx.nome_completo = "Cliente anonimizado"
        tx.cpf = None
        tx.email_contato = None
        tx.telefone = None
        if tx.endereco_entrega:
            tx.endereco_entrega = "Endereço removido a pedido do titular"
        tx.cep_entrega = None
    for modelo in (Endereco, ListaDesejo, ListaEspera, Notificacao, Avaliacao):
        modelo.query.filter_by(usuario_id=usuario.id).delete()
    foto = usuario.foto
    usuario.nome = "Conta excluída"
    usuario.email = f"excluida-{usuario.id}-{secrets.token_hex(6)}@anonimizada.invalid"
    usuario.set_senha(secrets.token_urlsafe(48))
    usuario.senha_definida = False
    usuario.google_sub = None
    usuario.two_fa_ativo = False
    limpar_codigo(usuario)
    usuario.cpf = None
    usuario.telefone = None
    usuario.foto = None
    usuario.plano_id = None
    usuario.ativo = False
    usuario.consentimento_em = None
    db.session.commit()
    remover_arquivo(foto)
    session.clear()
    flash("Sua conta foi excluída e seus dados pessoais foram anonimizados.", "sucesso")
    return redirect(url_for("main.home"))
