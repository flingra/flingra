ALTER TABLE privacy_requests
    ADD COLUMN result_json LONGTEXT NULL,
    ADD COLUMN updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    ADD KEY ix_privacy_requests_status_created (status, created_at);
