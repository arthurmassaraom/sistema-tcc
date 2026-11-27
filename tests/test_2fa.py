import os

os.environ.setdefault("AUTO_INIT_DATABASE", "false")

import re  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from unittest import mock  # noqa: E402

from database import db  # noqa: E402
from models.usuario import Usuario  # noqa: E402
from services.twofa import MAX_TENTATIVAS  # noqa: E402
from tests.test_conta import ContaTestCase  # noqa: E402

SENHA = "senha-segura-123"


class Caixa:
    """Guarda os e-mails enviados durante o teste, para ler o código."""

    def __init__(self):
        self.envios = []

    def __call__(self, destinatario, assunto, texto):
        self.envios.append({"to": destinatario, "subject": assunto, "text": texto})
        return True

    def ultimo_codigo(self):
        return re.search(r"código de verificação é: (\d{6})", self.envios[-1]["text"]).group(1)


class TwoFactorTest(ContaTestCase):
    def setUp(self):
        super().setUp()
        self.user.set_senha(SENHA)
        db.session.commit()
        self.caixa = Caixa()
        patches = [
            mock.patch("services.twofa.enviar_email", side_effect=self.caixa),
            mock.patch("routes.conta_routes.enviar_email", side_effect=self.caixa),
            mock.patch("routes.usuarios_routes.enviar_email", side_effect=self.caixa),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def ativar_2fa(self):
        """Fluxo completo de ativação com o código recebido por e-mail."""
        self.client.post("/conta/2fa/ativar", data={"senha_atual": SENHA})
        codigo = self.caixa.ultimo_codigo()
        self.client.post("/conta/2fa/confirmar", data={"codigo": codigo})
        return codigo

    def sair(self):
        self.client.post("/logout")

    def entrar_com_senha(self):
        return self.client.post("/login", data={"acao": "login", "email": self.user.email, "senha": SENHA})

    # ---------------------------------------------------------- ativação
    def test_ativar_envia_codigo_sem_pedir_senha(self):
        self.client.post("/conta/2fa/ativar")
        self.assertEqual(len(self.caixa.envios), 1)
        self.assertFalse(self.refresh().two_fa_ativo)
        self.assertTrue(self.refresh().two_fa_codigo_hash)

    def test_ativacao_com_codigo_correto_liga_o_2fa(self):
        self.ativar_2fa()
        self.assertTrue(self.refresh().two_fa_ativo)
        self.assertIsNone(self.refresh().two_fa_codigo_hash)
        self.assertTrue(any("ativada" in e["subject"] for e in self.caixa.envios))

    def test_codigo_errado_nao_ativa_e_conta_tentativas(self):
        self.client.post("/conta/2fa/ativar", data={"senha_atual": SENHA})
        self.client.post("/conta/2fa/confirmar", data={"codigo": "000000"})
        usuario = self.refresh()
        self.assertFalse(usuario.two_fa_ativo)
        self.assertEqual(usuario.two_fa_tentativas, 1)

    # ---------------------------------------------------------- login
    def test_login_com_2fa_exige_codigo_antes_de_entrar(self):
        self.ativar_2fa()
        self.sair()
        resposta = self.entrar_com_senha()
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/login/2fa", resposta.headers["Location"])
        with self.client.session_transaction() as sessao:
            self.assertNotIn("usuario_id", sessao)

    def test_codigo_correto_conclui_o_login(self):
        self.ativar_2fa()
        self.sair()
        self.entrar_com_senha()
        codigo = self.caixa.ultimo_codigo()
        resposta = self.client.post("/login/2fa", data={"codigo": codigo})
        self.assertEqual(resposta.status_code, 302)
        with self.client.session_transaction() as sessao:
            self.assertEqual(sessao.get("usuario_id"), self.user.id)

    def test_codigo_expirado_nao_funciona(self):
        self.ativar_2fa()
        self.sair()
        self.entrar_com_senha()
        codigo = self.caixa.ultimo_codigo()
        usuario = self.refresh()
        usuario.two_fa_expira_em = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
        self.client.post("/login/2fa", data={"codigo": codigo})
        with self.client.session_transaction() as sessao:
            self.assertNotIn("usuario_id", sessao)

    def test_muitas_tentativas_bloqueiam_o_codigo(self):
        self.ativar_2fa()
        self.sair()
        self.entrar_com_senha()
        codigo_certo = self.caixa.ultimo_codigo()
        errado = "000000" if codigo_certo != "000000" else "111111"
        for _ in range(MAX_TENTATIVAS):
            self.client.post("/login/2fa", data={"codigo": errado})
        self.client.post("/login/2fa", data={"codigo": codigo_certo})
        with self.client.session_transaction() as sessao:
            self.assertNotIn("usuario_id", sessao)

    def test_desativar_exige_codigo_do_email(self):
        self.ativar_2fa()
        self.client.post("/conta/2fa/desativar/enviar")
        self.client.post("/conta/2fa/desativar/confirmar", data={"codigo": "000000" if self.caixa.ultimo_codigo() != "000000" else "111111"})
        self.assertTrue(self.refresh().two_fa_ativo)
        self.client.post("/conta/2fa/desativar/confirmar", data={"codigo": self.caixa.ultimo_codigo()})
        self.assertFalse(self.refresh().two_fa_ativo)
        self.sair()
        resposta = self.entrar_com_senha()
        self.assertNotIn("/login/2fa", resposta.headers.get("Location", ""))


if __name__ == "__main__":
    import unittest

    unittest.main()
