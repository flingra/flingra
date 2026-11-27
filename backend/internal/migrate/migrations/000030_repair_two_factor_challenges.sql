CREATE TABLE IF NOT EXISTS two_factor_challenges (
    account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL PRIMARY KEY,
    code_hash CHAR(64) NOT NULL,
    expires_at DATETIME NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_two_factor_challenges_account
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DELETE FROM two_factor_challenges;

ALTER TABLE two_factor_challenges
    MODIFY code_hash CHAR(64) NOT NULL;
