import base64
import hashlib
import io
import hmac
import math
import time
import uuid
from datetime import date, datetime, timedelta

import requests
from flask import Blueprint, current_app, jsonify, request, session, url_for
from sqlalchemy import update

from database import db
from models.biblioteca import Biblioteca
from services.estoque import debitar, devolver_alocacoes, registrar_alocacoes
from models.livro import Livro
from models.transacao import Transacao
from models.usuario import Usuario
from services.limites import alugueis_em_aberto, limite_alugueis, mensagem_limite
from services.geo import GeoErro, area_atendida, consultar_viacep
from services.validacao import (
    UFS,
    cpf_valido,
    formatar_telefone,
    logradouro_diverge,
    normalizar_email,
    normalizar_texto,
    somente_digitos,
    validar_cep,
    validar_nome,
    validar_numero,
    validar_telefone,
)

pagamentos_bp = Blueprint("pagamentos", __name__)
MP_PAYMENTS_URL = "https://api.mercadopago.com/v1/payments"


def _truthy(value):
    return value is True or str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _cpf_valido(valor):
    return cpf_valido(valor)


def _payload():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else request.form.to_dict()


def _erro(mensagem, status=400, campo=None, codigo=None):
    return None, None, (mensagem, status, campo, codigo)


def _checkout_data(payload):
    from routes.carrinho_routes import _cart_rows, frete_domicilio

    user = db.session.get(Usuario, session.get("usuario_id")) if session.get("usuario_id") else None
    if not user:
        return _erro("Entre na sua conta para finalizar o pedido.", 401)
    if user.is_admin:
        return _erro("A conta administrativa não pode fazer pedidos.", 403)
    rows, subtotal = _cart_rows()
    if not rows:
        return _erro("Seu carrinho está vazio.")

    nome, erro_nome = validar_nome(payload.get("nome_completo", ""), completo=True)
    if erro_nome:
        return _erro(erro_nome, campo="nome_completo")
    cpf = somente_digitos(payload.get("cpf", ""))
    if not cpf_valido(cpf):
        return _erro("Informe um CPF válido: confira os 11 números.", campo="cpf")
    email, erro_email = normalizar_email(payload.get("email", ""))
    if erro_email:
        return _erro(erro_email, campo="email")
    telefone_digitos, erro_tel = validar_telefone(payload.get("telefone", ""))
    if erro_tel:
        return _erro(erro_tel, campo="telefone")
    telefone = formatar_telefone(telefone_digitos)
    modo = str(payload.get("modo_entrega", ""))
    if modo not in ("domicilio", "retirada"):
        return _erro("Escolha entrega em domicílio ou retirada.", campo="modo_entrega")
    if not _truthy(payload.get("termos_aceitos")):
        return _erro("É necessário aceitar os Termos e Condições.", campo="termos_aceitos")
    if not _truthy(payload.get("consentimento_dados")):
        return _erro(
            "Autorize o tratamento dos seus dados pessoais para processarmos o pedido.",
            campo="consentimento_dados",
        )

    biblioteca = None
    endereco = cep = cidade = estado = None
    if modo == "domicilio":
        cep, erro_cep = validar_cep(payload.get("cep", ""))
        if erro_cep:
            return _erro(erro_cep, campo="cep")
        logradouro = " ".join(str(payload.get("logradouro", "")).split())[:160]
        sem_numero = _truthy(payload.get("sem_numero"))
        numero, erro_numero = validar_numero(payload.get("numero", ""), sem_numero)
        if erro_numero:
            return _erro(erro_numero, campo="numero")
        complemento = (
            ""
            if _truthy(payload.get("sem_complemento"))
            else " ".join(str(payload.get("complemento", "")).split())[:80]
        )
        bairro = " ".join(str(payload.get("bairro", "")).split())[:100]
        cidade = " ".join(str(payload.get("cidade", "")).split())[:100]
        estado = str(payload.get("estado", "")).strip().upper()
        if not logradouro or not bairro or not cidade or estado not in UFS:
            return _erro("Preencha CEP e todos os campos obrigatórios do endereço.", campo="logradouro")
        if current_app.config.get("CEP_LOOKUP_ENABLED", True):
            try:
                oficial = consultar_viacep(cep)
            except GeoErro as exc:
                if exc.codigo == "cep_inexistente":
                    return _erro(exc.mensagem, campo="cep")
                current_app.logger.warning("ViaCEP indisponível; CEP validado apenas pelo formato.")
            else:
                if oficial["estado"] != estado or normalizar_texto(oficial["cidade"]) != normalizar_texto(cidade):
                    return _erro(
                        f"O CEP informado pertence a {oficial['cidade']}/{oficial['estado']}. Confira cidade e UF.",
                        campo="cep",
                    )
                if (
                    oficial["logradouro"]
                    and logradouro_diverge(logradouro, oficial["logradouro"])
                    and not _truthy(payload.get("confirmar_logradouro"))
                ):
                    return _erro(
                        f"O CEP corresponde a “{oficial['logradouro']}”, mas você digitou “{logradouro}”. "
                        "Confirme o logradouro para continuar.",
                        409,
                        campo="logradouro",
                        codigo="logradouro_divergente",
                    )
        atendido, motivo = area_atendida(cidade, estado)
        if not atendido:
            return _erro(motivo, campo="cep", codigo="fora_da_area")
        endereco = (
            f"{logradouro}, {numero or 's/n'}"
            + (f", {complemento}" if complemento else "")
            + f" — {bairro}"
        )
        cep = cep
    else:
        try:
            biblioteca = db.session.get(Biblioteca, int(payload.get("biblioteca_id", "")))
        except (ValueError, TypeError):
            biblioteca = None
        if not biblioteca:
            return _erro("Escolha uma biblioteca parceira válida para retirada.", campo="biblioteca_id")
        cidade, estado = biblioteca.cidade, biblioteca.estado

    frete = frete_domicilio() if modo == "domicilio" else 0.0
    data = {
        "nome": nome,
        "cpf": cpf,
        "email": email,
        "telefone": telefone,
        "modo": modo,
        "biblioteca": biblioteca,
        "endereco": endereco,
        "cep": cep,
        "cidade": cidade,
        "estado": estado,
        "frete": frete,
        "termos_aceitos": True,
        "consentimento_dados": True,
    }
    return (user, rows, subtotal, data), None, None


