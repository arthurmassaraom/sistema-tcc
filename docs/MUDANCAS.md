# Revisão completa — Biblioteca Aberta (nov/2026)

Resumo das mudanças por etapa. Detalhes de configuração no README e em `.env.example`.

- **Etapa 1 — Cabeçalho e menus:** busca centralizada na viewport com sugestões (títulos/autores) navegáveis por teclado; lupa expansível no mobile; botão "Entrar" para visitantes; avatar + menu da conta (foco preso, Esc, clique fora); select acessível em todo o site; gaveta mobile.
- **Etapa 2 — Sacola lateral:** painel à direita com itens, quantidade, remover, entrega, totais fixos e sugestões; JSON + X-CSRF-Token nos endpoints existentes; aria-live; `/carrinho` completo sem JS; frete central em `DELIVERY_FEE`.
- **Etapas 3 e 4 — Responsividade e páginas:** breakpoints 480/768/1024; CSS por página; todas as páginas redesenhadas com estados vazios, skeletons e erros; tabelas admin viram cards; páginas 404/500/400/403/413.
- **Etapa 5 — Perfil e conta:** foto (Pillow, assinatura, 2 MB, 512 px, sem EXIF, nome aleatório); dados, e-mail com senha, senha; até 3 endereços com padrão; preferências; prazos com contagem regressiva; renovar; favoritos; minhas avaliações; excluir conta com anonimização; vincular/desvincular Google.
- **Etapa 6 — Mapas e validações:** `/api/geo/<cep>` (ViaCEP + Geocoding com cache, chave só no servidor), precisão ROOFTOP, pino distante, área de atendimento, distância da biblioteca; validação de CPF, telefone/DDD, e-mail, nome, CEP, número e logradouro no servidor e no navegador.
- **Etapa 7 — Legal:** termos ampliados (CDC art. 49, entrega, aluguel, estorno, modo demo); `/privacidade` e `/cookies`; consentimento separado no cadastro e checkout; versões registradas.
- **Etapa 8 — Código e segurança:** `AUTO_INIT_DATABASE`; usuário carregado uma vez por requisição; `no-store` só onde há dados do usuário; SQL organizado em `database/`; migração aditiva automática também para MySQL; `.env.example`; macros e componentes reutilizáveis.
- **Etapa 9 — Novidades:** "Quem comprou também levou" e mesmo gênero; lista de espera; ISBN com/sem hífen; avisos internos; transparência de doações; unidades com filtro por cidade e horário e mapa.
