import os

os.environ.setdefault("AUTO_INIT_DATABASE", "false")

import unittest  # noqa: E402
from datetime import date, timedelta  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import patch  # noqa: E402

import requests  # noqa: E402

from database import db  # noqa: E402
from models.biblioteca import Biblioteca  # noqa: E402
from models.interacoes import GeoCache, ListaDesejo, ListaEspera, Notificacao  # noqa: E402
from models.livro import Livro  # noqa: E402
from models.transacao import Transacao  # noqa: E402
from services import geo as geo_service  # noqa: E402
from tests.test_interface import InterfaceTestCase  # noqa: E402

JSON = {"Accept": "application/json"}
VIACEP_SE = {"cep": "01001-000", "logradouro": "Praça da Sé", "bairro": "Sé", "localidade": "São Paulo", "uf": "SP"}


def resposta(dados, status=200):
    def json():
        return dados

    def raise_for_status():
        if status >= 400:
            raise requests.HTTPError(str(status))

    return SimpleNamespace(json=json, raise_for_status=raise_for_status, status_code=status)


class FakeHttp:
    """Responde ViaCEP e Google Geocoding sem acessar a rede."""

    def __init__(self, google=None, viacep=None):
        self.google = google or []
        self.viacep = viacep or VIACEP_SE
        self.google_calls = []

    def __call__(self, url, params=None, timeout=None, **_):
        if "viacep" in url:
            return resposta(self.viacep)
        self.google_calls.append(params)
        item = self.google.pop(0) if self.google else {"status": "ZERO_RESULTS", "results": []}
        if isinstance(item, Exception):
            raise item
        return resposta(item)


def google_ok(lat, lng, tipo="ROOFTOP"):
    return {
        "status": "OK",
        "results": [{"formatted_address": "Endereço", "geometry": {"location": {"lat": lat, "lng": lng}, "location_type": tipo}}],
    }


