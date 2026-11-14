CREATE TABLE password_reset_tokens (
    account_id VARCHAR(64) NOT NULL PRIMARY KEY,
    token_hash BINARY(32) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_password_reset_token_hash (token_hash),
    CONSTRAINT fk_password_reset_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