def _erro_json(error):
    mensagem, status = error[0], error[1]
    corpo = {"ok": False, "error": mensagem}
    if len(error) > 2 and error[2]:
        corpo["campo"] = error[2]
    if len(error) > 3 and error[3]:
        corpo["codigo"] = error[3]
    return jsonify(corpo), status


def _make_or_reuse_order(user, rows, data, forma_pagamento):
    user = Usuario.query.filter_by(id=user.id).with_for_update().first()
    if not user:
        raise ValueError("A sessão do usuário expirou. Entre novamente.")
    reference = session.get("checkout_reference") or str(uuid.uuid4())
    session["checkout_reference"] = reference
    existentes = Transacao.query.filter_by(referencia_pedido=reference, usuario_id=user.id).all()
    if existentes:
        if any(tx.forma_pagamento != forma_pagamento for tx in existentes):
            raise ValueError(
                "Já existe uma tentativa deste pedido com outra forma de pagamento. Consulte o status antes de tentar novamente."
            )
        return reference, existentes

    alugando = sum(row["quantidade"] for row in rows if row["tipo"] == "aluguel")
    limite = limite_alugueis(user)
    if alugando and alugueis_em_aberto(user.id) + alugando > limite:
        raise ValueError(mensagem_limite(limite))

    try:
        # Retirada tira da biblioteca escolhida; domicílio tira das bibliotecas com estoque.
        biblioteca_escolhida = data["biblioteca"].id if data["biblioteca"] else None
        alocacoes_por_linha = []
        for row in rows:
            if not row["livro"].ativo:
                raise ValueError(f"“{row['livro'].titulo}” não está mais disponível.")
            alocacoes_por_linha.append(
                debitar(row["livro"].id, row["quantidade"], biblioteca_id=biblioteca_escolhida)
            )

        user.nome, user.email, user.cpf, user.telefone = (
            data["nome"],
            data["email"],
            data["cpf"],
            data["telefone"],
        )
        user.termos_versao_aceita = current_app.config.get("TERMS_VERSION", "2026-11")
        user.consentimento_versao = current_app.config.get("PRIVACY_VERSION", "2026-11")
        user.consentimento_em = datetime.utcnow()
        for index, row in enumerate(rows):
            rent = row["tipo"] == "aluguel"
            tx = Transacao(
                usuario_id=user.id,
                livro_id=row["livro"].id,
                biblioteca_id=data["biblioteca"].id if data["biblioteca"] else None,
                referencia_pedido=reference,
                pagamento_status="pending",
                estoque_debitado=True,
                termos_aceitos=True,
                consentimento_dados=True,
                termos_versao=current_app.config.get(
                    "TERMS_VERSION",
                    "2026-11",
                ),
                tipo=row["tipo"],
                status="aguardando_pagamento",
                status_entrega="Aguardando pagamento",
                quantidade=row["quantidade"],
                dias_aluguel=row["dias"] if rent else None,
                valor_base=row["subtotal"],
                frete=data["frete"] if index == 0 else 0,
                forma_pagamento=forma_pagamento,
                modo_entrega=data["modo"],
                nome_completo=data["nome"],
                cpf=data["cpf"],
                email_contato=data["email"],
                telefone=data["telefone"],
                endereco_entrega=data["endereco"],
                cep_entrega=data["cep"],
                cidade_entrega=data["cidade"],
                estado_entrega=data["estado"],
                data_devolucao_prevista=(
                    date.today() + timedelta(days=row["dias"]) if rent else None
                ),
            )
            db.session.add(tx)
            db.session.flush()
            registrar_alocacoes(tx.id, row["livro"].id, alocacoes_por_linha[index])
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return (
        reference,
        Transacao.query.filter_by(
            referencia_pedido=reference,
            usuario_id=user.id,
        ).all(),
    )


