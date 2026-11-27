-- =====================================================================
-- Biblioteca Aberta: estrutura completa do banco MySQL (MySQL 8+).
--
-- Este é o ÚNICO arquivo SQL do projeto. Ele cria todas as tabelas com a
-- versão atual do sistema. Não contém dados: planos, bibliotecas e o
-- acervo de exemplo são criados pelo seed.py na primeira inicialização
-- (AUTO_INIT_DATABASE=true), ou manualmente se você desligá-la.
--
-- Uso (instalação nova):
--   mysql -u root -p -e "CREATE DATABASE biblioteca_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
--   mysql -u root -p biblioteca_db < database/schema_mysql.sql
--
-- Se o banco já existe com a estrutura antiga, o sistema aplica as colunas
-- e tabelas novas sozinho quando AUTO_INIT_DATABASE=true. Não rode este
-- arquivo sobre um banco com dados: ele usa CREATE TABLE IF NOT EXISTS e
-- não altera tabelas existentes.
-- =====================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------------------------- planos
CREATE TABLE IF NOT EXISTS planos (
  id INT NOT NULL AUTO_INCREMENT,
  nome VARCHAR(80) NOT NULL,
  preco_mensal DOUBLE NOT NULL DEFAULT 0,
  limite_alugueis INT NOT NULL DEFAULT 1,
  beneficios TEXT NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_planos_nome (nome)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------- bibliotecas
CREATE TABLE IF NOT EXISTS bibliotecas (
  id INT NOT NULL AUTO_INCREMENT,
  nome VARCHAR(160) NOT NULL,
  cep VARCHAR(12) NOT NULL,
  endereco VARCHAR(200) NOT NULL,
  cidade VARCHAR(100) NOT NULL,
  estado VARCHAR(2) NOT NULL,
  telefone VARCHAR(30) DEFAULT '',
  dias_funcionamento VARCHAR(80) NULL,
  horario_abertura VARCHAR(5) NULL,
  horario_fechamento VARCHAR(5) NULL,
  latitude DOUBLE NULL,
  longitude DOUBLE NULL,
  PRIMARY KEY (id),
  KEY ix_bibliotecas_cep (cep)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------------- livros
CREATE TABLE IF NOT EXISTS livros (
  id INT NOT NULL AUTO_INCREMENT,
  titulo VARCHAR(200) NOT NULL,
  autor VARCHAR(160) NOT NULL,
  editora VARCHAR(120) DEFAULT '',
  ano INT NULL,
  isbn VARCHAR(30) NULL,
  genero VARCHAR(80) NOT NULL DEFAULT 'Geral',
  categoria VARCHAR(100) NOT NULL DEFAULT 'Geral',
  modalidade VARCHAR(20) NOT NULL DEFAULT 'Ambos',
  estoque INT NOT NULL DEFAULT 0,            -- soma dos exemplares em todas as bibliotecas
  preco_venda DOUBLE NOT NULL DEFAULT 0,
  preco_aluguel DOUBLE NOT NULL DEFAULT 0,   -- valor para 14 dias; outros prazos são proporcionais
  resumo TEXT NOT NULL,
  avaliacao DOUBLE NOT NULL DEFAULT 0,
  capa_arquivo VARCHAR(120) NULL,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_livros_isbn (isbn),
  KEY ix_livros_titulo (titulo),
  KEY ix_livros_autor (autor),
  KEY ix_livros_genero (genero),
  KEY ix_livros_categoria (categoria),
  KEY ix_livros_ativo (ativo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------- estoque por biblioteca
CREATE TABLE IF NOT EXISTS estoque_bibliotecas (
  id INT NOT NULL AUTO_INCREMENT,
  biblioteca_id INT NOT NULL,
  livro_id INT NOT NULL,
  quantidade INT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_estoque_biblioteca_livro (biblioteca_id, livro_id),
  KEY ix_estoque_biblioteca (biblioteca_id),
  KEY ix_estoque_livro (livro_id),
  CONSTRAINT fk_estoque_biblioteca FOREIGN KEY (biblioteca_id) REFERENCES bibliotecas (id),
  CONSTRAINT fk_estoque_livro FOREIGN KEY (livro_id) REFERENCES livros (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------- usuarios
CREATE TABLE IF NOT EXISTS usuarios (
  id INT NOT NULL AUTO_INCREMENT,
  nome VARCHAR(120) NOT NULL,
  email VARCHAR(160) NOT NULL,
  google_sub VARCHAR(255) NULL,
  senha_hash VARCHAR(255) NOT NULL,
  papel VARCHAR(20) NOT NULL DEFAULT 'cliente',
  cpf VARCHAR(14) NULL,
  telefone VARCHAR(30) NULL,
  plano_id INT NULL,
  foto VARCHAR(80) NULL,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  notif_pedido TINYINT(1) NOT NULL DEFAULT 1,
  notif_devolucao TINYINT(1) NOT NULL DEFAULT 1,
  notif_retirada TINYINT(1) NOT NULL DEFAULT 1,
  termos_versao_aceita VARCHAR(24) NULL,
  consentimento_versao VARCHAR(24) NULL,
  consentimento_em DATETIME NULL,
  senha_definida TINYINT(1) NOT NULL DEFAULT 1,
  two_fa_ativo TINYINT(1) NOT NULL DEFAULT 0,
  two_fa_codigo_hash VARCHAR(255) NULL,
  two_fa_expira_em DATETIME NULL,
  two_fa_tentativas INT NOT NULL DEFAULT 0,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_usuarios_email (email),
  UNIQUE KEY uq_usuarios_google_sub (google_sub),
  CONSTRAINT fk_usuarios_plano FOREIGN KEY (plano_id) REFERENCES planos (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------------- enderecos
CREATE TABLE IF NOT EXISTS enderecos (
  id INT NOT NULL AUTO_INCREMENT,
  usuario_id INT NOT NULL,
  rotulo VARCHAR(40) NOT NULL DEFAULT 'Casa',
  cep VARCHAR(9) NOT NULL,
  logradouro VARCHAR(160) NOT NULL,
  numero VARCHAR(20) NULL,
  sem_numero TINYINT(1) NOT NULL DEFAULT 0,
  complemento VARCHAR(80) NULL,
  bairro VARCHAR(100) NOT NULL,
  cidade VARCHAR(100) NOT NULL,
  uf VARCHAR(2) NOT NULL,
  padrao TINYINT(1) NOT NULL DEFAULT 0,
  latitude DOUBLE NULL,
  longitude DOUBLE NULL,
  location_type VARCHAR(30) NULL,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_enderecos_usuario (usuario_id),
  CONSTRAINT fk_enderecos_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------- transacoes
CREATE TABLE IF NOT EXISTS transacoes (
  id INT NOT NULL AUTO_INCREMENT,
  usuario_id INT NOT NULL,
  livro_id INT NOT NULL,
  biblioteca_id INT NULL,
  referencia_pedido VARCHAR(36) NULL,
  payment_attempt_key VARCHAR(36) NULL,
  payment_id VARCHAR(80) NULL,
  pagamento_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  estoque_debitado TINYINT(1) NOT NULL DEFAULT 0,
  termos_aceitos TINYINT(1) NOT NULL DEFAULT 0,
  termos_versao VARCHAR(24) NULL,
  consentimento_dados TINYINT(1) NOT NULL DEFAULT 0,
  renovacoes INT NOT NULL DEFAULT 0,
  tipo VARCHAR(20) NOT NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'aguardando_pagamento',
  status_entrega VARCHAR(30) NOT NULL DEFAULT 'Pendente',
  quantidade INT NOT NULL DEFAULT 1,
  dias_aluguel INT NULL,
  valor_base DOUBLE NOT NULL,
  frete DOUBLE NOT NULL DEFAULT 0,
  forma_pagamento VARCHAR(30) NOT NULL DEFAULT 'PIX',
  modo_entrega VARCHAR(30) NOT NULL DEFAULT 'retirada',
  nome_completo VARCHAR(160) NULL,
  cpf VARCHAR(14) NULL,
  email_contato VARCHAR(160) NULL,
  telefone VARCHAR(30) NULL,
  endereco_entrega VARCHAR(300) NULL,
  cep_entrega VARCHAR(12) NULL,
  cidade_entrega VARCHAR(100) NULL,
  estado_entrega VARCHAR(2) NULL,
  data_transacao DATE NOT NULL,
  data_devolucao_prevista DATE NULL,
  data_devolucao DATE NULL,
  multa DOUBLE NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  KEY ix_transacoes_usuario (usuario_id),
  KEY ix_transacoes_livro (livro_id),
  KEY ix_transacoes_biblioteca (biblioteca_id),
  KEY ix_transacoes_referencia (referencia_pedido),
  KEY ix_transacoes_payment_id (payment_id),
  KEY ix_transacoes_pagamento_status (pagamento_status),
  KEY ix_transacoes_status (status),
  CONSTRAINT fk_transacoes_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE RESTRICT,
  CONSTRAINT fk_transacoes_livro FOREIGN KEY (livro_id) REFERENCES livros (id) ON DELETE RESTRICT,
  CONSTRAINT fk_transacoes_biblioteca FOREIGN KEY (biblioteca_id) REFERENCES bibliotecas (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------- alocações de estoque por pedido
CREATE TABLE IF NOT EXISTS alocacoes_estoque (
  id INT NOT NULL AUTO_INCREMENT,
  transacao_id INT NOT NULL,
  biblioteca_id INT NOT NULL,
  livro_id INT NOT NULL,
  quantidade INT NOT NULL,
  PRIMARY KEY (id),
  KEY ix_alocacao_transacao (transacao_id),
  CONSTRAINT fk_alocacao_transacao FOREIGN KEY (transacao_id) REFERENCES transacoes (id),
  CONSTRAINT fk_alocacao_biblioteca FOREIGN KEY (biblioteca_id) REFERENCES bibliotecas (id),
  CONSTRAINT fk_alocacao_livro FOREIGN KEY (livro_id) REFERENCES livros (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------- avaliacoes
CREATE TABLE IF NOT EXISTS avaliacoes_livros (
  id INT NOT NULL AUTO_INCREMENT,
  livro_id INT NOT NULL,
  usuario_id INT NOT NULL,
  estrelas INT NOT NULL,
  comentario TEXT NOT NULL,
  criada_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_avaliacao_livro_usuario (livro_id, usuario_id),
  KEY ix_avaliacoes_livro (livro_id),
  KEY ix_avaliacoes_usuario (usuario_id),
  CONSTRAINT fk_avaliacoes_livro FOREIGN KEY (livro_id) REFERENCES livros (id) ON DELETE CASCADE,
  CONSTRAINT fk_avaliacoes_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ lista_desejos
CREATE TABLE IF NOT EXISTS lista_desejos (
  id INT NOT NULL AUTO_INCREMENT,
  usuario_id INT NOT NULL,
  livro_id INT NOT NULL,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_desejo_usuario_livro (usuario_id, livro_id),
  KEY ix_desejos_usuario (usuario_id),
  KEY ix_desejos_livro (livro_id),
  CONSTRAINT fk_desejos_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE,
  CONSTRAINT fk_desejos_livro FOREIGN KEY (livro_id) REFERENCES livros (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------- lista_espera
CREATE TABLE IF NOT EXISTS lista_espera (
  id INT NOT NULL AUTO_INCREMENT,
  usuario_id INT NOT NULL,
  livro_id INT NOT NULL,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  notificado_em DATETIME NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_espera_usuario_livro (usuario_id, livro_id),
  KEY ix_espera_usuario (usuario_id),
  KEY ix_espera_livro (livro_id),
  CONSTRAINT fk_espera_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE,
  CONSTRAINT fk_espera_livro FOREIGN KEY (livro_id) REFERENCES livros (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------- notificacoes
CREATE TABLE IF NOT EXISTS notificacoes (
  id INT NOT NULL AUTO_INCREMENT,
  usuario_id INT NOT NULL,
  tipo VARCHAR(30) NOT NULL DEFAULT 'aviso',
  titulo VARCHAR(160) NOT NULL,
  mensagem VARCHAR(400) NOT NULL DEFAULT '',
  url VARCHAR(300) NULL,
  chave VARCHAR(120) NOT NULL,
  lida TINYINT(1) NOT NULL DEFAULT 0,
  criada_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_notificacao_chave (usuario_id, chave),
  KEY ix_notificacoes_usuario (usuario_id),
  CONSTRAINT fk_notificacoes_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------- doacoes
CREATE TABLE IF NOT EXISTS doacoes (
  id INT NOT NULL AUTO_INCREMENT,
  titulo VARCHAR(200) NOT NULL,
  autor VARCHAR(160) NOT NULL,
  editora VARCHAR(120) DEFAULT '',
  ano INT NULL,
  isbn VARCHAR(30) NULL,
  conservacao VARCHAR(50) NOT NULL,
  biblioteca_entrega VARCHAR(160) NOT NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'Aguardando Análise',
  justificativa TEXT NULL,
  usuario_id INT NOT NULL,
  criada_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_doacoes_status (status),
  KEY ix_doacoes_usuario (usuario_id),
  CONSTRAINT fk_doacoes_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------- geo_cache
CREATE TABLE IF NOT EXISTS geo_cache (
  id INT NOT NULL AUTO_INCREMENT,
  chave VARCHAR(255) NOT NULL,
  cep VARCHAR(8) NOT NULL,
  latitude DOUBLE NULL,
  longitude DOUBLE NULL,
  location_type VARCHAR(30) NULL,
  endereco_formatado VARCHAR(300) NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'OK',
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_geo_cache_chave (chave),
  KEY ix_geo_cache_cep (cep)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
