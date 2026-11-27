import os

# O módulo app cria uma instância no import; sem isto ela tentaria inicializar o
# banco configurado no .env (ex.: MySQL local). Cada teste usa SQLite em memória.
os.environ.setdefault("AUTO_INIT_DATABASE", "false")

import hashlib  # noqa: E402
import hmac
import base64
from io import BytesIO
import time
import tempfile
from pathlib import Path
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image

from app import create_app
from database import db
from models.avaliacao import Avaliacao
from models.biblioteca import Biblioteca
from models.livro import Livro
from models.transacao import Transacao
from models.usuario import Usuario


class BibliotecaAppTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "AUTO_INIT_DATABASE": True,"TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SECRET_KEY": "test-secret",
                "MP_PAYMENTS_ENABLED": True,
                "DEMO_PAYMENTS_ENABLED": False,
                "PAYMENT_MODE": "mercadopago",
                "MP_ACCESS_TOKEN": "test-access-token",
                "MP_PUBLIC_KEY": "test-public-key",
                "MP_WEBHOOK_SECRET": "test-webhook-secret",
                "MP_NOTIFICATION_URL": "",
                "TERMS_VERSION": "test-1",
                "AUTO_INIT_DATABASE": True,
                "CEP_LOOKUP_ENABLED": False,
                "GOOGLE_MAPS_API_KEY": "",
                # Isola os testes das credenciais reais que possam existir no .env.
                "GOOGLE_CLIENT_ID": "",
                "GOOGLE_CLIENT_SECRET": "",
                "GOOGLE_REDIRECT_URI": "",
            }
        )
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        from seed import seed_database

        seed_database()
        self.test_libraries = [
            Biblioteca(
                nome="Unidade Teste Centro",
                cep="01001-000",
                endereco="Endereço de teste, 1",
                cidade="São Paulo",
                estado="SP",
                telefone="",
            ),
            Biblioteca(
                nome="Unidade Teste Sul",
                cep="04534-011",
                endereco="Endereço de teste, 2",
                cidade="São Paulo",
                estado="SP",
                telefone="",
            ),
            Biblioteca(
                nome="Unidade Teste RJ",
                cep="20031-144",
                endereco="Endereço de teste, 3",
                cidade="Rio de Janeiro",
                estado="RJ",
                telefone="",
            ),
        ]
        db.session.add_all(self.test_libraries)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def create_user(self, email="leitor@example.com", name="Leitor Exemplo", role="cliente"):
        user = Usuario(nome=name, email=email, papel=role)
        user.set_senha("senha-forte-123")
        db.session.add(user)
        db.session.commit()
        return user

    def login_user(self, user):
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = user.id

    def add_book_to_cart(self, book, kind="aluguel", days="7", quantity="1"):
        response = self.client.post(
            "/carrinho/adicionar",
            data={
                "livro_id": str(book.id),
                "tipo": kind,
                "dias": days,
                "quantidade": quantity,
            },
        )
        self.assertEqual(response.status_code, 302)

    def checkout_payload(self, library, **updates):
        payload = {
            "nome_completo": "Leitor Exemplo",
            "cpf": "529.982.247-25",
            "email": "leitor@example.com",
            "telefone": "(11) 99999-1111",
            "modo_entrega": "retirada",
            "biblioteca_id": str(library.id),
            "forma_pagamento": "PIX",
            "termos_aceitos": True,
            "consentimento_dados": True,
        }
        payload.update(updates)
        return payload

    @staticmethod
    def mock_payment_response(body, status="pending", payment_id="9001"):
        payment = {
            "id": payment_id,
            "external_reference": body["external_reference"],
            "status": status,
            "status_detail": "pending_waiting_transfer" if status == "pending" else "accredited",
            "transaction_amount": body["transaction_amount"],
            "currency_id": "BRL",
            "point_of_interaction": {
                "transaction_data": {
                    "qr_code": "pix-code-from-provider",
                    "qr_code_base64": "cGl4LWJhc2U2NA==",
                    "ticket_url": "https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=public-test",
                }
            },
        }
        return SimpleNamespace(status_code=201, json=lambda: payment)

    def test_public_pages_and_complete_seed_render(self):
        for path in ("/", "/planos", "/livros", "/bibliotecas", "/login", "/carrinho", "/termos"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
        self.assertEqual(Livro.query.count(), 16)
        self.assertEqual(
            Biblioteca.query.count(), 3
        )  # unidades são fixtures de teste, não seed público.
        self.assertEqual(Biblioteca.query.filter(Biblioteca.nome.like("Unidade Teste%")).count(), 3)
        response = self.client.get("/livros/1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Sinopse".encode(), response.data)
        self.assertIn("Sem avaliações por enquanto".encode(), response.data)

    def test_public_library_page_handles_empty_real_partner_network(self):
        Biblioteca.query.delete()
        db.session.commit()
        response = self.client.get("/bibliotecas")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Rede parceira em configuração".encode(), response.data)
        self.assertNotIn("Biblioteca Pública Mário de Andrade".encode(), response.data)
        user = self.create_user()
        self.login_user(user)
        self.add_book_to_cart(Livro.query.filter_by(titulo="Dom Casmurro").one())
        checkout = self.client.get("/checkout")
        self.assertEqual(checkout.status_code, 200)
        self.assertIn("Retirada temporariamente indisponível".encode(), checkout.data)

    def test_no_default_admin_and_interactive_creation_command_exists(self):
        self.assertIsNone(Usuario.query.filter_by(papel="admin").first())
        self.assertIn("create-admin", self.app.cli.commands)
        self.assertIn("promote-admin", self.app.cli.commands)

    def test_all_admin_pages_render_in_horizontal_layout(self):
        admin = self.create_user("gestao@example.com", "Equipe Gestora", "admin")
        self.login_user(admin)
        for path in (
            "/admin/dashboard",
            "/admin/livros",
            "/admin/bibliotecas",
            "/admin/transacoes",
            "/admin/curadoria",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(b"admin-header", response.data)
            self.assertNotIn(b"admin-sidebar", response.data)

    def test_profile_is_private_and_not_cached(self):
        user = self.create_user()
        self.login_user(user)
        response = self.client.get("/perfil")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store".encode(), response.headers["Cache-Control"].encode())
        self.assertIn("private".encode(), response.headers["Cache-Control"].encode())

    def test_login_after_logout_accepts_legacy_email_case_and_places_error_in_card(self):
        user = self.create_user("Pessoa.Mista@Example.com", "Pessoa Leitora")
        self.client.post("/logout")
        response = self.client.post(
            "/login",
            data={
                "acao": "login",
                "email": "PESSOA.MISTA@EXAMPLE.COM",
                "senha": "senha-forte-123",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/perfil"))
        self.assertEqual(self.client.get("/perfil").status_code, 200)
        self.client.post("/logout")
        invalid = self.client.post(
            "/login",
            data={
                "acao": "login",
                "email": user.email,
                "senha": "senha-errada",
            },
        )
        self.assertEqual(invalid.status_code, 200)
        body = invalid.data
        marker = body.find(b'id="login-error"')
        start = body.rfind(b'<section class="panel login-card"', 0, marker)
        end = body.find(b"</section>", marker)
        self.assertGreaterEqual(start, 0)
        self.assertGreater(end, marker)
        self.assertIn("E-mail ou senha inválidos.".encode(), body[start:end])
        self.assertNotIn(b'class="flash', body)
        self.assertIn(b".login-inline-error", Path("static/css/components.css").read_bytes())
        import re

        normalized_css = re.sub(rb"\s+", b"", Path("static/css/components.css").read_bytes())
        self.assertIn(b"color:#b42318", normalized_css)
        self.assertIn(b"background:transparent!important", normalized_css)

    def test_legacy_demo_admin_is_disabled_once_and_can_be_safely_reactivated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(
                {
                    "AUTO_INIT_DATABASE": True,"TESTING": True,
                    "SQLALCHEMY_DATABASE_URI": f"sqlite:///{Path(temp_dir) / 'legacy.sqlite'}",
                    "SECRET_KEY": "isolated-test-secret",
                }
            )
            with app.app_context():
                user = self.create_user("admin@biblioteca.local", "Admin", "admin")
                user_id = user.id
                db.session.remove()
                with db.engine.begin() as connection:
                    connection.exec_driver_sql("PRAGMA user_version = 0")
                from services.sqlite_migrations import upgrade_legacy_sqlite

                upgrade_legacy_sqlite()
                db.session.remove()
                user = db.session.get(Usuario, user_id)
                self.assertEqual(user.papel, "cliente")
                new_password = "NovaSenhaAdminForte-2026!"
                result = app.test_cli_runner().invoke(
                    args=["promote-admin", "--email", "admin@biblioteca.local"],
                    input=f"{new_password}\n{new_password}\n",
                )
                self.assertEqual(result.exit_code, 0, result.output)
                db.session.remove()
                user = db.session.get(Usuario, user_id)
                self.assertTrue(user.is_admin)
                self.assertTrue(user.verificar_senha(new_password))
                db.session.remove()
                upgrade_legacy_sqlite()
                db.session.remove()
                self.assertTrue(db.session.get(Usuario, user_id).is_admin)
                client = app.test_client()
                response = client.post(
                    "/login",
                    data={
                        "acao": "login",
                        "email": "ADMIN@BIBLIOTECA.LOCAL",
                        "senha": new_password,
                    },
                )
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.headers["Location"].endswith("/admin/dashboard"))
                self.assertEqual(client.get("/admin/dashboard").status_code, 200)

    def test_legacy_admin_role_names_enter_admin_dashboard(self):
        for index, role in enumerate(("ADMIN", "Administrador", "Bibliotecário", "Bibliotecaria")):
            with self.subTest(role=role):
                email = f"admin-{index}@example.com"
                self.create_user(email, "Equipe Administrativa", role)
                self.client.post("/logout")
                response = self.client.post(
                    "/login",
                    data={
                        "acao": "login",
                        "email": email,
                        "senha": "senha-forte-123",
                    },
                )
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.headers["Location"].endswith("/admin/dashboard"))
                self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)
                self.assertEqual(self.client.get("/livros").status_code, 302)
                self.client.post("/logout")

    def test_login_signup_and_admin_role_boundary(self):
        response = self.client.post(
            "/login",
            data={
                "acao": "cadastro",
                "nome": "Pessoa Leitora",
                "email": "pessoa@example.com",
                "senha": "senha-forte-123",
                "termos_aceitos": "1",
                "consentimento_dados": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = Usuario.query.filter_by(email="pessoa@example.com").one()
        self.assertTrue(user.verificar_senha("senha-forte-123"))
        self.assertNotIn("Você fez login".encode(), response.data)

        admin = self.create_user("admin@example.com", "Bibliotecário Teste", "admin")
        self.client.post("/logout")
        response = self.client.post(
            "/login",
            data={"acao": "login", "email": admin.email, "senha": "senha-forte-123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/dashboard", response.headers["Location"])
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)
        self.assertEqual(self.client.get("/livros").status_code, 302)
        self.client.post("/logout")
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 403)

    def test_checkout_page_requires_consent_and_uses_provider_credentials(self):
        user = self.create_user()
        self.login_user(user)
        self.add_book_to_cart(Livro.query.filter_by(titulo="Dom Casmurro").one())
        response = self.client.get("/checkout")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'type="checkbox" value="true" required', response.data)
        self.assertIn(b"Termos e Condi\xc3\xa7\xc3\xb5es", response.data)
        self.assertIn(b"Gerar Pix", response.data)
        self.assertIn(b"cardPaymentBrick_container", response.data)
        self.assertIn(b'id="profile-link"', response.data)
        checkout_js = Path("static/js/checkout.js").read_text(encoding="utf-8")
        self.assertIn("goToProfileAfterApproval", checkout_js)
        self.assertIn("payment-success-overlay", checkout_js)
        self.assertIn("handleCardResult", checkout_js)
        self.assertIn(b"checkout-sucesso.css", response.data)

    @staticmethod
    def demo_checkout_payload(**updates):
        payload = {
            "nome_completo": "Leitor Exemplo",
            "cpf": "529.982.247-25",
            "email": "leitor@example.com",
            "telefone": "(11) 99999-1111",
            "modo_entrega": "domicilio",
            "cep": "01001-000",
            "logradouro": "Praça da Sé",
            "numero": "100",
            "bairro": "Sé",
            "cidade": "São Paulo",
            "estado": "SP",
            "termos_aceitos": True,
            "consentimento_dados": True,
        }
        payload.update(updates)
        return payload

    def test_demo_pix_qr_is_nonpayable_and_auto_accepts_into_profile(self):
        self.app.config.update(DEMO_PAYMENTS_ENABLED=True, MP_PAYMENTS_ENABLED=False)
        user = self.create_user()
        self.login_user(user)
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        stock_before = book.estoque
        self.add_book_to_cart(book, kind="compra")
        checkout = self.client.get("/checkout")
        self.assertEqual(checkout.status_code, 200)
        self.assertIn(b'id="demo-card-fields"', checkout.data)
        self.assertIn(b'id="demo-card-number"', checkout.data)
        self.assertIn(b'data-profile-url="/perfil"', checkout.data)
        response = self.client.post("/checkout/demo/pix", json=self.demo_checkout_payload())
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["demo"])
        self.assertTrue(data["qr_code"].startswith("DEMO-PIX-NAO-PAGAVEL-"))
        self.assertGreater(len(data["qr_code_base64"]), 100)
        image = Image.open(BytesIO(base64.b64decode(data["qr_code_base64"])))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["auto_accept_seconds"], 5)
        reference = data["order_reference"]
        # Antes de 5 segundos o pedido continua pendente.
        pending = self.client.get(f"/checkout/status/{reference}").get_json()
        self.assertEqual(pending["status"], "pending")
        # Após 5 segundos o Pix demo é aceito e o pedido aparece no perfil.
        later = (time.time_ns() // 1_000_000 + 6000) * 1_000_000
        with patch("routes.pagamentos_routes.time.time_ns", return_value=later):
            accepted = self.client.get(f"/checkout/status/{reference}").get_json()
        self.assertEqual(accepted["status"], "approved")
        self.assertEqual(accepted["redirect_url"], "/perfil")
        tx = Transacao.query.one()
        self.assertEqual(tx.pagamento_status, "approved")
        self.assertEqual(tx.status, "concluida")
        self.assertEqual(db.session.get(Livro, book.id).estoque, stock_before - 1)
        self.assertEqual(self.client.get("/carrinho").status_code, 200)
        profile = self.client.get("/perfil")
        self.assertIn("Dom Casmurro".encode(), profile.data)
        checkout_js = Path("static/js/checkout.js").read_text(encoding="utf-8")
        self.assertIn("confirmDemoPix", checkout_js)
        self.assertIn("auto_accept_seconds", checkout_js)

    def test_demo_card_is_accepted_and_order_shows_in_profile(self):
        self.app.config.update(DEMO_PAYMENTS_ENABLED=True, MP_PAYMENTS_ENABLED=False)
        user = self.create_user()
        self.login_user(user)
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        stock_before = book.estoque
        self.add_book_to_cart(book, kind="compra")
        response = self.client.post(
            "/checkout/demo/cartao", json=self.demo_checkout_payload(demo_card_confirmed=True)
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["demo"])
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["redirect_url"], "/perfil")
        self.assertEqual(Transacao.query.count(), 1)
        self.assertEqual(db.session.get(Livro, book.id).estoque, stock_before - 1)
        self.assertIn("Dom Casmurro".encode(), self.client.get("/perfil").data)
        checkout_js = Path("static/js/checkout.js").read_text(encoding="utf-8")
        self.assertNotIn("Cartão aceito", checkout_js)

    def test_demo_card_requires_confirmed_card_fields(self):
        self.app.config.update(DEMO_PAYMENTS_ENABLED=True, MP_PAYMENTS_ENABLED=False)
        user = self.create_user()
        self.login_user(user)
        self.add_book_to_cart(Livro.query.filter_by(titulo="Dom Casmurro").one(), kind="compra")
        response = self.client.post("/checkout/demo/cartao", json=self.demo_checkout_payload())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transacao.query.count(), 0)

    def test_pix_checkout_uses_gateway_and_reserves_stock_atomically(self):
        user = self.create_user()
        self.login_user(user)
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        before = book.estoque
        self.add_book_to_cart(book, quantity="2")
        library = Biblioteca.query.first()

        def request_gateway(method, url, headers, json, timeout):
            self.assertEqual(method, "POST")
            self.assertEqual(json["payment_method_id"], "pix")
            self.assertEqual(json["transaction_amount"], 16.0)
            self.assertTrue(headers["X-Idempotency-Key"])
            return self.mock_payment_response(json)

        with patch("routes.pagamentos_routes.requests.request", side_effect=request_gateway):
            response = self.client.post("/checkout/pix", json=self.checkout_payload(library))
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["qr_code"], "pix-code-from-provider")
        self.assertEqual(body["qr_code_base64"], "cGl4LWJhc2U2NA==")
        db.session.expire_all()
        tx = Transacao.query.filter_by(usuario_id=user.id).one()
        self.assertEqual(db.session.get(Livro, book.id).estoque, before - 2)
        self.assertEqual(tx.quantidade, 2)
        self.assertEqual(tx.pagamento_status, "pending")
        self.assertEqual(tx.forma_pagamento, "PIX")
        self.assertTrue(tx.termos_aceitos)
        self.assertEqual(tx.termos_versao, "test-1")
        self.assertEqual(tx.frete, 0)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("carrinho", {}), {})

    def test_missing_card_token_does_not_reserve_inventory(self):
        user = self.create_user()
        self.login_user(user)
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        before = book.estoque
        self.add_book_to_cart(book)
        library = Biblioteca.query.first()
        payload = self.checkout_payload(library, forma_pagamento="Cartão", card={})
        response = self.client.post("/checkout/cartao", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transacao.query.count(), 0)
        db.session.refresh(book)
        self.assertEqual(book.estoque, before)

    def test_card_uses_tokenized_provider_data_and_does_not_store_card_token(self):
        user = self.create_user()
        self.login_user(user)
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        self.add_book_to_cart(book, kind="compra")
        library = Biblioteca.query.first()
        card = {
            "token": "secure-token-only",
            "payment_method_id": "visa",
            "installments": 1,
            "issuer_id": "1234",
        }
        payload = self.checkout_payload(library, forma_pagamento="Cartão", card=card)

        def request_gateway(method, url, headers, json, timeout):
            self.assertEqual(json["token"], "secure-token-only")
            self.assertEqual(json["payment_method_id"], "visa")
            self.assertNotIn("number", json)
            self.assertNotIn("security_code", json)
            return self.mock_payment_response(json, status="approved", payment_id="9002")

        with patch("routes.pagamentos_routes.requests.request", side_effect=request_gateway):
            response = self.client.post("/checkout/cartao", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "approved")
        tx = Transacao.query.filter_by(usuario_id=user.id).one()
        self.assertEqual(tx.pagamento_status, "approved")
        self.assertEqual(tx.status, "concluida")
        self.assertFalse(hasattr(tx, "token"))
        self.assertNotIn(b"secure-token-only", response.data)

    def test_declined_payment_releases_reserved_inventory(self):
        user = self.create_user()
        self.login_user(user)
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        before = book.estoque
        self.add_book_to_cart(book)
        library = Biblioteca.query.first()

        def request_gateway(method, url, headers, json, timeout):
            return self.mock_payment_response(json, status="rejected", payment_id="9003")

        with patch("routes.pagamentos_routes.requests.request", side_effect=request_gateway):
            response = self.client.post("/checkout/pix", json=self.checkout_payload(library))
        self.assertEqual(response.status_code, 200)
        tx = Transacao.query.filter_by(usuario_id=user.id).one()
        self.assertEqual(tx.pagamento_status, "rejected")
        self.assertEqual(tx.status, "cancelada")
        db.session.refresh(book)
        self.assertEqual(book.estoque, before)

    def test_timeout_retry_reuses_idempotency_key_and_rejects_payment_method_switch(self):
        import requests

        user = self.create_user()
        self.login_user(user)
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        before = book.estoque
        self.add_book_to_cart(book)
        library = Biblioteca.query.first()
        payload = self.checkout_payload(library)
        keys = []

        def timeout_request(method, url, headers, json, timeout):
            keys.append(headers["X-Idempotency-Key"])
            raise requests.Timeout()

        with patch("routes.pagamentos_routes.requests.request", side_effect=timeout_request):
            failed = self.client.post("/checkout/pix", json=payload)
            self.assertEqual(failed.status_code, 502)
            with self.client.session_transaction() as sess:
                reference = sess["checkout_reference"]
            failed_retry = self.client.post("/checkout/pix", json=payload)
            self.assertEqual(failed_retry.status_code, 502)
            switched = self.client.post(
                "/checkout/cartao",
                json=self.checkout_payload(
                    library,
                    forma_pagamento="Cartão",
                    card={
                        "token": "token",
                        "payment_method_id": "visa",
                        "installments": 1,
                    },
                ),
            )
            self.assertEqual(switched.status_code, 409)
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(Transacao.query.filter_by(referencia_pedido=reference).count(), 1)
        db.session.refresh(book)
        self.assertEqual(book.estoque, before - 1)

    def test_webhook_requires_valid_hmac_and_applies_provider_status(self):
        user = self.create_user()
        self.login_user(user)
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        self.add_book_to_cart(book)
        library = Biblioteca.query.first()

        with patch(
            "routes.pagamentos_routes.requests.request",
            side_effect=lambda method, url, headers, json, timeout: self.mock_payment_response(
                json
            ),
        ):
            self.client.post("/checkout/pix", json=self.checkout_payload(library))
        tx = Transacao.query.filter_by(usuario_id=user.id).one()
        reference = tx.referencia_pedido
        bad = self.client.post(
            "/webhooks/mercadopago?type=payment&data.id=9001",
            headers={"x-signature": "ts=1,v1=bad", "x-request-id": "request-1"},
        )
        self.assertEqual(bad.status_code, 401)

        data_id, request_id, timestamp = "9001", "request-1", str(int(time.time()))
        manifest = f"id:{data_id};request-id:{request_id};ts:{timestamp};"
        digest = hmac.new(b"test-webhook-secret", manifest.encode(), hashlib.sha256).hexdigest()
        payment = {
            "id": data_id,
            "external_reference": reference,
            "status": "approved",
            "transaction_amount": float(tx.valor_base) + float(tx.frete),
            "currency_id": "BRL",
        }
        response = SimpleNamespace(
            status_code=200,
            json=lambda: payment,
            raise_for_status=lambda: None,
        )
        with patch("routes.pagamentos_routes.requests.get", return_value=response):
            accepted = self.client.post(
                f"/webhooks/mercadopago?type=payment&data.id={data_id}",
                headers={"x-signature": f"ts={timestamp},v1={digest}", "x-request-id": request_id},
            )
        self.assertEqual(accepted.status_code, 200)
        db.session.refresh(tx)
        self.assertEqual(tx.pagamento_status, "approved")
        self.assertEqual(tx.status, "ativa")

    def test_reviews_require_paid_order_and_average_real_user_ratings(self):
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        first = self.create_user("primeiro@example.com", "Pessoa Um")
        second = self.create_user("segundo@example.com", "Pessoa Dois")
        db.session.add_all(
            [
                Transacao(
                    usuario_id=first.id,
                    livro_id=book.id,
                    tipo="compra",
                    status="concluida",
                    pagamento_status="approved",
                    valor_base=32.90,
                ),
                Transacao(
                    usuario_id=second.id,
                    livro_id=book.id,
                    tipo="aluguel",
                    status="ativa",
                    pagamento_status="approved",
                    valor_base=8.00,
                ),
            ]
        )
        db.session.commit()
        self.login_user(first)
        response = self.client.post(
            f"/livros/{book.id}/avaliacoes",
            data={"estrelas": "3", "comentario": "Leitura marcante e muito bem escrita."},
        )
        self.assertEqual(response.status_code, 302)
        self.client.post("/logout")
        self.login_user(second)
        self.client.post(
            f"/livros/{book.id}/avaliacoes",
            data={"estrelas": "5", "comentario": "Gostei muito desta edição."},
        )
        db.session.expire_all()
        response = self.client.get(f"/livros/{book.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"4.00", response.data)
        self.assertIn(b"2 avalia", response.data)
        self.assertIn(b"Leitor verificado", response.data)
        self.assertNotIn(b'<span class="review-author">Pessoa Um</span>', response.data)
        self.assertNotIn(b'<span class="review-author">Pessoa Dois</span>', response.data)
        self.assertEqual(Avaliacao.query.filter_by(livro_id=book.id).count(), 2)

    def test_visitor_without_paid_order_cannot_submit_review(self):
        response = self.client.post(
            "/livros/1/avaliacoes",
            data={"estrelas": "5", "comentario": "Teste"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Avaliacao.query.count(), 0)

    def test_admin_book_crud_does_not_allow_manual_fake_rating(self):
        admin = self.create_user("admin@example.com", "Bibliotecário Teste", "admin")
        self.login_user(admin)
        response = self.client.post(
            "/admin/livros/novo",
            data={
                "titulo": "Livro de Teste",
                "autor": "Pessoa Autora",
                "estoque": "3",
                "ano": "2024",
                "preco_venda": "20",
                "preco_aluguel": "5",
                "modalidade": "Ambos",
                "genero": "Ficção",
                "categoria": "Teste",
                "avaliacao": "4.5",
            },
        )
        self.assertEqual(response.status_code, 302)
        book = Livro.query.filter_by(titulo="Livro de Teste").one()
        self.assertEqual(book.media_avaliacao, 0)
        self.assertEqual(self.client.post(f"/admin/livros/{book.id}/desativar").status_code, 302)
        db.session.refresh(book)
        self.assertFalse(book.ativo)
        self.assertIsNotNone(db.session.get(Livro, book.id))

    def test_admin_can_manage_real_partner_libraries_and_preserve_order_history(self):
        admin = self.create_user("admin-units@example.com", "Administradora Teste", "admin")
        self.login_user(admin)
        self.assertEqual(self.client.get("/admin/bibliotecas").status_code, 200)
        response = self.client.post(
            "/admin/bibliotecas",
            data={
                "nome": "Unidade Oficial Teste",
                "cep": "13010-111",
                "endereco": "Rua de teste, 50",
                "cidade": "Campinas",
                "estado": "sp",
                "telefone": "(19) 3333-4444",
            },
        )
        self.assertEqual(response.status_code, 302)
        library = Biblioteca.query.filter_by(nome="Unidade Oficial Teste").one()
        self.assertEqual(library.cep, "13010-111")
        response = self.client.post(
            f"/admin/bibliotecas/{library.id}/editar",
            data={
                "nome": "Unidade Oficial Atualizada",
                "cep": "13010-222",
                "endereco": "Avenida de teste, 10",
                "cidade": "Campinas",
                "estado": "SP",
                "telefone": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(Biblioteca.query.filter_by(nome="Unidade Oficial Atualizada").first())
        user = self.create_user("pedido@example.com", "Leitor Pedido")
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        tx = Transacao(
            usuario_id=user.id,
            livro_id=book.id,
            biblioteca_id=library.id,
            tipo="compra",
            valor_base=32.90,
        )
        db.session.add(tx)
        db.session.commit()
        self.client.post(f"/admin/bibliotecas/{library.id}/excluir")
        self.assertIsNotNone(db.session.get(Biblioteca, library.id))
        db.session.delete(tx)
        db.session.commit()
        self.client.post(f"/admin/bibliotecas/{library.id}/excluir")
        self.assertIsNone(db.session.get(Biblioteca, library.id))

    def test_cep_backend_groups_same_city_and_other_state(self):
        fake = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "cep": "01001-000",
                "logradouro": "Praça da Sé",
                "bairro": "Sé",
                "localidade": "São Paulo",
                "uf": "SP",
            },
        )
        with patch("routes.bibliotecas_routes.requests.get", return_value=fake):
            response = self.client.get("/api/cep/01001000")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["mesma_cidade"]), 2)
        self.assertEqual(len(data["outras_regioes"]), 1)
        self.assertEqual(data["endereco"]["estado"], "SP")

    def test_fine_progression_and_sale_price_cap(self):
        book = Livro(
            titulo="Teste multa",
            autor="Autora",
            modalidade="Ambos",
            estoque=1,
            preco_venda=3,
            preco_aluguel=10,
        )
        user = self.create_user("multa@example.com")
        db.session.add(book)
        db.session.commit()
        tx = Transacao(
            usuario_id=user.id,
            livro_id=book.id,
            tipo="aluguel",
            valor_base=10,
            data_devolucao_prevista=date.today() - timedelta(days=5),
        )
        db.session.add(tx)
        db.session.commit()
        self.assertEqual(tx.calcular_multa(), 3)

    def test_csrf_blocks_post_outside_testing_mode(self):
        app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://", "SECRET_KEY": "csrf-secret"})
        client = app.test_client()
        response = client.post(
            "/login",
            data={"acao": "login", "email": "a@example.com", "senha": "wrong"},
        )
        self.assertEqual(response.status_code, 400)

    def test_login_rejects_ambiguous_external_next_urls(self):
        user = self.create_user()
        for destination in (
            "//example.com",
            "/\\example.com",
            "/%2f%2fexample.com",
            "https://example.com",
        ):
            with self.subTest(destination=destination):
                self.client.post("/logout")
                response = self.client.post(
                    f"/login?next={destination}",
                    data={"acao": "login", "email": user.email, "senha": "senha-forte-123"},
                )
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.headers["Location"].endswith("/perfil"))

    def test_stale_session_is_cleared_without_server_error(self):
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = 999999
        response = self.client.get("/perfil")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        with self.client.session_transaction() as sess:
            self.assertNotIn("usuario_id", sess)

    def test_approved_payment_with_wrong_total_is_not_applied(self):
        from routes.pagamentos_routes import _set_payment_state

        user = self.create_user()
        self.login_user(user)
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        self.add_book_to_cart(book, kind="compra")
        library = Biblioteca.query.first()
        with patch(
            "routes.pagamentos_routes.requests.request",
            side_effect=lambda method, url, headers, json, timeout: self.mock_payment_response(
                json
            ),
        ):
            self.client.post("/checkout/pix", json=self.checkout_payload(library))
        tx = Transacao.query.filter_by(usuario_id=user.id).one()
        applied = _set_payment_state(
            {
                "id": "9002",
                "external_reference": tx.referencia_pedido,
                "status": "approved",
                "transaction_amount": float(tx.valor_base) + float(tx.frete) + 1.0,
                "currency_id": "BRL",
            }
        )
        self.assertFalse(applied)
        db.session.refresh(tx)
        self.assertEqual(tx.pagamento_status, "pending")
        self.assertEqual(tx.status, "aguardando_pagamento")

    def test_returning_same_rental_twice_restores_inventory_only_once(self):
        user = self.create_user()
        self.login_user(user)
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        starting_stock = book.estoque
        tx = Transacao(
            usuario_id=user.id,
            livro_id=book.id,
            tipo="aluguel",
            status="ativa",
            pagamento_status="approved",
            estoque_debitado=True,
            quantidade=1,
            valor_base=8.0,
            frete=0.0,
            data_devolucao_prevista=date.today(),
        )
        db.session.add(tx)
        db.session.commit()
        first = self.client.post(f"/livros/transacoes/{tx.id}/devolver")
        second = self.client.post(f"/livros/transacoes/{tx.id}/devolver")
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        db.session.refresh(book)
        db.session.refresh(tx)
        self.assertEqual(book.estoque, starting_stock + 1)
        self.assertEqual(tx.status, "devolvida")

    def test_donation_is_saved_and_success_message_is_shown(self):
        user = self.create_user()
        self.login_user(user)
        library = self.test_libraries[0]
        response = self.client.post(
            "/doe",
            data={
                "titulo": "Livro doado",
                "autor": "Autora Exemplo",
                "editora": "Editora",
                "ano": str(date.today().year - 1),
                "isbn": "9780000000001",
                "conservacao": "Boa",
                "biblioteca_entrega": library.nome,
            },
        )
        self.assertEqual(response.status_code, 302)
        page = self.client.get("/doe")
        self.assertIn("Doação enviada para análise da equipe.".encode(), page.data)

    def test_sqlite_foreign_keys_are_enabled(self):
        with db.engine.connect() as connection:
            enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        self.assertEqual(enabled, 1)

    def test_seed_preserves_curated_book_data_on_repeated_startup(self):
        from seed import seed_database

        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        book.preco_venda = 77.77
        book.capa_arquivo = "books/capa-curada.jpg"
        book.resumo = "Resumo revisado pela curadoria."
        book.avaliacao = 3.5
        db.session.commit()
        seed_database()
        db.session.refresh(book)
        self.assertEqual(book.preco_venda, 77.77)
        self.assertEqual(book.capa_arquivo, "books/capa-curada.jpg")
        self.assertEqual(book.resumo, "Resumo revisado pela curadoria.")
        self.assertEqual(book.avaliacao, 3.5)

    def test_anonymous_cart_survives_login(self):
        user = self.create_user()
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        self.add_book_to_cart(book, kind="compra")
        response = self.client.post(
            "/login",
            data={"acao": "login", "email": user.email, "senha": "senha-forte-123"},
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get("carrinho"))
            self.assertEqual(sess.get("usuario_id"), user.id)

    def test_cart_add_rejects_external_referer_redirect(self):
        book = Livro.query.filter_by(titulo="Dom Casmurro").one()
        response = self.client.post(
            "/carrinho/adicionar",
            data={"livro_id": str(book.id), "tipo": "compra", "quantidade": "1"},
            headers={"Referer": "https://attacker.example/"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/carrinho")

    def test_google_button_is_hidden_without_credentials(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Continuar com Google".encode(), response.data)

    def test_google_button_appears_when_oauth_credentials_are_configured(self):
        app = create_app(
            {
                "AUTO_INIT_DATABASE": True,"TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SECRET_KEY": "google-button-test-secret",
                "GOOGLE_CLIENT_ID": "web-client.apps.googleusercontent.com",
                "GOOGLE_CLIENT_SECRET": "test-client-secret",
            }
        )
        self.assertTrue(app.config["GOOGLE_LOGIN_ENABLED"])
        self.assertIn("google_oauth", app.extensions)
        with app.test_client() as client:
            response = client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Continuar com Google".encode(), response.data)

    def test_google_login_uses_configured_redirect_and_saves_only_local_next(self):
        calls = []

        def authorize_redirect(uri, **kwargs):
            calls.append((uri, kwargs))
            return self.app.response_class(
                "",
                status=302,
                headers={"Location": "https://accounts.google.com/o/oauth2/v2/auth"},
            )

        self.app.config.update(
            {
                "APP_ENV": "development",
                "GOOGLE_REDIRECT_URI": "http://localhost:5000/login/google/callback",
            }
        )
        self.app.extensions["google_oauth"] = SimpleNamespace(authorize_redirect=authorize_redirect)
        response = self.client.get("/login/google?next=%2Fcheckout")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            calls,
            [
                (
                    "http://localhost:5000/login/google/callback",
                    {"prompt": "select_account"},
                )
            ],
        )
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("google_login_next"), "/checkout")

    def test_google_production_redirect_must_use_https(self):
        calls = []
        self.app.config.update(
            {
                "APP_ENV": "production",
                "GOOGLE_REDIRECT_URI": "http://example.com/login/google/callback",
            }
        )
        self.app.extensions["google_oauth"] = SimpleNamespace(
            authorize_redirect=lambda *args, **kwargs: calls.append((args, kwargs))
        )
        response = self.client.get("/login/google")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(calls)
        with self.client.session_transaction() as sess:
            self.assertNotIn("google_login_next", sess)

    def test_google_oidc_callback_creates_verified_account(self):
        profile = {
            "sub": "google-sub-new-user",
            "email": "google-reader@gmail.com",
            "email_verified": True,
            "name": "Leitora Google",
        }
        self.app.extensions["google_oauth"] = SimpleNamespace(
            authorize_access_token=lambda: {"userinfo": profile}
        )
        response = self.client.get("/login/google/callback")
        self.assertEqual(response.status_code, 302)
        user = Usuario.query.filter_by(email="google-reader@gmail.com").one()
        self.assertEqual(user.google_sub, "google-sub-new-user")
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("usuario_id"), user.id)
        self.assertEqual(self.client.get("/perfil").status_code, 200)

    def test_google_oidc_callback_rejects_unverified_email(self):
        profile = {
            "sub": "google-sub-unverified",
            "email": "unverified@gmail.com",
            "email_verified": False,
            "name": "Google Reader",
        }
        self.app.extensions["google_oauth"] = SimpleNamespace(
            authorize_access_token=lambda: {"userinfo": profile}
        )
        response = self.client.get("/login/google/callback")
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(Usuario.query.filter_by(email="unverified@gmail.com").first())
        with self.client.session_transaction() as sess:
            self.assertNotIn("usuario_id", sess)

    def test_google_oidc_callback_links_existing_verified_gmail(self):
        user = self.create_user("existing@gmail.com", "Existing Reader")
        profile = {
            "sub": "google-sub-existing",
            "email": "existing@gmail.com",
            "email_verified": True,
            "name": "Existing Reader",
        }
        self.app.extensions["google_oauth"] = SimpleNamespace(
            authorize_access_token=lambda: {"userinfo": profile}
        )
        response = self.client.get("/login/google/callback")
        self.assertEqual(response.status_code, 302)
        db.session.refresh(user)
        self.assertEqual(user.google_sub, "google-sub-existing")
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("usuario_id"), user.id)

    def test_google_oidc_callback_does_not_link_external_email_automatically(self):
        user = self.create_user("person@external.example", "Existing Reader")
        profile = {
            "sub": "google-sub-external",
            "email": "person@external.example",
            "email_verified": True,
            "name": "External Reader",
        }
        self.app.extensions["google_oauth"] = SimpleNamespace(
            authorize_access_token=lambda: {"userinfo": profile}
        )
        response = self.client.get("/login/google/callback")
        self.assertEqual(response.status_code, 302)
        db.session.refresh(user)
        self.assertIsNone(user.google_sub)
        with self.client.session_transaction() as sess:
            self.assertNotIn("usuario_id", sess)

    def test_sqlite_migration_adds_google_subject_to_legacy_users(self):
        import sqlite3
        from sqlalchemy import inspect

        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy.sqlite"
            with sqlite3.connect(database_path) as connection:
                connection.execute("""CREATE TABLE usuarios (
                       id INTEGER PRIMARY KEY, nome VARCHAR(120) NOT NULL,
                       email VARCHAR(160) NOT NULL, senha_hash VARCHAR(255) NOT NULL,
                       papel VARCHAR(20) NOT NULL, cpf VARCHAR(14) NULL,
                       telefone VARCHAR(30) NULL, plano_id INTEGER NULL,
                       criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )""")
            app = create_app(
                {
                    "AUTO_INIT_DATABASE": True,"TESTING": True,
                    "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
                    "SECRET_KEY": "legacy-google-migration-test-secret",
                }
            )
            with app.app_context():
                columns = {column["name"] for column in inspect(db.engine).get_columns("usuarios")}
                indexes = inspect(db.engine).get_indexes("usuarios")
            self.assertIn("google_sub", columns)
            self.assertTrue(any(index["name"] == "uq_usuarios_google_sub" for index in indexes))


if __name__ == "__main__":
    unittest.main()