class PaginasTest(InterfaceTestCase):
    def test_privacy_and_cookies_pages(self):
        html = self.client.get("/privacidade").get_data(as_text=True)
        self.assertIn("Política de Privacidade", html)
        for trecho in ("Controlador", "Bases legais", "Retenção", "LGPD", "Google Maps"):
            self.assertIn(trecho.lower(), html.lower())
        cookies = self.client.get("/cookies").get_data(as_text=True)
        self.assertIn("estritamente necessários", cookies)
        self.assertIn("session", cookies)
        self.assertIn("Não usamos cookies de publicidade", cookies)

    def test_terms_contain_new_sections(self):
        html = self.client.get("/termos").get_data(as_text=True)
        for trecho in ("7 (sete) dias", "art. 49", "Multa por atraso", "modo de demonstração", "10 dias úteis", "revisado por assessoria jurídica"):
            self.assertIn(trecho, html)
        self.assertNotIn("processados pelo Mercado Pago", html)

    def test_footer_links_legal_pages(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/privacidade"', html)
        self.assertIn('href="/cookies"', html)

    def test_404_page_has_identity_and_way_back(self):
        response = self.client.get("/pagina-que-nao-existe")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 404)
        self.assertIn("Página não encontrada", html)
        self.assertIn("site-header", html)
        self.assertIn("Ir para o início", html)

    def test_404_json_for_api(self):
        response = self.client.get("/api/inexistente")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json()["ok"])

    def test_400_expired_session_page(self):
        self.app.config["TESTING"] = False
        response = self.client.post("/carrinho/remover", data={"key": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Sua sessão expirou", response.get_data(as_text=True))

    def test_500_page(self):
        self.app.config["PROPAGATE_EXCEPTIONS"] = False

        @self.app.get("/explode-teste")
        def explode():
            raise RuntimeError("falha simulada")

        response = self.client.get("/explode-teste")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Algo deu errado do nosso lado", response.get_data(as_text=True))

    def test_public_page_is_not_no_store_but_user_page_is(self):
        self.assertNotIn("no-store", self.client.get("/termos").headers["Cache-Control"])
        self.login_as()
        self.assertIn("no-store", self.client.get("/termos").headers["Cache-Control"])


class EstadosVaziosTest(InterfaceTestCase):
    def test_catalog_empty_state_with_suggestions(self):
        html = self.client.get("/livros?q=zzzzzz").get_data(as_text=True)
        self.assertIn("Nenhuma obra encontrada", html)
        self.assertIn("empty-state", html)
        self.assertIn("book-card", html)

    def test_profile_without_orders_and_favorites(self):
        self.login_as()
        html = self.client.get("/perfil").get_data(as_text=True)
        self.assertIn("Seu diário de leituras começa aqui", html)
        self.assertIn("Nenhum favorito ainda", html)
        self.assertIn("Nenhuma avaliação por aqui", html)
        self.assertIn("Cadastre seu primeiro endereço", html)

    def test_libraries_empty_state_links_partner_info(self):
        html = self.client.get("/bibliotecas").get_data(as_text=True)
        self.assertIn("Rede parceira em configuração", html)
        self.assertIn("Como uma biblioteca se torna parceira", html)

    def test_transparency_and_donation_empty_states(self):
        self.assertIn("A primeira doação pode ser a sua", self.client.get("/doacoes/transparencia").get_data(as_text=True))
        self.assertIn("Entre para registrar sua doação", self.client.get("/doe").get_data(as_text=True))

    def test_admin_empty_listings(self):
        self.login_as(nome="Admin Teste", email="adm@example.com", papel="admin")
        self.assertIn("Ainda não há pedidos", self.client.get("/admin/transacoes").get_data(as_text=True))
        self.assertIn("Nenhuma unidade cadastrada", self.client.get("/admin/bibliotecas").get_data(as_text=True))
        self.assertIn("Fila em dia!", self.client.get("/admin/curadoria").get_data(as_text=True))
        Livro.query.delete()
        db.session.commit()
        self.assertIn("Nenhum livro cadastrado", self.client.get("/admin/livros").get_data(as_text=True))


class GeoTest(InterfaceTestCase):
    def setUp(self):
        super().setUp()
        geo_service._viacep_cache.clear()
        self.user = self.login_as()

    def test_without_key_degrades_gracefully(self):
        with patch("services.geo.requests.get", FakeHttp()):
            data = self.client.get("/api/geo/01001000?numero=100").get_json()
        self.assertTrue(data["ok"])
        self.assertIsNone(data["mapa"])
        self.assertIn("não está configurada", data["mapa_mensagem"])
        self.assertEqual(data["endereco"]["cidade"], "São Paulo")

    def test_rooftop_with_number_is_exact_and_key_is_not_exposed(self):
        self.app.config["GOOGLE_MAPS_API_KEY"] = "CHAVE-SECRETA-TESTE"
        fake = FakeHttp(google=[google_ok(-23.5503, -46.6340, "APPROXIMATE"), google_ok(-23.5505, -46.6333)])
        with patch("services.geo.requests.get", fake):
            response = self.client.get("/api/geo/01001000?numero=100")
        body = response.get_data(as_text=True)
        data = response.get_json()
        self.assertNotIn("CHAVE-SECRETA-TESTE", body)
        self.assertTrue(data["mapa"]["preciso"])
        self.assertEqual(data["mapa"]["legenda"], "Localização exata do endereço")
        self.assertIn("output=embed", data["mapa"]["embed_url"])
        self.assertIn("100", fake.google_calls[1]["address"])
        self.assertEqual(GeoCache.query.count(), 2)
        # Segunda chamada usa o cache, sem nova consulta ao Google.
        with patch("services.geo.requests.get", FakeHttp()) as _:
            again = self.client.get("/api/geo/01001000?numero=100").get_json()
        self.assertTrue(again["mapa"]["preciso"])

    def test_approximate_without_number(self):
        self.app.config["GOOGLE_MAPS_API_KEY"] = "k"
        with patch("services.geo.requests.get", FakeHttp(google=[google_ok(-23.55, -46.63, "APPROXIMATE")])):
            data = self.client.get("/api/geo/01001000").get_json()
        self.assertFalse(data["mapa"]["preciso"])
        self.assertEqual(data["mapa"]["legenda"], "Localização aproximada do CEP")

    def test_distant_pin_alert(self):
        self.app.config["GOOGLE_MAPS_API_KEY"] = "k"
        fake = FakeHttp(google=[google_ok(-23.55, -46.63, "APPROXIMATE"), google_ok(-23.70, -46.63)])
        with patch("services.geo.requests.get", fake):
            data = self.client.get("/api/geo/01001000?numero=9999").get_json()
        self.assertTrue(data["mapa"]["pino_distante"])
        self.assertIn("km do centro do CEP", data["aviso"])

    def test_google_error_statuses_have_portuguese_messages(self):
        self.app.config["GOOGLE_MAPS_API_KEY"] = "k"
        casos = {
            "OVER_QUERY_LIMIT": "limite de consultas",
            "REQUEST_DENIED": "recusou a consulta",
            "ZERO_RESULTS": "Não encontramos esse endereço",
        }
        for status, trecho in casos.items():
            with self.subTest(status=status):
                GeoCache.query.delete()
                db.session.commit()
                with patch("services.geo.requests.get", FakeHttp(google=[{"status": status, "results": []}])):
                    data = self.client.get("/api/geo/01001000").get_json()
                self.assertTrue(data["ok"])
                self.assertIsNone(data["mapa"])
                self.assertIn(trecho, data["mapa_mensagem"])

    def test_network_failure(self):
        self.app.config["GOOGLE_MAPS_API_KEY"] = "k"
        with patch("services.geo.requests.get", FakeHttp(google=[requests.ConnectionError("x")])):
            data = self.client.get("/api/geo/01001000").get_json()
        self.assertIn("Não foi possível falar com o serviço de mapas", data["mapa_mensagem"])

    def test_cep_not_found_and_bad_format(self):
        with patch("services.geo.requests.get", FakeHttp(viacep={"erro": True})):
            response = self.client.get("/api/geo/99999999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get("/api/geo/123").status_code, 400)

    def test_street_divergence_and_service_area(self):
        with patch("services.geo.requests.get", FakeHttp()):
            data = self.client.get("/api/geo/01001000?logradouro=Rua das Flores").get_json()
        self.assertTrue(data["logradouro_divergente"])
        self.app.config["DELIVERY_STATES"] = ["RJ"]
        with patch("services.geo.requests.get", FakeHttp()):
            data = self.client.get("/api/geo/01001000").get_json()
        self.assertFalse(data["atendido"])
        self.assertIn("Ainda não entregamos em SP", data["area_mensagem"])

    def test_address_level_lookup_requires_login(self):
        self.client.post("/logout")
        self.assertEqual(self.client.get("/api/geo/01001000?numero=10").status_code, 401)


class CheckoutValidacaoTest(InterfaceTestCase):
    def setUp(self):
        super().setUp()
        geo_service._viacep_cache.clear()
        self.app.config.update(DEMO_PAYMENTS_ENABLED=True, MP_PAYMENTS_ENABLED=False, CEP_LOOKUP_ENABLED=True)
        self.login_as()
        livro = Livro.query.filter_by(titulo="Dom Casmurro").one()
        self.client.post("/carrinho/adicionar", data={"livro_id": livro.id, "tipo": "compra"})

    def payload(self, **extra):
        base = {
            "nome_completo": "Ana Clara Souza", "cpf": "529.982.247-25", "email": "ana@example.com",
            "telefone": "(11) 98765-4321", "modo_entrega": "domicilio", "cep": "01001-000",
            "logradouro": "Praça da Sé", "numero": "100", "bairro": "Sé", "cidade": "São Paulo",
            "estado": "SP", "termos_aceitos": True, "consentimento_dados": True,
            "demo_card_confirmed": True,
        }
        base.update(extra)
        return base

    def post(self, **extra):
        with patch("services.geo.requests.get", FakeHttp()):
            return self.client.post("/checkout/demo/cartao", json=self.payload(**extra))

    def test_consent_is_required_separately_from_terms(self):
        response = self.post(consentimento_dados=False)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["campo"], "consentimento_dados")

    def test_invalid_phone_cpf_and_name(self):
        self.assertEqual(self.post(telefone="(20) 98765-4321").get_json()["campo"], "telefone")
        self.assertEqual(self.post(cpf="111.111.111-11").get_json()["campo"], "cpf")
        self.assertEqual(self.post(nome_completo="Ana 2 Souza").get_json()["campo"], "nome_completo")

    def test_number_or_explicit_no_number(self):
        self.assertEqual(self.post(numero="").get_json()["campo"], "numero")
        self.assertEqual(self.post(numero="", sem_numero=True).status_code, 200)

    def test_street_divergence_requires_confirmation(self):
        response = self.post(logradouro="Rua das Flores")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["codigo"], "logradouro_divergente")
        self.assertEqual(self.post(logradouro="Rua das Flores", confirmar_logradouro=True).status_code, 200)

    def test_out_of_area_is_blocked(self):
        self.app.config["DELIVERY_STATES"] = ["RJ"]
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["codigo"], "fora_da_area")

    def test_city_must_match_cep(self):
        self.assertEqual(self.post(cidade="Campinas").get_json()["campo"], "cep")

    def test_success_records_terms_version_and_consent(self):
        data = self.post().get_json()
        self.assertTrue(data["ok"])
        tx = Transacao.query.one()
        self.assertTrue(tx.consentimento_dados)
        self.assertEqual(tx.termos_versao, self.app.config["TERMS_VERSION"])
        self.assertEqual(tx.frete, self.app.config["DELIVERY_FEE"])
        self.assertIn("/pedido/", data["sucesso_url"])
        page = self.client.get(data["sucesso_url"]).get_data(as_text=True)
        self.assertIn("Pedido confirmado!", page)
        self.assertIn("Próximos passos", page)


