CREATE TABLE live_streams (
    id CHAR(32) NOT NULL PRIMARY KEY,
    host_account_id VARCHAR(64) NOT NULL,
    room_name VARCHAR(80) NOT NULL,
    title VARCHAR(80) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'live',
    started_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    ended_at DATETIME(6),
    CONSTRAINT uq_live_streams_room UNIQUE (room_name),
    CONSTRAINT fk_live_streams_host
        FOREIGN KEY (host_account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    KEY ix_live_streams_status_started (status, started_at),
    KEY ix_live_streams_host_status (host_account_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
