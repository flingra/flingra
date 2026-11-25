CREATE TABLE payout_bank_accounts (
    account_id VARCHAR(64) NOT NULL PRIMARY KEY,
    recipient_code VARCHAR(64) NOT NULL,
    bank_code VARCHAR(16) NOT NULL,
    bank_name VARCHAR(100) NOT NULL,
    account_name VARCHAR(150) NOT NULL,
    account_last4 CHAR(4) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_payout_bank_recipient (recipient_code),
    CONSTRAINT fk_payout_bank_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE payout_requests (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    account_id VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    reference VARCHAR(100) NOT NULL,
    recipient_code VARCHAR(64) NOT NULL,
    amount_kobo BIGINT UNSIGNED NOT NULL,
    wallet_transaction_id VARCHAR(64) NOT NULL,
    transfer_code VARCHAR(64),
    status VARCHAR(24) NOT NULL DEFAULT 'initiating',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_payout_idempotency (account_id, idempotency_key),
    UNIQUE KEY uq_payout_reference (reference),
    KEY ix_payout_account_created (account_id, created_at),
    CONSTRAINT fk_payout_request_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
