CREATE TABLE referral_codes (
    account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL PRIMARY KEY,
    code VARCHAR(16) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT uq_referral_codes_code UNIQUE (code),
    CONSTRAINT fk_referral_codes_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE referral_rewards (
    referred_account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL PRIMARY KEY,
    referrer_account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci,
    referral_code VARCHAR(16) NOT NULL,
    bonus_kobo BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_referral_rewards_referred
        FOREIGN KEY (referred_account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_referral_rewards_referrer
        FOREIGN KEY (referrer_account_id) REFERENCES accounts (id) ON DELETE SET NULL,
    KEY ix_referral_rewards_referrer_created (referrer_account_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_accounts_referred_by_code ON accounts (referred_by_code);
