-- MIGRAÇÃO DE EXECUÇÃO ÚNICA para habilitar o login Google em um banco MySQL existente.
-- Faça backup antes e confirme que o schema ativo é biblioteca_db.
USE biblioteca_db;

ALTER TABLE usuarios
  ADD COLUMN google_sub VARCHAR(255) NULL,
  ADD UNIQUE KEY uq_usuarios_google_sub (google_sub);
