import os

os.environ.setdefault("AUTO_INIT_DATABASE", "false")

import tempfile  # noqa: E402
import unittest  # noqa: E402
from datetime import date  # noqa: E402
from io import BytesIO  # noqa: E402
from pathlib import Path  # noqa: E402

from PIL import Image  # noqa: E402

from database import db  # noqa: E402
from models.endereco import Endereco  # noqa: E402
from models.interacoes import ListaDesejo  # noqa: E402
from models.livro import Livro  # noqa: E402
from models.transacao import Transacao  # noqa: E402
from models.usuario import Usuario  # noqa: E402
from tests.test_interface import InterfaceTestCase  # noqa: E402


def imagem(formato="JPEG", tamanho=(900, 600), exif=False):
    buffer = BytesIO()
    img = Image.new("RGB", tamanho, (120, 60, 30))
    kwargs = {}
    if exif:
        dados = Image.Exif()
        dados[0x010F] = "CameraTeste"  # Make
        dados[0x8825] = {2: (23.0, 33.0, 0.0)}  # GPSInfo
        kwargs["exif"] = dados.tobytes()
    img.save(buffer, formato, **kwargs)
    buffer.seek(0)
    return buffer


class ContaTestCase(InterfaceTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.app.config["AVATAR_DIR"] = self.tmp.name
        self.user = self.login_as()

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def refresh(self):
        db.session.expire_all()
        return db.session.get(Usuario, self.user.id)


class AvatarTest(ContaTestCase):
    def enviar(self, arquivo, nome="foto.jpg"):
        return self.client.post(
            "/conta/foto", data={"foto": (arquivo, nome)}, content_type="multipart/form-data"
        )

    def test_valid_image_is_resized_renamed_and_stripped_of_exif(self):
        response = self.enviar(imagem(exif=True), "minha foto pessoal.jpg")
        self.assertEqual(response.status_code, 302)
        user = self.refresh()
        self.assertTrue(user.foto)
        self.assertNotIn("pessoal", user.foto)
        self.assertRegex(user.foto, r"^[0-9a-f]{32}\.jpg$")
        salvo = Path(self.tmp.name) / user.foto
        with Image.open(salvo) as img:
            self.assertEqual(img.size, (512, 512))
            self.assertEqual(len(img.getexif()), 0)

    def test_rejects_fake_image_by_signature(self):
        falso = BytesIO(b"<?php echo 'oi'; ?>" + b"0" * 200)
        self.enviar(falso, "foto.jpg")
        self.assertIsNone(self.refresh().foto)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_rejects_file_above_2mb(self):
        grande = BytesIO(b"\xff\xd8\xff" + os.urandom(2 * 1024 * 1024 + 10))
        response = self.enviar(grande, "grande.jpg")
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.refresh().foto)
        page = self.client.get("/perfil?aba=dados").get_data(as_text=True)
        self.assertIn("no máximo 2 MB", page)

    def test_rejects_unsupported_format(self):
        self.enviar(imagem("GIF"), "anim.gif")
        self.assertIsNone(self.refresh().foto)

    def test_remove_photo_deletes_file(self):
        self.enviar(imagem("PNG"), "a.png")
        nome = self.refresh().foto
        self.assertTrue((Path(self.tmp.name) / nome).exists())
        self.client.post("/conta/foto/remover")
        self.assertIsNone(self.refresh().foto)
        self.assertFalse((Path(self.tmp.name) / nome).exists())

    def test_header_shows_photo_or_initials(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn(">AS</span>", html)
        self.enviar(imagem(), "x.jpg")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("uploads/avatars/", html)


class SegurancaTest(ContaTestCase):
    def test_change_password_requires_current_and_min_length(self):
        r = self.client.post("/conta/senha", data={"senha_atual": "errada", "nova_senha": "nova-senha-1", "confirmacao": "nova-senha-1"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.refresh().verificar_senha("senha-segura-123"))
        self.client.post("/conta/senha", data={"senha_atual": "senha-segura-123", "nova_senha": "curta", "confirmacao": "curta"})
        self.assertTrue(self.refresh().verificar_senha("senha-segura-123"))
        self.client.post("/conta/senha", data={"senha_atual": "senha-segura-123", "nova_senha": "nova-senha-1", "confirmacao": "outra-senha-1"})
        self.assertTrue(self.refresh().verificar_senha("senha-segura-123"))
        self.client.post("/conta/senha", data={"senha_atual": "senha-segura-123", "nova_senha": "nova-senha-1", "confirmacao": "nova-senha-1"})
        user = self.refresh()
        self.assertTrue(user.verificar_senha("nova-senha-1"))
        self.assertTrue(user.senha_hash.startswith(("scrypt:", "pbkdf2:")))

    def test_change_email_requires_password_and_normalizes(self):
        self.client.post("/conta/email", data={"email": "novo@example.com", "senha_atual": "errada"})
        self.assertEqual(self.refresh().email, "ana@example.com")
        self.client.post("/conta/email", data={"email": "  NOVO@Example.com ", "senha_atual": "senha-segura-123"})
        self.assertEqual(self.refresh().email, "novo@example.com")

    def test_update_name_and_phone_validation(self):
        self.client.post("/conta/dados", data={"nome": "Ana 123", "telefone": ""})
        self.assertEqual(self.refresh().nome, "Ana Clara Souza")
        self.client.post("/conta/dados", data={"nome": "Ana Souza", "telefone": "(20) 98765-4321"})
        self.assertEqual(self.refresh().nome, "Ana Clara Souza")
        self.client.post("/conta/dados", data={"nome": "Ana Souza", "telefone": "11987654321"})
        user = self.refresh()
        self.assertEqual((user.nome, user.telefone), ("Ana Souza", "(11) 98765-4321"))

    def test_google_unlink_keeps_an_access_method(self):
        user = self.refresh()
        user.google_sub = "sub-1"
        user.senha_definida = False
        db.session.commit()
        self.client.post("/conta/google/desvincular")
        self.assertEqual(self.refresh().google_sub, "sub-1")
        self.client.post("/conta/senha", data={"nova_senha": "definida-123", "confirmacao": "definida-123"})
        self.client.post("/conta/google/desvincular")
        user = self.refresh()
        self.assertIsNone(user.google_sub)
        self.assertTrue(user.verificar_senha("definida-123"))


class EnderecosTest(ContaTestCase):
    def dados(self, **extra):
        base = {"cep": "01001-000", "logradouro": "Praça da Sé", "numero": "100", "bairro": "Sé", "cidade": "São Paulo", "uf": "SP", "rotulo": "Casa"}
        base.update(extra)
        return base

    def test_limit_of_three_and_single_default(self):
        for rotulo in ("Casa", "Trabalho", "Outro", "Casa"):
            self.client.post("/conta/enderecos", data=self.dados(rotulo=rotulo))
        enderecos = Endereco.query.filter_by(usuario_id=self.user.id).all()
        self.assertEqual(len(enderecos), 3)
        self.assertEqual(sum(1 for e in enderecos if e.padrao), 1)
        self.client.post(f"/conta/enderecos/{enderecos[2].id}/padrao")
        db.session.expire_all()
        self.assertEqual([e.padrao for e in Endereco.query.order_by(Endereco.id)], [False, False, True])

    def test_requires_number_or_no_number_flag(self):
        self.client.post("/conta/enderecos", data=self.dados(numero=""))
        self.assertEqual(Endereco.query.count(), 0)
        self.client.post("/conta/enderecos", data=self.dados(numero="", sem_numero="1"))
        self.assertTrue(Endereco.query.one().sem_numero)

    def test_saved_address_is_offered_in_checkout(self):
        self.client.post("/conta/enderecos", data=self.dados())
        livro = Livro.query.filter_by(titulo="Dom Casmurro").one()
        self.client.post("/carrinho/adicionar", data={"livro_id": livro.id, "tipo": "compra"})
        html = self.client.get("/checkout").get_data(as_text=True)
        self.assertIn('name="endereco_salvo"', html)
        self.assertIn("Praça da Sé", html)


class ExclusaoContaTest(ContaTestCase):
    def test_delete_account_anonymizes_orders(self):
        livro = Livro.query.filter_by(titulo="Dom Casmurro").one()
        tx = Transacao(
            usuario_id=self.user.id, livro_id=livro.id, tipo="compra", status="concluida",
            pagamento_status="approved", valor_base=10, nome_completo="Ana Clara Souza",
            cpf="52998224725", email_contato="ana@example.com", telefone="(11) 98765-4321",
            endereco_entrega="Rua X, 1", cep_entrega="01001000", data_transacao=date.today(),
        )
        db.session.add_all([tx, ListaDesejo(usuario_id=self.user.id, livro_id=livro.id)])
        db.session.commit()
        self.client.post("/conta/excluir", data={"senha_atual": "errada"})
        self.assertTrue(self.refresh().ativo)
        self.client.post("/conta/excluir", data={"senha_atual": "senha-segura-123"})
        user = self.refresh()
        self.assertFalse(user.ativo)
        self.assertNotIn("ana@example.com", user.email)
        self.assertEqual(user.nome, "Conta excluída")
        pedido = db.session.get(Transacao, tx.id)
        self.assertIsNotNone(pedido, "O pedido deve ser mantido")
        self.assertEqual(pedido.nome_completo, "Cliente anonimizado")
        self.assertIsNone(pedido.cpf)
        self.assertIsNone(pedido.email_contato)
        self.assertEqual(ListaDesejo.query.count(), 0)
        self.assertEqual(self.client.get("/perfil").status_code, 302)

    def test_active_rental_blocks_deletion(self):
        livro = Livro.query.filter_by(titulo="Dom Casmurro").one()
        db.session.add(Transacao(usuario_id=self.user.id, livro_id=livro.id, tipo="aluguel", status="ativa", pagamento_status="approved", valor_base=8, data_transacao=date.today()))
        db.session.commit()
        self.client.post("/conta/excluir", data={"senha_atual": "senha-segura-123"})
        self.assertTrue(self.refresh().ativo)


if __name__ == "__main__":
    unittest.main()
