-- Atualiza um banco já criado com o schema antigo de checkout.
-- Faça backup e execute uma única vez. MySQL 8+.
USE biblioteca_db;

-- A conta de demonstração antiga usava uma senha pública conhecida; ela perde o papel admin.
UPDATE usuarios SET papel = 'cliente' WHERE email = 'admin@biblioteca.local' AND papel = 'admin';

-- Remove locais ilustrativos antigos apenas quando não existem pedidos ligados.
DELETE b FROM bibliotecas b
LEFT JOIN transacoes t ON t.biblioteca_id = b.id
WHERE b.nome IN ('Biblioteca Pública Mário de Andrade', 'Biblioteca Parque Villa-Lobos',
                 'Biblioteca Nacional do Brasil', 'Biblioteca Parque Estadual')
  AND t.id IS NULL;

ALTER TABLE livros
  ADD COLUMN capa_arquivo VARCHAR(120) NULL,
  MODIFY avaliacao DECIMAL(4,2) NOT NULL DEFAULT 0;
UPDATE livros SET avaliacao = 0;

ALTER TABLE transacoes
  ADD COLUMN referencia_pedido VARCHAR(36) NULL,
  ADD COLUMN payment_attempt_key VARCHAR(36) NULL,
  ADD COLUMN payment_id VARCHAR(80) NULL,
  ADD COLUMN pagamento_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  ADD COLUMN estoque_debitado BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN termos_aceitos BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN termos_versao VARCHAR(24) NULL,
  MODIFY status VARCHAR(24) NOT NULL DEFAULT 'aguardando_pagamento',
  MODIFY forma_pagamento VARCHAR(30) NOT NULL DEFAULT 'PIX',
  MODIFY modo_entrega VARCHAR(30) NOT NULL DEFAULT 'retirada';

CREATE INDEX ix_transacoes_referencia_pedido ON transacoes(referencia_pedido);
CREATE INDEX ix_transacoes_payment_id ON transacoes(payment_id);
CREATE INDEX ix_transacoes_pagamento_status ON transacoes(pagamento_status);

CREATE TABLE avaliacoes_livros (
  id INT NOT NULL AUTO_INCREMENT,
  livro_id INT NOT NULL,
  usuario_id INT NOT NULL,
  estrelas INT NOT NULL,
  comentario TEXT NOT NULL,
  criada_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_avaliacao_livro_usuario (livro_id,usuario_id),
  KEY ix_avaliacoes_livro_id (livro_id),
  KEY ix_avaliacoes_usuario_id (usuario_id),
  CONSTRAINT fk_avaliacoes_livro FOREIGN KEY (livro_id) REFERENCES livros(id) ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_avaliacoes_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT ck_avaliacao_estrelas_1_5 CHECK (estrelas >= 1 AND estrelas <= 5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