def _order_total(rows):
    return round(sum(float(tx.valor_base or 0) + float(tx.frete or 0) for tx in rows), 2)


def _set_payment_state(payment):
    if not isinstance(payment, dict):
        return False
    reference = str(payment.get("external_reference", ""))
    if not reference:
        return False
    rows = Transacao.query.filter_by(referencia_pedido=reference).with_for_update().all()
    if not rows:
        return False
    payment_id = str(payment.get("id", "")) or None
    status = str(payment.get("status", "pending")).lower()
    if status == "approved" and not (payment_id or "").startswith("DEMO-"):
        try:
            received_amount = float(payment.get("transaction_amount"))
        except (TypeError, ValueError):
            current_app.logger.warning(
                "Aprovação sem valor financeiro válido para pedido %s", reference
            )
            return False
        currency = str(payment.get("currency_id", "")).upper()
        expected_amount = _order_total(rows)
        if (
            not math.isfinite(received_amount)
            or abs(received_amount - expected_amount) > 0.01
            or currency != "BRL"
        ):
            current_app.logger.warning(
                "Pagamento divergente para pedido %s (valor/moeda não corresponde)", reference
            )
            return False
    terminal_failed = status in ("rejected", "cancelled", "canceled")
    approved = status == "approved"
    for tx in rows:
        tx.payment_id = payment_id or tx.payment_id
        current_status = str(tx.pagamento_status or "").lower()
        terminal_states = {
            "approved",
            "rejected",
            "cancelled",
            "canceled",
            "refunded",
            "charged_back",
        }
        if current_status in terminal_states and status != current_status:
            # Ignora notificações tardias; somente aprovação pode evoluir para estorno/chargeback.
            if not (current_status == "approved" and status in ("refunded", "charged_back")):
                continue
        tx.pagamento_status = status[:32]
        if approved:
            tx.payment_attempt_key = None
            tx.status = "ativa" if tx.tipo == "aluguel" else "concluida"
            tx.status_entrega = (
                "Aguardando retirada" if tx.modo_entrega == "retirada" else "Preparando envio"
            )
            # O estoque já foi debitado na reserva e não é debitado novamente.
            tx.estoque_debitado = True
        elif terminal_failed and tx.status == "aguardando_pagamento":
            tx.payment_attempt_key = None
            if tx.estoque_debitado:
                devolver_alocacoes(tx.id)
                tx.estoque_debitado = False
            tx.status = "cancelada"
            tx.status_entrega = "Pagamento não aprovado"
        elif status in ("refunded", "charged_back"):
            tx.payment_attempt_key = None
            # Não devolve estoque automaticamente após possível separação/entrega.
            tx.status = "cancelada"
            tx.status_entrega = "Revisar estorno/contestação"
    db.session.commit()
    return True


