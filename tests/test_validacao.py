import unittest

from services.validacao import (
    cpf_valido,
    formatar_telefone,
    logradouro_diverge,
    normalizar_email,
    validar_cep,
    validar_nome,
    validar_numero,
    validar_telefone,
)


class CpfTest(unittest.TestCase):
    def test_valid_cpfs_with_and_without_mask(self):
        self.assertTrue(cpf_valido("529.982.247-25"))
        self.assertTrue(cpf_valido("52998224725"))

    def test_invalid_check_digits(self):
        self.assertFalse(cpf_valido("529.982.247-24"))
        self.assertFalse(cpf_valido("529.982.247-35"))

    def test_repeated_and_wrong_length(self):
        self.assertFalse(cpf_valido("111.111.111-11"))
        self.assertFalse(cpf_valido("1234567890"))
        self.assertFalse(cpf_valido(""))
        self.assertFalse(cpf_valido(None))


class TelefoneTest(unittest.TestCase):
    def test_mobile_and_landline(self):
        self.assertEqual(validar_telefone("(11) 98765-4321"), ("11987654321", None))
        self.assertEqual(validar_telefone("(21) 3333-4444"), ("2133334444", None))
        self.assertEqual(validar_telefone("+55 11 98765-4321")[0], "11987654321")

    def test_invalid_ddd(self):
        digitos, erro = validar_telefone("(20) 98765-4321")
        self.assertIsNone(digitos)
        self.assertIn("DDD 20", erro)

    def test_wrong_number_of_digits(self):
        self.assertIsNotNone(validar_telefone("11 9876-543")[1])
        self.assertIsNotNone(validar_telefone("11 987654321000")[1])

    def test_mobile_must_start_with_nine(self):
        self.assertIsNotNone(validar_telefone("(11) 88765-4321")[1])

    def test_landline_prefix_and_repeated_digits(self):
        self.assertIsNotNone(validar_telefone("(11) 9876-5432")[1])
        self.assertIsNotNone(validar_telefone("(11) 99999-9999")[1])

    def test_format(self):
        self.assertEqual(formatar_telefone("11987654321"), "(11) 98765-4321")
        self.assertEqual(formatar_telefone("2133334444"), "(21) 3333-4444")


class EmailTest(unittest.TestCase):
    def test_normalizes_case_and_spaces(self):
        self.assertEqual(normalizar_email("  Ana.Souza@Exemplo.COM "), ("ana.souza@exemplo.com", None))

    def test_rejects_invalid_formats(self):
        for valor in ("ana", "ana@", "ana@exemplo", "ana..s@exemplo.com", ".ana@exemplo.com", "ana@exemplo.c", "a b@exemplo.com", ""):
            with self.subTest(valor=valor):
                self.assertIsNotNone(normalizar_email(valor)[1])

    def test_rejects_too_long(self):
        self.assertIsNotNone(normalizar_email("a" * 64 + "@" + "b" * 100 + ".com")[1])


class NomeTest(unittest.TestCase):
    def test_minimum_and_digits(self):
        self.assertEqual(validar_nome("  Ana   Souza "), ("Ana Souza", None))
        self.assertIsNotNone(validar_nome("A")[1])
        self.assertIsNotNone(validar_nome("Ana 2")[1])
        self.assertIsNotNone(validar_nome("Ana@Souza")[1])

    def test_full_name_requires_surname(self):
        self.assertIsNotNone(validar_nome("Ana", completo=True)[1])
        self.assertIsNone(validar_nome("Ana Souza", completo=True)[1])
        self.assertIsNone(validar_nome("João D'Ávila-Neto", completo=True)[1])


class EnderecoTest(unittest.TestCase):
    def test_cep(self):
        self.assertEqual(validar_cep("01001-000"), ("01001000", None))
        self.assertIsNotNone(validar_cep("0100-100")[1])
        self.assertIsNotNone(validar_cep("00000-000")[1])

    def test_numero_required_or_explicit_no_number(self):
        self.assertEqual(validar_numero("120"), ("120", None))
        self.assertEqual(validar_numero("120A"), ("120A", None))
        self.assertIsNotNone(validar_numero("")[1])
        self.assertEqual(validar_numero("", sem_numero=True), ("", None))
        self.assertIsNotNone(validar_numero("apto 12 bloco B")[1])

    def test_street_divergence(self):
        self.assertFalse(logradouro_diverge("Praça da Sé", "Praça da Sé"))
        self.assertFalse(logradouro_diverge("R. Augusta", "Rua Augusta"))
        self.assertFalse(logradouro_diverge("Av Paulista", "Avenida Paulista"))
        self.assertTrue(logradouro_diverge("Rua das Flores", "Avenida Paulista"))


if __name__ == "__main__":
    unittest.main()
