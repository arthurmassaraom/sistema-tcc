-- Migração da revisão de interface (perfil, endereços, mapas, avisos, lista de espera).
-- Para bancos MySQL 8+ JÁ EXISTENTES. Faça backup e execute UMA ÚNICA VEZ.
-- Não execute em banco novo criado pelo schema_mysql.sql atualizado (ele já contém tudo isto).
USE biblioteca_db;

ALTER TABLE usuarios
  ADD COLUMN foto VARCHAR(80) NULL,
  ADD COLUMN ativo TINYINT(1) NOT NULL DEFAULT 1,
  ADD COLUMN notif_pedido TINYINT(1) NOT NULL DEFAULT 1,
  ADD COLUMN notif_devolucao TINYINT(1) NOT NULL DEFAULT 1,
  ADD COLUMN notif_retirada TINYINT(1) NOT NULL DEFAULT 1,
  ADD COLUMN termos_versao_aceita VARCHAR(24) NULL,
  ADD COLUMN consentimento_versao VARCHAR(24) NULL,
  ADD COLUMN consentimento_em DATETIME NULL,
  ADD COLUMN senha_definida TINYINT(1) NOT NULL DEFAULT 1;

ALTER TABLE bibliotecas
  ADD COLUMN dias_funcionamento VARCHAR(80) NULL,
  ADD COLUMN horario_abertura VARCHAR(5) NULL,
  ADD COLUMN horario_fechamento VARCHAR(5) NULL,
  ADD COLUMN latitude DOUBLE NULL,
  ADD COLUMN longitude DOUBLE NULL;

ALTER TABLE transacoes
  ADD COLUMN consentimento_dados TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN renovacoes INT NOT NULL DEFAULT 0;

-- Tabelas da revisão de interface (endereços, favoritos, lista de espera, avisos, cache de mapas).
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
  PRIMARY KEY (id), KEY ix_enderecos_usuario_id (usuario_id),
  CONSTRAINT fk_enderecos_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lista_desejos (
  id INT NOT NULL AUTO_INCREMENT,
  usuario_id INT NOT NULL,
  livro_id INT NOT NULL,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id), UNIQUE KEY uq_desejo_usuario_livro (usuario_id, livro_id), KEY ix_lista_desejos_livro_id (livro_id),
  CONSTRAINT fk_desejos_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
  CONSTRAINT fk_desejos_livro FOREIGN KEY (livro_id) REFERENCES livros(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lista_espera (
  id INT NOT NULL AUTO_INCREMENT,
  usuario_id INT NOT NULL,
  livro_id INT NOT NULL,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  notificado_em DATETIME NULL,
  PRIMARY KEY (id), UNIQUE KEY uq_espera_usuario_livro (usuario_id, livro_id), KEY ix_lista_espera_livro_id (livro_id),
  CONSTRAINT fk_espera_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
  CONSTRAINT fk_espera_livro FOREIGN KEY (livro_id) REFERENCES livros(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  PRIMARY KEY (id), UNIQUE KEY uq_notificacao_chave (usuario_id, chave),
  CONSTRAINT fk_notificacoes_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  PRIMARY KEY (id), UNIQUE KEY uq_geo_cache_chave (chave), KEY ix_geo_cache_cep (cep)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