def _payment_request(method, body=None, idempotency_key=None):
    access_token = current_app.config.get("MP_ACCESS_TOKEN", "")
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    return requests.request(method, MP_PAYMENTS_URL, headers=headers, json=body, timeout=(5, 18))


def _get_payment(payment_id):
    if not str(payment_id).isdigit():
        raise ValueError("Identificador de pagamento inválido.")
    access_token = current_app.config.get("MP_ACCESS_TOKEN", "")
    response = requests.get(
        f"{MP_PAYMENTS_URL}/{payment_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=(5, 12),
    )
    response.raise_for_status()
    payment = response.json()
    if not isinstance(payment, dict):
        raise ValueError("Resposta inválida do provedor de pagamento.")
    return payment


def _transaction_data(payment):
    return (payment.get("point_of_interaction") or {}).get("transaction_data") or {}


def _payment_response(payment, reference):
    transaction_data = _transaction_data(payment)
    return {
        "ok": True,
        "order_reference": reference,
        "payment_id": str(payment.get("id", "")),
        "status": str(payment.get("status", "pending")),
        "status_detail": str(payment.get("status_detail", "")),
        "qr_code": transaction_data.get("qr_code", ""),
        "qr_code_base64": transaction_data.get("qr_code_base64", ""),
        "ticket_url": transaction_data.get("ticket_url", ""),
        "sucesso_url": url_for("pagamentos.pedido_confirmado", reference=reference),
    }


