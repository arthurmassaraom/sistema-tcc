from sqlalchemy import inspect, text
from database import db

# Colunas introduzidas pelo sistema de checkout/reviews ao longo das versões do protótipo.
_SQLITE_COLUMNS = {
    "usuarios": {
        "cpf": "VARCHAR(14) NULL",
        "telefone": "VARCHAR(30) NULL",
        "google_sub": "VARCHAR(255) NULL",
        "foto": "VARCHAR(80) NULL",
        "ativo": "BOOLEAN NOT NULL DEFAULT 1",
        "notif_pedido": "BOOLEAN NOT NULL DEFAULT 1",
        "notif_devolucao": "BOOLEAN NOT NULL DEFAULT 1",
        "notif_retirada": "BOOLEAN NOT NULL DEFAULT 1",
        "termos_versao_aceita": "VARCHAR(24) NULL",
        "consentimento_versao": "VARCHAR(24) NULL",
        "consentimento_em": "DATETIME NULL",
        "senha_definida": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "bibliotecas": {
        "dias_funcionamento": "VARCHAR(80) NULL",
        "horario_abertura": "VARCHAR(5) NULL",
        "horario_fechamento": "VARCHAR(5) NULL",
        "latitude": "FLOAT NULL",
        "longitude": "FLOAT NULL",
    },
    "livros": {
        "resumo": "TEXT NOT NULL DEFAULT ''",
        "avaliacao": "FLOAT NOT NULL DEFAULT 0",
        "capa_arquivo": "VARCHAR(120) NULL",
    },
    "transacoes": {
        "biblioteca_id": "INTEGER NULL",
        "status_entrega": "VARCHAR(30) NOT NULL DEFAULT 'Pendente'",
        "quantidade": "INTEGER NOT NULL DEFAULT 1",
        "dias_aluguel": "INTEGER NULL",
        "frete": "FLOAT NOT NULL DEFAULT 0",
        "forma_pagamento": "VARCHAR(30) NOT NULL DEFAULT 'PIX'",
        "modo_entrega": "VARCHAR(30) NOT NULL DEFAULT 'retirada'",
        "nome_completo": "VARCHAR(160) NULL",
        "cpf": "VARCHAR(14) NULL",
        "email_contato": "VARCHAR(160) NULL",
        "telefone": "VARCHAR(30) NULL",
        "endereco_entrega": "VARCHAR(300) NULL",
        "cep_entrega": "VARCHAR(12) NULL",
        "cidade_entrega": "VARCHAR(100) NULL",
        "estado_entrega": "VARCHAR(2) NULL",
        "data_devolucao_prevista": "DATE NULL",
        "referencia_pedido": "VARCHAR(36) NULL",
        "payment_attempt_key": "VARCHAR(36) NULL",
        "payment_id": "VARCHAR(80) NULL",
        "pagamento_status": "VARCHAR(32) NOT NULL DEFAULT 'pending'",
        "estoque_debitado": "BOOLEAN NOT NULL DEFAULT 0",
        "termos_aceitos": "BOOLEAN NOT NULL DEFAULT 0",
        "termos_versao": "VARCHAR(24) NULL",
        "consentimento_dados": "BOOLEAN NOT NULL DEFAULT 0",
        "renovacoes": "INTEGER NOT NULL DEFAULT 0",
    },
}

_LEGACY_DEMO_LIBRARIES = (
    "Biblioteca Pública Mário de Andrade",
    "Biblioteca Parque Villa-Lobos",
    "Biblioteca Nacional do Brasil",
    "Biblioteca Parque Estadual",
)


def upgrade_legacy_sqlite():
    """Aplica colunas/índices ausentes ao SQLite antigo; a migração MySQL usa scripts SQL próprios."""
    if db.engine.dialect.name != "sqlite":
        return
    inspector = inspect(db.engine)
    with db.engine.begin() as connection:
        migration_version = connection.exec_driver_sql("PRAGMA user_version").scalar() or 0
        for table, columns in _SQLITE_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspect(db.engine).get_columns(table)}
            for name, declaration in columns.items():
                if name not in existing:
                    connection.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {declaration}')
                    )
                    existing.add(name)
        if inspector.has_table("transacoes"):
            for column in ("referencia_pedido", "payment_id", "pagamento_status", "biblioteca_id"):
                connection.execute(
                    text(
                        f'CREATE INDEX IF NOT EXISTS ix_transacoes_{column} ON transacoes("{column}")'
                    )
                )
        if inspector.has_table("usuarios") and migration_version < 1:
            # Desativa uma única vez a conta de demonstração com senha conhecida das versões antigas.
            connection.execute(
                text(
                    "UPDATE usuarios SET papel='cliente' WHERE email='admin@biblioteca.local' AND papel='admin'"
                )
            )
        if inspector.has_table("usuarios"):
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_google_sub "
                    "ON usuarios(google_sub)"
                )
            )
        if inspector.has_table("livros"):
            # Notas pré-preenchidas antigas não são avaliações de leitores.
            connection.execute(text("UPDATE livros SET avaliacao=0 WHERE avaliacao IS NOT NULL"))
        if inspector.has_table("bibliotecas") and inspector.has_table("transacoes"):
            connection.execute(
                text(
                    "DELETE FROM bibliotecas WHERE nome IN ("
                    "'Biblioteca Pública Mário de Andrade','Biblioteca Parque Villa-Lobos',"
                    "'Biblioteca Nacional do Brasil','Biblioteca Parque Estadual') "
                    "AND id NOT IN (SELECT biblioteca_id FROM transacoes WHERE biblioteca_id IS NOT NULL)"
                )
            )
        if migration_version < 1:
            # Marca o rebaixamento do admin demo como concluído para não desfazer uma promoção segura futura.
            connection.exec_driver_sql("PRAGMA user_version = 1")


