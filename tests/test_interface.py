import os

os.environ.setdefault("AUTO_INIT_DATABASE", "false")

import unittest  # noqa: E402

from app import create_app  # noqa: E402
from database import db  # noqa: E402
from models.livro import Livro  # noqa: E402
from models.usuario import Usuario  # noqa: E402
from services.ui import avatar_hue, iniciais  # noqa: E402


class InterfaceTestCase(unittest.TestCase):
    """Base compartilhada: app isolado em SQLite em memória com o seed padrão."""

    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SECRET_KEY": "interface-test-secret",
                "AUTO_INIT_DATABASE": True,
                "CEP_LOOKUP_ENABLED": False,
                "GOOGLE_MAPS_API_KEY": "",
                "GOOGLE_CLIENT_ID": "",
                "GOOGLE_CLIENT_SECRET": "",
            }
        )
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def login_as(self, nome="Ana Clara Souza", email="ana@example.com", papel="cliente"):
        user = Usuario(nome=nome, email=email, papel=papel)
        user.set_senha("senha-segura-123")
        db.session.add(user)
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = user.id
        return user


class HeaderTest(InterfaceTestCase):
    def test_visitor_sees_sign_in_button_instead_of_account_menu(self):
        html = self.client.get("/livros").get_data(as_text=True)
        self.assertIn('class="button button-signin"', html)
        self.assertIn("next=/livros", html.replace("%2F", "/"))
        self.assertNotIn('id="menu-conta"', html)
        self.assertIn('role="search"', html)
        self.assertIn('name="q"', html)
        self.assertIn('action="/livros"', html)

    def test_logged_user_sees_avatar_and_styled_account_menu(self):
        self.login_as()
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="menu-conta" role="menu"', html)
        self.assertIn(">AS</span>", html)  # iniciais de Ana Clara Souza
        for item in ("Meu perfil", "Meus pedidos", "Favoritos", "Configurações", "Sair da conta"):
            self.assertIn(item, html)
        self.assertEqual(html.count('role="menuitem"'), 5)
        self.assertIn("ana@example.com", html)
        self.assertNotIn("button-signin", html)

    def test_mobile_drawer_and_current_page_marker(self):
        html = self.client.get("/planos").get_data(as_text=True)
        self.assertIn('id="menu-mobile" role="dialog" aria-modal="true"', html)
        self.assertIn('href="/planos" aria-current="page"', html)
        self.assertIn('data-search-open', html)

    def test_footer_lists_navigation_contact_and_legal_links(self):
        html = self.client.get("/").get_data(as_text=True)
        footer = html[html.index('<footer class="site-footer">'):]
        for text in ("Explore", "Sua conta", "Legal", "Contato e instituição", "/termos", "CNPJ"):
            self.assertIn(text, footer)

    def test_empty_business_data_shows_not_informed(self):
        self.app.config.update(BUSINESS_CNPJ="", BUSINESS_ADDRESS="", BUSINESS_EMAIL="")
        footer = self.client.get("/").get_data(as_text=True).split('<footer class="site-footer">')[1]
        self.assertGreaterEqual(footer.count("Não informado"), 3)

    def test_icons_use_local_sprite(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("/static/icons/sprite.svg#i-shopping-bag", html)
        self.assertTrue(os.path.exists(os.path.join(self.app.static_folder, "icons", "sprite.svg")))


class SearchSuggestionsTest(InterfaceTestCase):
    def test_short_query_returns_empty_lists(self):
        data = self.client.get("/api/livros/sugestoes?q=a").get_json()
        self.assertEqual(data["livros"], [])
        self.assertEqual(data["autores"], [])

    def test_returns_titles_and_authors_with_links(self):
        data = self.client.get("/api/livros/sugestoes?q=machado").get_json()
        self.assertTrue(any(item["titulo"] == "Dom Casmurro" for item in data["livros"]))
        self.assertIn("Machado de Assis", [autor["nome"] for autor in data["autores"]])
        livro = Livro.query.filter_by(titulo="Dom Casmurro").one()
        self.assertIn(f"/livros/{livro.id}", [item["url"] for item in data["livros"]])

    def test_like_wildcards_are_literal(self):
        data = self.client.get("/api/livros/sugestoes?q=%25%25").get_json()
        self.assertEqual(data["livros"], [])

    def test_inactive_books_are_not_suggested(self):
        livro = Livro.query.filter_by(titulo="Dom Casmurro").one()
        livro.ativo = False
        db.session.commit()
        data = self.client.get("/api/livros/sugestoes?q=casmurro").get_json()
        self.assertEqual(data["livros"], [])


class AvatarHelpersTest(unittest.TestCase):
    def test_initials(self):
        self.assertEqual(iniciais("ana clara souza"), "AS")
        self.assertEqual(iniciais("Bruno"), "B")
        self.assertEqual(iniciais(""), "?")

    def test_hue_is_stable_and_in_range(self):
        self.assertEqual(avatar_hue("Ana"), avatar_hue(" ana "))
        self.assertTrue(0 <= avatar_hue("Qualquer Nome") < 360)


if __name__ == "__main__":
    unittest.main()
