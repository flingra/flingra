CREATE TABLE meetup_payments (
    id CHAR(32) NOT NULL PRIMARY KEY,
    thread_id CHAR(32) NOT NULL,
    payer_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    recipient_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    payer_name VARCHAR(100) NOT NULL,
    recipient_name VARCHAR(100) NOT NULL,
    amount_kobo BIGINT UNSIGNED NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'proposed',
    dispute_reason VARCHAR(1000),
    dispute_opened_by VARCHAR(64) COLLATE utf8mb4_0900_ai_ci,
    resolution_reason VARCHAR(1000),
    resolved_by_admin_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    resolved_at DATETIME(6),
    CONSTRAINT fk_meetup_payment_thread
        FOREIGN KEY (thread_id) REFERENCES chat_threads (id) ON DELETE CASCADE,
    CONSTRAINT fk_meetup_payment_payer
        FOREIGN KEY (payer_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_meetup_payment_recipient
        FOREIGN KEY (recipient_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_meetup_payment_disputer
        FOREIGN KEY (dispute_opened_by) REFERENCES accounts (id) ON DELETE SET NULL,
    CONSTRAINT fk_meetup_payment_resolver
        FOREIGN KEY (resolved_by_admin_id) REFERENCES admin_users (id) ON DELETE SET NULL,
    KEY ix_meetup_payments_thread_created (thread_id, created_at),
    KEY ix_meetup_payments_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE chat_messages
    ADD COLUMN payment_id CHAR(32) NULL,
    ADD UNIQUE KEY uq_chat_messages_payment (payment_id),
    ADD CONSTRAINT fk_chat_messages_payment
        FOREIGN KEY (payment_id) REFERENCES meetup_payments (id) ON DELETE SET NULL;
