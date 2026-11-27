import os

os.environ.setdefault("AUTO_INIT_DATABASE", "false")

import unittest  # noqa: E402

from database import db  # noqa: E402
from models.livro import Livro  # noqa: E402
from tests.test_interface import InterfaceTestCase  # noqa: E402

JSON = {"Accept": "application/json"}


class CarrinhoJsonTest(InterfaceTestCase):
    def setUp(self):
        super().setUp()
        self.livro = Livro.query.filter_by(titulo="Dom Casmurro").one()

    def add(self, tipo="compra", quantidade=1, dias=None):
        payload = {"livro_id": self.livro.id, "tipo": tipo, "quantidade": quantidade}
        if dias:
            payload["dias"] = dias
        return self.client.post("/carrinho/adicionar", json=payload, headers=JSON)

    def test_add_returns_state_json(self):
        data = self.add().get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["quantidade_total"], 1)
        self.assertEqual(data["itens"][0]["titulo"], "Dom Casmurro")
        self.assertIn("Dom Casmurro", data["mensagem"])

    def test_update_and_remove_via_json(self):
        key = self.add().get_json()["itens"][0]["key"]
        response = self.client.post(
            "/carrinho/atualizar", json={"key": key, "quantidade": 3}, headers=JSON
        )
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["itens"][0]["quantidade"], 3)
        self.assertAlmostEqual(data["subtotal"], round(self.livro.preco_venda * 3, 2))

        response = self.client.post("/carrinho/remover", json={"key": key}, headers=JSON)
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["itens"], [])
        self.assertTrue(data["sugestoes"], "Sacola vazia deve trazer sugestões")

    def test_update_above_stock_is_rejected_with_message(self):
        key = self.add().get_json()["itens"][0]["key"]
        response = self.client.post(
            "/carrinho/atualizar", json={"key": key, "quantidade": self.livro.estoque + 1}, headers=JSON
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.get_json()["ok"])
        self.assertIn("estoque", response.get_json()["mensagem"])

    def test_unknown_key_returns_404_json(self):
        response = self.client.post("/carrinho/remover", json={"key": "999:compra:0"}, headers=JSON)
        self.assertEqual(response.status_code, 404)
        response = self.client.post("/carrinho/atualizar", json={"key": "x", "quantidade": 1}, headers=JSON)
        self.assertEqual(response.status_code, 404)

    def test_delivery_choice_uses_central_fee(self):
        self.app.config["DELIVERY_FEE"] = 15.5
        self.add()
        data = self.client.post("/carrinho/entrega", json={"modo": "domicilio"}, headers=JSON).get_json()
        self.assertEqual(data["frete"], 15.5)
        self.assertAlmostEqual(data["total"], round(self.livro.preco_venda + 15.5, 2))
        data = self.client.post("/carrinho/entrega", json={"modo": "retirada"}, headers=JSON).get_json()
        self.assertEqual(data["frete"], 0)

    def test_form_posts_still_redirect(self):
        self.client.post("/carrinho/adicionar", data={"livro_id": self.livro.id, "tipo": "compra"})
        response = self.client.post("/carrinho/atualizar", data={"key": f"{self.livro.id}:compra:0", "quantidade": "2"})
        self.assertEqual(response.status_code, 302)
        page = self.client.get("/carrinho").get_data(as_text=True)
        self.assertIn("Dom Casmurro", page)
        self.assertIn("Continuar para o checkout", page)

    def test_csrf_header_is_accepted_outside_testing(self):
        self.app.config["TESTING"] = False
        self.client.get("/")
        with self.client.session_transaction() as sess:
            token = sess["_csrf_token"]
        blocked = self.client.post("/carrinho/adicionar", json={"livro_id": self.livro.id, "tipo": "compra"}, headers=JSON)
        self.assertEqual(blocked.status_code, 400)
        allowed = self.client.post(
            "/carrinho/adicionar",
            json={"livro_id": self.livro.id, "tipo": "compra"},
            headers={**JSON, "X-CSRF-Token": token},
        )
        self.assertEqual(allowed.status_code, 200)

    def test_empty_cart_page_has_empty_state_and_suggestions(self):
        html = self.client.get("/carrinho").get_data(as_text=True)
        self.assertIn("empty-state", html)
        self.assertIn("Sua sacola está esperando uma história", html)
        self.assertIn("book-card", html)

    def test_drawer_markup_is_accessible(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="sacola" role="dialog" aria-modal="true" aria-labelledby="sacola-titulo"', html)
        self.assertIn('data-cart-live', html)
        self.assertIn('aria-live="polite"', html)

    def test_inactive_book_cannot_be_added(self):
        self.livro.ativo = False
        db.session.commit()
        response = self.add()
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