class NovasFuncionalidadesTest(InterfaceTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.login_as()
        self.livro = Livro.query.filter_by(titulo="Dom Casmurro").one()

    def test_isbn_search_with_or_without_hyphens(self):
        self.livro.isbn = "978-85-359-1484-9"
        db.session.commit()
        for termo in ("9788535914849", "978-85-359-1484-9", "978 85 359 1484 9"):
            with self.subTest(termo=termo):
                html = self.client.get(f"/livros?q={termo}").get_data(as_text=True)
                self.assertIn("Dom Casmurro", html)
                self.assertIn("1 obra encontrada", html)

    def test_wishlist_toggle(self):
        self.client.post(f"/livros/{self.livro.id}/favorito")
        self.assertEqual(ListaDesejo.query.count(), 1)
        self.assertIn("Nos seus favoritos", self.client.get(f"/livros/{self.livro.id}").get_data(as_text=True))
        self.client.post(f"/livros/{self.livro.id}/favorito")
        self.assertEqual(ListaDesejo.query.count(), 0)

    def test_waitlist_notifies_when_back_in_stock(self):
        estoque = self.livro.estoque
        self.livro.estoque = 0
        db.session.commit()
        self.assertIn("Avise-me quando voltar", self.client.get(f"/livros/{self.livro.id}").get_data(as_text=True))
        self.client.post(f"/livros/{self.livro.id}/avise-me")
        self.assertEqual(ListaEspera.query.count(), 1)
        self.livro.estoque = estoque
        db.session.commit()
        html = self.client.get("/perfil").get_data(as_text=True)
        self.assertIn("voltou ao estoque", html)
        self.client.get("/perfil")
        self.assertEqual(Notificacao.query.filter_by(tipo="estoque").count(), 1)

    def test_return_reminder_and_renewal(self):
        tx = Transacao(usuario_id=self.user.id, livro_id=self.livro.id, tipo="aluguel", status="ativa", pagamento_status="approved", valor_base=8, dias_aluguel=14, data_transacao=date.today() - timedelta(days=13), data_devolucao_prevista=date.today() + timedelta(days=1))
        db.session.add(tx)
        db.session.commit()
        html = self.client.get("/perfil").get_data(as_text=True)
        self.assertIn("Faltam", html)
        self.assertIn("Renovar aluguel", html)
        self.assertEqual(Notificacao.query.filter_by(tipo="prazo").count(), 1)
        self.client.post(f"/livros/transacoes/{tx.id}/renovar")
        db.session.refresh(tx)
        self.assertEqual(tx.data_devolucao_prevista, date.today() + timedelta(days=15))
        self.assertEqual(tx.renovacoes, 1)

    def test_renewal_blocked_without_stock(self):
        tx = Transacao(usuario_id=self.user.id, livro_id=self.livro.id, tipo="aluguel", status="ativa", pagamento_status="approved", valor_base=8, dias_aluguel=7, data_transacao=date.today(), data_devolucao_prevista=date.today() + timedelta(days=5))
        self.livro.estoque = 0
        db.session.add(tx)
        db.session.commit()
        self.client.post(f"/livros/transacoes/{tx.id}/renovar")
        db.session.refresh(tx)
        self.assertEqual(tx.renovacoes, 0)

    def test_also_bought_and_same_genre(self):
        outro = Livro.query.filter(Livro.id != self.livro.id).first()
        for livro in (self.livro, outro):
            db.session.add(Transacao(usuario_id=self.user.id, livro_id=livro.id, referencia_pedido="ref-1", tipo="compra", status="concluida", pagamento_status="approved", valor_base=10, data_transacao=date.today()))
        db.session.commit()
        html = self.client.get(f"/livros/{self.livro.id}").get_data(as_text=True)
        self.assertIn("Quem comprou também levou", html)
        self.assertIn(outro.titulo, html)
        self.assertIn(f"Mais de {self.livro.genero}", html)

    def test_library_filters_by_city_and_period(self):
        db.session.add_all([
            Biblioteca(nome="Unidade Manhã", cep="01001-000", endereco="Rua A, 1", cidade="São Paulo", estado="SP", horario_abertura="08:00", horario_fechamento="12:00"),
            Biblioteca(nome="Unidade Noite", cep="20031-144", endereco="Rua B, 2", cidade="Rio de Janeiro", estado="RJ", horario_abertura="17:00", horario_fechamento="22:00"),
        ])
        db.session.commit()
        html = self.client.get("/bibliotecas?periodo=noite").get_data(as_text=True)
        self.assertIn("Unidade Noite", html)
        self.assertNotIn("<h3>Unidade Manhã</h3>", html)
        html = self.client.get("/bibliotecas?cidade=São Paulo/SP").get_data(as_text=True)
        self.assertIn("<h3>Unidade Manhã</h3>", html)
        self.assertNotIn("<h3>Unidade Noite</h3>", html)
        self.assertIn("Mapa indisponível", html)

    def test_donation_transparency_hides_donor(self):
        from models.doacao import Doacao

        db.session.add(Doacao(titulo="Vidas Secas", autor="Graciliano Ramos", conservacao="Boa", biblioteca_entrega="X", usuario_id=self.user.id, status="Aprovada"))
        db.session.commit()
        html = self.client.get("/doacoes/transparencia").get_data(as_text=True)
        self.assertIn("Vidas Secas", html)
        self.assertNotIn(self.user.nome, html.split('<main')[1].split('</main>')[0])


if __name__ == "__main__":
    unittest.main()
