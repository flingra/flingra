CREATE TABLE chat_interest_requests (
    id CHAR(32) NOT NULL PRIMARY KEY,
    sender_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    recipient_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    decided_at DATETIME(6) NULL,
    CONSTRAINT uq_chat_interest_requests_pair UNIQUE (sender_id, recipient_id),
    CONSTRAINT fk_chat_interest_requests_sender
        FOREIGN KEY (sender_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_chat_interest_requests_recipient
        FOREIGN KEY (recipient_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_chat_interest_requests_recipient_status_created (recipient_id, status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO chat_interest_requests (
    id, sender_id, recipient_id, status, created_at, updated_at, decided_at
)
SELECT
    MD5(CONCAT(t.id, '-legacy-accepted')),
    t.participant_a_id,
    t.participant_b_id,
    'accepted',
    t.created_at,
    t.created_at,
    t.created_at
FROM chat_threads t;
