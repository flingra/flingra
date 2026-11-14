CREATE TABLE sessions (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    account_id VARCHAR(64) NOT NULL,
    session_token_hash BINARY(32) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    revoked_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_sessions_token_hash (session_token_hash),
    KEY ix_sessions_account_expiry (account_id, expires_at),
    CONSTRAINT fk_sessions_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
