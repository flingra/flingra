CREATE TABLE safety_blocks (
    blocker_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    blocked_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (blocker_id, blocked_id),
    CONSTRAINT fk_safety_blocks_blocker
        FOREIGN KEY (blocker_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_safety_blocks_blocked
        FOREIGN KEY (blocked_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_safety_blocks_blocked (blocked_id, blocker_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE safety_reports (
    id CHAR(32) NOT NULL PRIMARY KEY,
    reporter_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    target_account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    reason VARCHAR(40) NOT NULL,
    description VARCHAR(2000) NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'open',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    resolved_at DATETIME(6) NULL,
    CONSTRAINT fk_safety_reports_reporter
        FOREIGN KEY (reporter_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_safety_reports_target
        FOREIGN KEY (target_account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_safety_reports_status_created (status, created_at, id),
    KEY ix_safety_reports_target_created (target_account_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE moderation_review_requests (
    id CHAR(32) NOT NULL PRIMARY KEY,
    requester_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    target_account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    source_type VARCHAR(24) NOT NULL,
    source_id CHAR(32) NOT NULL,
    reason VARCHAR(2000) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'open',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_moderation_review_requester
        FOREIGN KEY (requester_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_moderation_review_target
        FOREIGN KEY (target_account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_moderation_review_status_created (status, created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE emergency_contacts (
    id CHAR(32) NOT NULL PRIMARY KEY,
    account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(32) NOT NULL,
    relationship VARCHAR(80) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_emergency_contacts_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_emergency_contacts_account (account_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE safety_check_ins (
    id CHAR(32) NOT NULL PRIMARY KEY,
    account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    message VARCHAR(1000) NOT NULL,
    location_link VARCHAR(2048) NULL,
    status VARCHAR(24) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_safety_check_ins_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_safety_check_ins_account_created (account_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE chat_threads (
    id CHAR(32) NOT NULL PRIMARY KEY,
    participant_a_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    participant_b_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    last_message_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT uq_chat_threads_pair UNIQUE (participant_a_id, participant_b_id),
    CONSTRAINT fk_chat_threads_a FOREIGN KEY (participant_a_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_chat_threads_b FOREIGN KEY (participant_b_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_chat_threads_a_last (participant_a_id, last_message_at),
    KEY ix_chat_threads_b_last (participant_b_id, last_message_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE chat_messages (
    id CHAR(32) NOT NULL PRIMARY KEY,
    thread_id CHAR(32) NOT NULL,
    author_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    message_text VARCHAR(5000) NOT NULL DEFAULT '',
    attachment_json JSON NULL,
    attachment_media_id CHAR(32) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_chat_messages_thread FOREIGN KEY (thread_id) REFERENCES chat_threads (id) ON DELETE CASCADE,
    CONSTRAINT fk_chat_messages_author FOREIGN KEY (author_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_chat_messages_thread_created (thread_id, created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE member_posts (
    id CHAR(32) NOT NULL PRIMARY KEY,
    author_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    photos JSON NOT NULL,
    video_url VARCHAR(2048) NULL,
    caption VARCHAR(2000) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_member_posts_author FOREIGN KEY (author_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_member_posts_author_created (author_id, created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE member_statuses (
    id CHAR(32) NOT NULL PRIMARY KEY,
    author_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    media_url VARCHAR(2048) NOT NULL,
    media_kind VARCHAR(12) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_member_statuses_author FOREIGN KEY (author_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_member_statuses_expiry_created (expires_at, created_at, id),
    KEY ix_member_statuses_author_expiry (author_id, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE privacy_requests (
    id CHAR(32) NOT NULL PRIMARY KEY,
    account_id VARCHAR(64) COLLATE utf8mb4_0900_ai_ci NOT NULL,
    request_type VARCHAR(24) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'queued',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_privacy_requests_account FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_privacy_requests_account_type_created (account_id, request_type, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
