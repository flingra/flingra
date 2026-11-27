CREATE TABLE wallet_payment_intents (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    reference VARCHAR(100) NOT NULL,
    amount_kobo BIGINT UNSIGNED NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'NGN',
    status VARCHAR(24) NOT NULL DEFAULT 'initializing',
    authorization_url VARCHAR(2048),
    settled_at DATETIME(6),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_wallet_payment_intents_reference (reference),
    KEY ix_wallet_payment_intents_account_created (account_id, created_at),
    CONSTRAINT fk_wallet_payment_intents_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
