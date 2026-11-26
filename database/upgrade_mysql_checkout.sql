-- MIGRAÇÃO DE EXECUÇÃO ÚNICA para banco criado pelo schema_mysql.sql anterior.
-- Faça backup antes. Se usar um schema novo, NÃO execute este arquivo.
USE biblioteca_db;

ALTER TABLE usuarios
  ADD COLUMN cpf VARCHAR(14) NULL,
  ADD COLUMN telefone VARCHAR(30) NULL;

ALTER TABLE livros
  ADD COLUMN resumo TEXT NULL,
  ADD COLUMN avaliacao FLOAT NOT NULL DEFAULT 4.5;
UPDATE livros SET resumo='Uma leitura selecionada pelo acervo comunitário.' WHERE resumo IS NULL;
ALTER TABLE livros MODIFY resumo TEXT NOT NULL;

ALTER TABLE transacoes
  ADD COLUMN biblioteca_id INT NULL,
  ADD COLUMN status_entrega VARCHAR(30) NOT NULL DEFAULT 'Pendente',
  ADD COLUMN quantidade INT NOT NULL DEFAULT 1,
  ADD COLUMN dias_aluguel INT NULL,
  ADD COLUMN frete FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN forma_pagamento VARCHAR(30) NOT NULL DEFAULT 'Simulação',
  ADD COLUMN modo_entrega VARCHAR(30) NOT NULL DEFAULT 'Retirada',
  ADD COLUMN nome_completo VARCHAR(160) NULL,
  ADD COLUMN cpf VARCHAR(14) NULL,
  ADD COLUMN email_contato VARCHAR(160) NULL,
  ADD COLUMN telefone VARCHAR(30) NULL,
  ADD COLUMN endereco_entrega VARCHAR(300) NULL,
  ADD COLUMN cep_entrega VARCHAR(12) NULL,
  ADD COLUMN cidade_entrega VARCHAR(100) NULL,
  ADD COLUMN estado_entrega VARCHAR(2) NULL;

ALTER TABLE transacoes
  ADD KEY ix_transacoes_biblioteca_id (biblioteca_id),
  ADD CONSTRAINT fk_transacoes_biblioteca FOREIGN KEY (biblioteca_id)
    REFERENCES bibliotecas(id) ON UPDATE CASCADE ON DELETE RESTRICT;

-- Após a migração, inicie a aplicação: seed.py acrescentará os livros e bibliotecas ausentes.
