ALTER TABLE accounts
    MODIFY email VARCHAR(254) NULL,
    MODIFY emergency_contact_name VARCHAR(100) NULL,
    MODIFY emergency_contact_phone_e164 VARCHAR(16) NULL,
    ADD COLUMN identifier VARCHAR(254) NULL,
    ADD COLUMN identifier_type ENUM('email', 'phone') NOT NULL DEFAULT 'email',
    ADD COLUMN referred_by_code VARCHAR(64) NULL,
    ADD COLUMN login_failed_attempts INT UNSIGNED NOT NULL DEFAULT 0,
    ADD COLUMN locked_until DATETIME(6) NULL;

UPDATE accounts
SET identifier = LOWER(email)
WHERE identifier IS NULL;

ALTER TABLE accounts
    MODIFY identifier VARCHAR(254) NOT NULL,
    ADD UNIQUE KEY uq_accounts_identifier (identifier);

ALTER TABLE accounts
    MODIFY gender ENUM('male', 'female', 'man', 'woman') NOT NULL;

UPDATE accounts SET gender = 'man' WHERE gender = 'male';
UPDATE accounts SET gender = 'woman' WHERE gender = 'female';

ALTER TABLE accounts
    MODIFY gender ENUM('man', 'woman') NOT NULL,
    MODIFY account_state VARCHAR(40) NOT NULL DEFAULT 'needs-verification';

ALTER TABLE email_verification_tokens
    DROP INDEX uq_email_verification_token_hash,
    ADD KEY ix_email_verification_token_hash (token_hash),
    ADD COLUMN attempt_count INT UNSIGNED NOT NULL DEFAULT 0;

CREATE TABLE profiles (
    account_id VARCHAR(64) NOT NULL PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL DEFAULT '',
    bio TEXT NOT NULL,
    photos JSON NOT NULL,
    videos JSON NULL,
    age_range VARCHAR(16) NOT NULL,
    area VARCHAR(160) NOT NULL DEFAULT '',
    distance_km DECIMAL(8, 2) NOT NULL DEFAULT 0,
    interests JSON NOT NULL,
    discoverable_by ENUM('men', 'women', 'everyone') NOT NULL DEFAULT 'everyone',
    wants_to_discover ENUM('men', 'women', 'everyone') NOT NULL DEFAULT 'everyone',
    identity ENUM('man', 'woman', 'private') NOT NULL,
    show_identity BOOLEAN NOT NULL DEFAULT FALSE,
    subscription_tier ENUM('free', 'vip') NOT NULL DEFAULT 'free',
    moderation_status ENUM('approved', 'pending', 'rejected') NOT NULL DEFAULT 'pending',
    two_factor_enabled BOOLEAN NULL,
    two_factor_method ENUM('email', 'authenticator') NULL,
    onboarding_complete BOOLEAN NOT NULL DEFAULT FALSE,
    selfie_verification ENUM('unverified', 'pending', 'verified', 'rejected') NOT NULL DEFAULT 'unverified',
    selfie_photo TEXT NULL,
    document_verification ENUM('unverified', 'pending', 'verified', 'rejected') NULL,
    document_type ENUM('NIN', 'BVN', 'voters-card') NULL,
    vip_expires_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_profiles_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
