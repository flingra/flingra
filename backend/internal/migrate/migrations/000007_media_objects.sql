CREATE TABLE media_objects (
    id CHAR(32) NOT NULL PRIMARY KEY,
    account_id VARCHAR(64) NOT NULL,
    purpose ENUM('profile-photo', 'identity-document') NOT NULL,
    object_key VARCHAR(512) NOT NULL UNIQUE,
    content_type VARCHAR(100) NOT NULL,
    size_bytes INT UNSIGNED NOT NULL,
    sha256 CHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_media_objects_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_media_objects_account_purpose (account_id, purpose),
    KEY ix_media_objects_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