def _start_payment(forma_pagamento, card_data=None):
    if not current_app.config.get("MP_PAYMENTS_ENABLED"):
        return (
            jsonify(
                ok=False,
                error="Configure MP_PUBLIC_KEY e MP_ACCESS_TOKEN no .env para habilitar pagamentos.",
            ),
            503,
        )
    payload = _payload()
    validated, _, error = _checkout_data(payload)
    if error:
        return _erro_json(error)
    user, cart_rows, subtotal, data = validated

    card_token = method_id = issuer_id = None
    installments = None
    if forma_pagamento != "PIX":
        card_data = card_data if isinstance(card_data, dict) else {}
        card_token = str(card_data.get("token", "")).strip()
        method_id = str(card_data.get("payment_method_id", "")).strip()
        try:
            installments = int(card_data.get("installments", 0))
        except (TypeError, ValueError):
            installments = 0
        issuer_id = card_data.get("issuer_id")
        if not card_token or not method_id or not 1 <= installments <= 12:
            return (
                jsonify(
                    ok=False,
                    error="Os dados tokenizados do cartão estão incompletos. Revise o formulário de pagamento.",
                ),
                400,
            )

    try:
        reference, order_rows = _make_or_reuse_order(user, cart_rows, data, forma_pagamento)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    except Exception:
        current_app.logger.exception("Falha ao criar reserva de pedido")
        return jsonify(ok=False, error="Não foi possível reservar os itens. Tente novamente."), 500

    known_payment_id = next((tx.payment_id for tx in order_rows if tx.payment_id), None)
    if known_payment_id:
        try:
            payment = _get_payment(known_payment_id)
            if str(payment.get("external_reference", "")) == reference:
                if not _set_payment_state(payment):
                    return (
                        jsonify(
                            ok=False, error="Os dados do pagamento não correspondem ao pedido."
                        ),
                        502,
                    )
                if str(payment.get("status", "")).lower() in ("rejected", "cancelled", "canceled"):
                    session.pop("checkout_reference", None)
                else:
                    session["carrinho"] = {}
                    session.pop("checkout_reference", None)
                return jsonify(_payment_response(payment, reference))
        except (requests.RequestException, ValueError):
            return (
                jsonify(
                    ok=False,
                    error="Não foi possível consultar o pagamento existente. Tente novamente em instantes.",
                ),
                502,
            )

    attempt_key = next(
        (tx.payment_attempt_key for tx in order_rows if tx.payment_attempt_key),
        None,
    )
    if not attempt_key:
        attempt_key = str(uuid.uuid4())
        for tx in order_rows:
            tx.payment_attempt_key = attempt_key
        db.session.commit()

    amount = _order_total(order_rows)
    payer = {
        "email": order_rows[0].email_contato,
        "first_name": (order_rows[0].nome_completo or "Leitor").split()[0],
        "identification": {"type": "CPF", "number": order_rows[0].cpf},
    }
    body = {
        "transaction_amount": amount,
        "description": f"Pedido Biblioteca Aberta {reference[:8]}",
        "external_reference": reference,
        "payer": payer,
    }
    if current_app.config.get("MP_NOTIFICATION_URL"):
        body["notification_url"] = current_app.config["MP_NOTIFICATION_URL"]

    if forma_pagamento == "PIX":
        body["payment_method_id"] = "pix"
    else:
        body.update(
            {
                "token": card_token,
                "payment_method_id": method_id,
                "installments": installments,
            }
        )
        if issuer_id:
            body["issuer_id"] = issuer_id

    try:
        response = _payment_request("POST", body=body, idempotency_key=attempt_key)
    except requests.RequestException:
        # A chave de idempotência mantém a repetição segura caso a resposta da API tenha se perdido.
        return (
            jsonify(
                ok=False,
                error="Não foi possível confirmar a resposta do provedor. Tente novamente com o mesmo pedido.",
            ),
            502,
        )

    try:
        payment = response.json()
    except ValueError:
        payment = {}
    if not isinstance(payment, dict):
        payment = {}
    if response.status_code not in (200, 201):
        # 4xx é rejeição definitiva da solicitação; libera a reserva. 5xx pode ser ambíguo.
        if 400 <= response.status_code < 500:
            _set_payment_state({"external_reference": reference, "status": "rejected"})
            session.pop("checkout_reference", None)
            return (
                jsonify(
                    ok=False,
                    error="O provedor não aceitou a solicitação de pagamento. Confira os dados e tente novamente.",
                ),
                400,
            )
        return (
            jsonify(
                ok=False,
                error="O provedor está temporariamente indisponível. Tente novamente com segurança.",
            ),
            502,
        )
    if not payment.get("id") or str(payment.get("external_reference", "")) != reference:
        return (
            jsonify(
                ok=False,
                error="Não foi possível confirmar a referência do pagamento. O pedido ficou reservado para conferência.",
            ),
            502,
        )
    if not _set_payment_state(payment):
        current_app.logger.error("Resposta do provedor não corresponde ao pedido %s", reference)
        return (
            jsonify(
                ok=False,
                error="Os dados financeiros do pagamento não correspondem ao pedido. O caso será conferido.",
            ),
            502,
        )
    if str(payment.get("status", "")).lower() in ("rejected", "cancelled", "canceled"):
        session.pop("checkout_reference", None)
    else:
        session["carrinho"] = {}
        session.pop("checkout_reference", None)
    return jsonify(_payment_response(payment, reference))


DEMO_PIX_DELAY_MS = 5000


def _now_ms():
    return time.time_ns() // 1_000_000


def _demo_created_ms(payment_id):
    try:
        return int(str(payment_id)[len("DEMO-") :])
    except (TypeError, ValueError):
        return None


