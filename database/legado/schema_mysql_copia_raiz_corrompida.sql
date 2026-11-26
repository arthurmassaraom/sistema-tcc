-- Biblioteca Aberta: schema inicial completo para MySQL 8+
-- Uso: mysql -u root -p < schema_mysql.sql
-- Crie o usuário MySQL da aplicação com privilégios limitados; nunca use root em produção.
CREATE DATABASE IF NOT EXISTS biblioteca_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE biblioteca_db;

CREATE TABLE IF NOT EXISTS planos (
  id INT NOT NULL AUTO_INCREMENT,
  nome VARCHAR(80) NOT NULL,
  preco_mensal DECIMAL(10,2) NOT NULL DEFAULT 0,
  limite_alugueis INT NOT NULL DEFAULT 1,
  beneficios TEXT NOT NULL,
  PRIMARY KEY (i
  d), UNIQUE KEY uq_planos_nome (nome)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id), UNIQUE KEY uq_usuarios_email (email), UNIQUE KEY uq_usuarios_google_sub (google_sub), KEY ix_usuarios_plano_id (plano_id),
  CONSTRAINT fk_usuarios_plano FOREIGN KEY (plano_id) REFERENCES planos(id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS livros (
  id INT NOT NULL AUTO_INCREMENT,
  titulo VARCHAR(200) NOT NULL,
  autor VARCHAR(160) NOT NULL,
  editora VARCHAR(120) NOT NULL DEFAULT '',
  ano INT NULL,
  isbn VARCHAR(30) NULL,
  genero VARCHAR(80) NOT NULL DEFAULT 'Geral',
  categoria VARCHAR(100) NOT NULL DEFAULT 'Geral',
  modalidade VARCHAR(20) NOT NULL DEFAULT 'Ambos',
  estoque INT NOT NULL DEFAULT 0,
  preco_venda DECIMAL(10,2) NOT NULL DEFAULT 0,
  preco_aluguel DECIMAL(10,2) NOT NULL DEFAULT 0,
  resumo TEXT NOT NULL,
  avaliacao DECIMAL(4,2) NOT NULL DEFAULT 0 COMMENT 'Campo legado; não é exibido nem utilizado como nota',
  capa_arquivo VARCHAR(120) NULL,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id), UNIQUE KEY uq_livros_isbn (isbn), KEY ix_livros_titulo (titulo), KEY ix_livros_autor (autor),
  KEY ix_livros_genero (genero), KEY ix_livros_categoria (categoria), KEY ix_livros_ativo (ativo),
  CONSTRAINT chk_livros_estoque CHECK (estoque >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bibliotecas (
  id INT NOT NULL AUTO_INCREMENT,
  nome VARCHAR(160) NOT NULL,
  cep VARCHAR(12) NOT NULL,
  endereco VARCHAR(200) NOT NULL,
  cidade VARCHAR(100) NOT NULL,
  estado VARCHAR(2) NOT NULL,
  telefone VARCHAR(30) NOT NULL DEFAULT '',
  PRIMARY KEY (id), KEY ix_bibliotecas_cep (cep), KEY ix_bibliotecas_estado_cidade (estado,cidade)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS doacoes (
  id INT NOT NULL AUTO_INCREMENT,
  titulo VARCHAR(200) NOT NULL,
  autor VARCHAR(160) NOT NULL,
  editora VARCHAR(120) NOT NULL DEFAULT '',
  ano INT NULL,
  isbn VARCHAR(30) NULL,
  conservacao VARCHAR(50) NOT NULL,
  biblioteca_entrega VARCHAR(160) NOT NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'Aguardando Análise',
  justificativa TEXT NULL,
  usuario_id INT NOT NULL,
  criada_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id), KEY ix_doacoes_status (status), KEY ix_doacoes_usuario_id (usuario_id),
  CONSTRAINT fk_doacoes_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS transacoes (
  id INT NOT NULL AUTO_INCREMENT,
  usuario_id INT NOT NULL,
  livro_id INT NOT NULL,
  biblioteca_id INT NULL,
  referencia_pedido VARCHAR(36) NULL,
  payment_attempt_key VARCHAR(36) NULL,
  payment_id VARCHAR(80) NULL,
  pagamento_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  estoque_debitado BOOLEAN NOT NULL DEFAULT FALSE,
  termos_aceitos BOOLEAN NOT NULL DEFAULT FALSE,
  termos_versao VARCHAR(24) NULL,
  tipo VARCHAR(20) NOT NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'aguardando_pagamento',
  status_entrega VARCHAR(30) NOT NULL DEFAULT 'Pendente',
  quantidade INT NOT NULL DEFAULT 1,
  dias_aluguel INT NULL,
  valor_base DECIMAL(10,2) NOT NULL,
  frete DECIMAL(10,2) NOT NULL DEFAULT 0,
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
  multa DECIMAL(10,2) NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  KEY ix_transacoes_usuario_id (usuario_id), KEY ix_transacoes_livro_id (livro_id),
  KEY ix_transacoes_status (status), KEY ix_transacoes_biblioteca_id (biblioteca_id),
  KEY ix_transacoes_referencia_pedido (referencia_pedido), KEY ix_transacoes_payment_id (payment_id),
  KEY ix_transacoes_pagamento_status (pagamento_status),
  CONSTRAINT fk_transacoes_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_transacoes_livro FOREIGN KEY (livro_id) REFERENCES livros(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_transacoes_biblioteca FOREIGN KEY (biblioteca_id) REFERENCES bibliotecas(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_transacoes_quantidade CHECK (quantidade > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS avaliacoes_livros (
  id INT NOT NULL AUTO_INCREMENT,
  livro_id INT NOT NULL,
  usuario_id INT NOT NULL,
  estrelas INT NOT NULL,
  comentario TEXT NOT NULL,
  criada_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_avaliacao_livro_usuario (livro_id,usuario_id),
  KEY ix_avaliacoes_livro_id (livro_id), KEY ix_avaliacoes_usuario_id (usuario_id),
  CONSTRAINT fk_avaliacoes_livro FOREIGN KEY (livro_id) REFERENCES livros(id) ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_avaliacoes_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT ck_avaliacao_estrelas_1_5 CHECK (estrelas >= 1 AND estrelas <= 5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- O seed idempotente inclui planos informativos e livros. Unidades parceiras são cadastradas pela administração.
-- Nenhuma conta admin, senha ou credencial de pagamento é criada por este script.
