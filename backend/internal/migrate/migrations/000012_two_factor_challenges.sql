CREATE TABLE two_factor_challenges (
    account_id VARCHAR(64) NOT NULL PRIMARY KEY,
    code_hash CHAR(64) NOT NULL,
    expires_at DATETIME NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_two_factor_challenges_account
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

ALTER TABLE profiles
    ADD COLUMN totp_secret VARCHAR(64) NULL;