def _start_demo_payment(payment_method):
    if not current_app.config.get("DEMO_PAYMENTS_ENABLED"):
        return jsonify(ok=False, error="modo demo off"), 503
    payload = _payload()
    validated, _, error = _checkout_data(payload)
    if error:
        return _erro_json(error)
    user, cart_rows, subtotal, data = validated
    if payment_method == "Cartão" and not _truthy(payload.get("demo_card_confirmed")):
        return (
            jsonify(
                ok=False,
                error="Preencha os campos fictícios do cartão para testar a tela.",
            ),
            400,
        )

    try:
        reference, order_rows = _make_or_reuse_order(user, cart_rows, data, payment_method)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    except Exception:
        current_app.logger.exception("Falha ao registrar pedido.")
        return (
            jsonify(
                ok=False,
                error="Não foi possível registrar o pedido. Tente novamente.",
            ),
            500,
        )

    payment_id = next((tx.payment_id for tx in order_rows if tx.payment_id), None)
    if not payment_id:
        payment_id = f"DEMO-{_now_ms()}"
        for tx in order_rows:
            tx.payment_id = payment_id
        db.session.commit()
    session["carrinho"] = {}
    session.pop("checkout_reference", None)

    amount = _order_total(order_rows)
    base = {
        "ok": True,
        "demo": True,
        "order_reference": reference,
        "payment_id": payment_id,
        "amount": amount,
        "redirect_url": url_for("usuarios.perfil"),
        "sucesso_url": url_for("pagamentos.pedido_confirmado", reference=reference),
        "message": "O pedido foi registrado no seu perfil.",
    }
    if payment_method == "Cartão":
        _set_payment_state(
            {
                "external_reference": reference,
                "id": payment_id,
                "status": "approved",
            }
        )
        return jsonify(
            {
                **base,
                "status": "approved",
                "status_detail": "Pagamento de cartão aceito",
            }
        )

    # Texto deliberadamente incompatível com um payload EMV Pix pagável.
    copy_code = f"DEMO-PIX-NAO-PAGAVEL-{uuid.uuid4().hex[:20].upper()}"
    qr_payload = f"BIBLIOTECA_ABERTA_DEMONSTRACAO|NAO_E_PIX|{reference}|TOTAL={amount:.2f}"
    import qrcode

    qr = qrcode.QRCode(
        version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=7, border=4
    )
    qr.add_data(qr_payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#14243a", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return jsonify(
        {
            **base,
            "status": str(order_rows[0].pagamento_status or "pending"),
            "status_detail": "Pendente",
            "auto_accept_seconds": DEMO_PIX_DELAY_MS // 1000,
            "qr_code": copy_code,
            "qr_code_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        }
    )


@pagamentos_bp.post("/checkout/demo/pix")
def criar_pix_demo():
    return _start_demo_payment("PIX")


@pagamentos_bp.post("/checkout/demo/cartao")
def pagar_cartao_demo():
    return _start_demo_payment("Cartão")


@pagamentos_bp.post("/checkout/pix")
def criar_pix():
    return _start_payment("PIX")


@pagamentos_bp.post("/checkout/cartao")
def pagar_cartao():
    payload = _payload()
    return _start_payment("Cartão", card_data=payload.get("card", {}))


@pagamentos_bp.get("/checkout/status/<reference>")
def status_pedido(reference):
    user_id = session.get("usuario_id")
    if not user_id:
        return jsonify(ok=False, error="Autenticação necessária."), 401
    rows = Transacao.query.filter_by(referencia_pedido=reference, usuario_id=user_id).all()
    if not rows:
        return jsonify(ok=False, error="Pedido não encontrado."), 404
    demo_id = next(
        (tx.payment_id for tx in rows if str(tx.payment_id or "").startswith("DEMO-")),
        None,
    )
    if demo_id:
        created = _demo_created_ms(demo_id)
        pending_pix = (
            rows[0].forma_pagamento == "PIX"
            and str(rows[0].pagamento_status or "").lower() == "pending"
        )
        if pending_pix and created is not None and _now_ms() - created >= DEMO_PIX_DELAY_MS:
            _set_payment_state(
                {
                    "external_reference": reference,
                    "id": demo_id,
                    "status": "approved",
                }
            )
            rows = Transacao.query.filter_by(referencia_pedido=reference, usuario_id=user_id).all()
        return jsonify(
            ok=True,
            demo=True,
            order_reference=reference,
            payment_id=demo_id,
            status=str(rows[0].pagamento_status or "pending"),
            status_detail="",
            redirect_url=url_for("usuarios.perfil"),
            sucesso_url=url_for("pagamentos.pedido_confirmado", reference=reference),
        )
    payment_id = next((tx.payment_id for tx in rows if tx.payment_id), None)
    payment = None
    if payment_id and current_app.config.get("MP_ACCESS_TOKEN"):
        try:
            payment = _get_payment(payment_id)
            if str(payment.get("external_reference", "")) == reference:
                _set_payment_state(payment)
        except (requests.RequestException, ValueError):
            current_app.logger.warning("Falha ao consultar estado do pagamento %s", payment_id)
    if payment and str(payment.get("external_reference", "")) == reference:
        if _set_payment_state(payment):
            return jsonify(_payment_response(payment, reference))
    return jsonify(
        {
            "ok": True,
            "order_reference": reference,
            "payment_id": payment_id,
            "status": rows[0].pagamento_status,
            "status_detail": "",
        }
    )


def _validate_webhook_signature(signature, request_id, data_id, secret):
    if not signature or not secret or not data_id:
        return False
    values = {}
    for item in signature.split(","):
        if "=" in item:
            key, value = item.strip().split("=", 1)
            values[key] = value
    timestamp, v1 = values.get("ts"), values.get("v1")
    if not timestamp or not v1:
        return False
    try:
        if abs(int(time.time()) - int(timestamp)) > 900:
            return False
    except (TypeError, ValueError):
        return False
    manifest = f"id:{data_id};"
    if request_id:
        manifest += f"request-id:{request_id};"
    manifest += f"ts:{timestamp};"
    digest = hmac.new(secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, v1)


@pagamentos_bp.post("/webhooks/mercadopago")
def webhook():
    secret = current_app.config.get("MP_WEBHOOK_SECRET", "")
    payload = request.get_json(silent=True)
    payload = payload if isinstance(payload, dict) else {}
    event_data = payload.get("data")
    event_data = event_data if isinstance(event_data, dict) else {}
    data_id = request.args.get("data.id") or event_data.get("id")
    if not _validate_webhook_signature(
        request.headers.get("x-signature", ""),
        request.headers.get(
            "x-request-id",
            "",
        ),
        str(data_id or ""),
        secret,
    ):
        return "", 401
    event = request.args.get("type") or payload.get("type")
    if event and event not in ("payment", "payment.created", "payment.updated"):
        return "", 200
    try:
        payment = _get_payment(str(data_id))
        if not _set_payment_state(payment):
            return "", 404
    except ValueError:
        return "", 400
    except requests.RequestException:
        return "", 503
    return "", 200


@pagamentos_bp.get("/pedido/<reference>")
def pedido_confirmado(reference):
    """Tela de sucesso: resumo do pedido e próximos passos."""
    from flask import abort, redirect, render_template

    user_id = session.get("usuario_id")
    if not user_id:
        return redirect(url_for("usuarios.login", next=request.path))
    rows = Transacao.query.filter_by(referencia_pedido=reference, usuario_id=user_id).all()
    if not rows:
        abort(404)
    primeiro = rows[0]
    return render_template(
        "checkout-sucesso.html",
        rows=rows,
        pedido=primeiro,
        reference=reference,
        total=_order_total(rows),
        subtotal=round(sum(float(tx.valor_base or 0) for tx in rows), 2),
        frete=round(sum(float(tx.frete or 0) for tx in rows), 2),
        aprovado=str(primeiro.pagamento_status or "").lower() == "approved",
    )