# Colunas introduzidas na revisão de interface, com o tipo em MySQL.
_COLUNAS_INTERFACE_MYSQL = {
    "usuarios": {
        "foto": "VARCHAR(80) NULL",
        "ativo": "TINYINT(1) NOT NULL DEFAULT 1",
        "notif_pedido": "TINYINT(1) NOT NULL DEFAULT 1",
        "notif_devolucao": "TINYINT(1) NOT NULL DEFAULT 1",
        "notif_retirada": "TINYINT(1) NOT NULL DEFAULT 1",
        "termos_versao_aceita": "VARCHAR(24) NULL",
        "consentimento_versao": "VARCHAR(24) NULL",
        "consentimento_em": "DATETIME NULL",
        "senha_definida": "TINYINT(1) NOT NULL DEFAULT 1",
    },
    "bibliotecas": {
        "dias_funcionamento": "VARCHAR(80) NULL",
        "horario_abertura": "VARCHAR(5) NULL",
        "horario_fechamento": "VARCHAR(5) NULL",
        "latitude": "DOUBLE NULL",
        "longitude": "DOUBLE NULL",
    },
    "transacoes": {
        "consentimento_dados": "TINYINT(1) NOT NULL DEFAULT 0",
        "renovacoes": "INT NOT NULL DEFAULT 0",
    },
}


def upgrade_interface_columns():
    """Adiciona (somente) as colunas novas ausentes em bancos MySQL existentes.

    É aditivo e idempotente: nunca remove nem altera colunas e dados. O mesmo
    conteúdo está em database/upgrade_mysql_2026_11_interface.sql para quem
    preferir migrar manualmente com AUTO_INIT_DATABASE=false.
    """
    if db.engine.dialect.name != "mysql":
        return
    inspector = inspect(db.engine)
    with db.engine.begin() as connection:
        for table, columns in _COLUNAS_INTERFACE_MYSQL.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, declaration in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{name}` {declaration}"))
