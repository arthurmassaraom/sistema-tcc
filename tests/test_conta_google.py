import os

os.environ.setdefault("AUTO_INIT_DATABASE", "false")

from database import db  # noqa: E402
from tests.test_conta import ContaTestCase  # noqa: E402


class ContaGoogleTest(ContaTestCase):
    def setUp(self):
        super().setUp()
        self.user.google_sub = "google-sub-teste"
        db.session.commit()

    def test_email_nao_pode_ser_alterado_em_conta_google(self):
        self.client.post("/conta/email", data={"email": "novo@example.com", "senha_atual": "senha-segura-123"})
        self.assertEqual(self.refresh().email, "ana@example.com")

    def test_senha_nao_pode_ser_alterada_em_conta_google(self):
        self.client.post(
            "/conta/senha",
            data={"senha_atual": "senha-segura-123", "nova_senha": "nova-senha-1", "confirmacao": "nova-senha-1"},
        )
        self.assertTrue(self.refresh().verificar_senha("senha-segura-123"))
        self.assertFalse(self.refresh().verificar_senha("nova-senha-1"))


if __name__ == "__main__":
    import unittest

    unittest.main()
