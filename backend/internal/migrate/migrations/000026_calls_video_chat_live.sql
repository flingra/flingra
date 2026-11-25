ALTER TABLE media_objects
    MODIFY purpose ENUM(
        'profile-photo',
        'identity-document',
        'status-media',
        'profile-video',
        'post-video',
        'chat-attachment'
    ) NOT NULL;

CREATE TABLE call_credit_pricing (
    id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    price_naira BIGINT UNSIGNED NOT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO call_credit_pricing (id, price_naira) VALUES (1, 50);

CREATE TABLE call_credit_accounts (
    account_id VARCHAR(64) NOT NULL PRIMARY KEY,
    balance BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_call_credit_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE call_sessions (
    id CHAR(32) NOT NULL PRIMARY KEY,
    caller_id VARCHAR(64) NOT NULL,
    callee_id VARCHAR(64) NOT NULL,
    payer_id VARCHAR(64),
    room_name VARCHAR(80) NOT NULL,
    call_type VARCHAR(12) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ringing',
    started_at DATETIME(6),
    last_billed_at DATETIME(6),
    ended_at DATETIME(6),
    caller_connected_at DATETIME(6),
    callee_connected_at DATETIME(6),
    room_closed_at DATETIME(6),
    last_activity_at DATETIME(6),
    billed_ticks INT UNSIGNED NOT NULL DEFAULT 0,
    idempotency_key VARCHAR(128),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT uq_call_sessions_room UNIQUE (room_name),
    CONSTRAINT uq_call_sessions_idempotency UNIQUE (caller_id, idempotency_key),
    CONSTRAINT fk_call_sessions_caller
        FOREIGN KEY (caller_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_call_sessions_callee
        FOREIGN KEY (callee_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_call_sessions_payer
        FOREIGN KEY (payer_id) REFERENCES accounts (id) ON DELETE SET NULL,
    KEY ix_call_sessions_caller_status (caller_id, status, created_at),
    KEY ix_call_sessions_callee_status (callee_id, status, created_at),
    KEY ix_call_sessions_active_billing (status, last_billed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE call_credit_transactions (
    id CHAR(32) NOT NULL PRIMARY KEY,
    account_id VARCHAR(64) NOT NULL,
    call_id CHAR(32),
    tick_number INT UNSIGNED,
    transaction_type VARCHAR(24) NOT NULL,
    amount BIGINT NOT NULL,
    description VARCHAR(255) NOT NULL,
    idempotency_key VARCHAR(128),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_call_credit_transactions_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_call_credit_transactions_call
        FOREIGN KEY (call_id) REFERENCES call_sessions (id) ON DELETE SET NULL,
    CONSTRAINT uq_call_credit_transaction_tick UNIQUE (call_id, tick_number),
    CONSTRAINT uq_call_credit_transaction_idempotency UNIQUE (account_id, idempotency_key),
    KEY ix_call_credit_transactions_account_created (account_id, created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE video_unlocks (
    id CHAR(32) NOT NULL PRIMARY KEY,
    viewer_id VARCHAR(64) NOT NULL,
    creator_id VARCHAR(64) NOT NULL,
    media_id CHAR(32) NOT NULL,
    price_kobo BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_video_unlock_viewer
        FOREIGN KEY (viewer_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_video_unlock_creator
        FOREIGN KEY (creator_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_video_unlock_media
        FOREIGN KEY (media_id) REFERENCES media_objects (id) ON DELETE CASCADE,
    CONSTRAINT uq_video_unlock_viewer_media UNIQUE (viewer_id, media_id),
    KEY ix_video_unlock_creator_created (creator_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE live_stream_join_requests (
    id CHAR(32) NOT NULL PRIMARY KEY,
    stream_id CHAR(32) NOT NULL,
    requester_id VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    responded_at DATETIME(6),
    CONSTRAINT fk_live_join_stream
        FOREIGN KEY (stream_id) REFERENCES live_streams (id) ON DELETE CASCADE,
    CONSTRAINT fk_live_join_requester
        FOREIGN KEY (requester_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_live_join_stream_status (stream_id, status, created_at),
    KEY ix_live_join_requester_status (requester_id, status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE live_streams
    ADD COLUMN room_closed_at DATETIME(6);

CREATE TABLE live_stream_participants (
    stream_id CHAR(32) NOT NULL,
    account_id VARCHAR(64) NOT NULL,
    role VARCHAR(12) NOT NULL,
    joined_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    last_seen_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (stream_id, account_id),
    CONSTRAINT fk_live_participant_stream
        FOREIGN KEY (stream_id) REFERENCES live_streams (id) ON DELETE CASCADE,
    CONSTRAINT fk_live_participant_account
        FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_live_participant_presence (stream_id, role, last_seen_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE live_stream_messages (
    id CHAR(32) NOT NULL PRIMARY KEY,
    stream_id CHAR(32) NOT NULL,
    author_id VARCHAR(64) NOT NULL,
    kind VARCHAR(12) NOT NULL DEFAULT 'message',
    message_text VARCHAR(500) NOT NULL,
    gift_id VARCHAR(40),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_live_message_stream
        FOREIGN KEY (stream_id) REFERENCES live_streams (id) ON DELETE CASCADE,
    CONSTRAINT fk_live_message_author
        FOREIGN KEY (author_id) REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT fk_live_message_gift
        FOREIGN KEY (gift_id) REFERENCES gift_catalog (id) ON DELETE SET NULL,
    KEY ix_live_message_stream_created (stream_id, created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE realtime_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    recipient_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(48) NOT NULL,
    payload_json LONGTEXT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_realtime_event_recipient
        FOREIGN KEY (recipient_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_realtime_events_recipient_id (recipient_id, id),
    KEY ix_realtime_events_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
