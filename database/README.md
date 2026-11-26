# Banco de dados (MySQL)

| Arquivo | Quando usar |
|---|---|
| `schema_mysql.sql` | Instalação **nova**. Já contém todas as tabelas e colunas atuais. |
| `upgrade_mysql_checkout.sql` | Bancos anteriores ao checkout (legado). |
| `upgrade_mysql_project.sql` | Bancos criados com o schema da versão com checkout. |
| `upgrade_mysql_google_login.sql` | Adiciona `google_sub` em bancos antigos. |
| `upgrade_mysql_2026_11_interface.sql` | Revisão de interface: foto, endereços, favoritos, lista de espera, avisos, cache de mapas, horários das unidades. |
| `legado/` | Arquivos antigos mantidos só para consulta (não executar). |

Ordem para um banco antigo: `upgrade_mysql_checkout.sql` → `upgrade_mysql_project.sql` → `upgrade_mysql_google_login.sql` (se ainda não tiver `google_sub`) → `upgrade_mysql_2026_11_interface.sql`.
Sempre faça backup antes e execute cada script uma única vez.

Com SQLite (desenvolvimento), as colunas novas são adicionadas automaticamente por `services/sqlite_migrations.py` e as tabelas novas por `db.create_all()` quando `AUTO_INIT_DATABASE=true`.
