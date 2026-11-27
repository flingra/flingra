CREATE TABLE wallet_accounts (
    account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL PRIMARY KEY,
    balance_kobo BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_wallet_accounts_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE wallet_transactions (
    id CHAR(32) NOT NULL PRIMARY KEY,
    account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    transaction_type VARCHAR(40) NOT NULL,
    amount_kobo BIGINT NOT NULL,
    description VARCHAR(500) NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_wallet_transactions_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_wallet_transactions_account_created (account_id, created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE gift_catalog (
    id VARCHAR(40) NOT NULL PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    emoji VARCHAR(16) NOT NULL,
    price_kobo BIGINT UNSIGNED NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO gift_catalog (id, name, emoji, price_kobo, active) VALUES
    ('rose', 'Rose', '🌹', 50000, TRUE),
    ('fire', 'Fire', '🔥', 100000, TRUE),
    ('diamond', 'Diamond', '💎', 500000, TRUE),
    ('crown', 'Crown', '👑', 1000000, TRUE);

CREATE TABLE gift_inventory (
    account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    gift_type_id VARCHAR(40) NOT NULL,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, gift_type_id),
    CONSTRAINT fk_gift_inventory_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_gift_inventory_type
        FOREIGN KEY (gift_type_id) REFERENCES gift_catalog (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE received_gifts (
    id CHAR(32) NOT NULL PRIMARY KEY,
    recipient_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    sender_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    gift_type_id VARCHAR(40) NOT NULL,
    value_kobo BIGINT UNSIGNED NOT NULL,
    redeemed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_received_gifts_recipient
        FOREIGN KEY (recipient_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_received_gifts_sender
        FOREIGN KEY (sender_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_received_gifts_type
        FOREIGN KEY (gift_type_id) REFERENCES gift_catalog (id) ON DELETE RESTRICT,
    KEY ix_received_gifts_recipient_created (recipient_id, created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
