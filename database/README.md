# Banco de dados

Há um único arquivo SQL: `schema_mysql.sql`. Ele contém a estrutura completa do banco MySQL 8+ (sem dados).

- Instalação nova: crie o banco com `utf8mb4` e rode o arquivo, conforme o comentário no topo.
- Instalação existente: com `AUTO_INIT_DATABASE=true` (padrão), o sistema cria tabelas e colunas novas sozinho ao iniciar. Não é preciso rodar nenhum SQL.
- Os dados iniciais (planos, bibliotecas e acervo de exemplo) são criados por `seed.py`.
