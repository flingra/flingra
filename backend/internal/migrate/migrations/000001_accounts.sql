CREATE TABLE accounts (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender ENUM('male', 'female') NOT NULL,
    emergency_contact_name VARCHAR(100) NOT NULL,
    emergency_contact_phone_e164 VARCHAR(16) NOT NULL,
    terms_version VARCHAR(64) NOT NULL,
    privacy_version VARCHAR(64) NOT NULL,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    account_state VARCHAR(40) NOT NULL DEFAULT 'email_verification_required',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_accounts_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
