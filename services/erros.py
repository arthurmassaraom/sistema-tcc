"""Páginas de erro com a identidade do site (HTML) ou JSON para chamadas de API."""

from flask import flash, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

MENSAGENS = {
    400: ("Não foi possível processar o pedido", "Algum dado chegou incompleto. Volte e tente novamente."),
    403: ("Acesso restrito", "Esta área exige permissões que sua conta não tem."),
    404: ("Página não encontrada", "O endereço pode ter mudado ou o livro saiu do acervo."),
    405: ("Ação não permitida", "Este endereço não aceita esse tipo de envio."),
    413: ("Arquivo grande demais", "O envio passou do tamanho máximo permitido."),
    429: ("Muitas tentativas", "Aguarde alguns instantes antes de tentar de novo."),
    500: ("Algo deu errado do nosso lado", "Já registramos a falha. Tente novamente em instantes."),
}


def _quer_json():
    return request.path.startswith("/api/") or request.is_json or (
        request.accept_mimetypes.best == "application/json"
    )


def register_error_handlers(app):
    @app.errorhandler(HTTPException)
    def http_error(exc):
        codigo = exc.code or 500
        if codigo == 413 and request.endpoint == "conta.enviar_foto":
            flash("A imagem deve ter no máximo 2 MB.", "erro")
            return redirect(url_for("usuarios.perfil", aba="dados"))
        titulo, texto = MENSAGENS.get(codigo, MENSAGENS[500 if codigo >= 500 else 400])
        sessao_expirada = codigo == 400 and "sessão do formulário expirou" in str(exc.description or "")
        if sessao_expirada:
            titulo = "Sua sessão expirou"
            texto = "Por segurança, formulários abertos por muito tempo deixam de valer. Atualize a página e envie de novo."
        if _quer_json():
            return jsonify(ok=False, error=texto, erro=texto, mensagem=texto), codigo
        return (
            render_template(
                "erro.html", codigo=codigo, titulo=titulo, texto=texto, sessao_expirada=sessao_expirada
            ),
            codigo,
        )

    @app.errorhandler(Exception)
    def erro_inesperado(exc):
        if isinstance(exc, HTTPException):
            return http_error(exc)
        app.logger.exception("Erro inesperado")
        if app.config.get("TESTING") and app.config.get("PROPAGATE_EXCEPTIONS") is not False:
            raise exc
        titulo, texto = MENSAGENS[500]
        if _quer_json():
            return jsonify(ok=False, error=texto, erro=texto), 500
        return render_template("erro.html", codigo=500, titulo=titulo, texto=texto, sessao_expirada=False), 500
