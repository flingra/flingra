CREATE TABLE admin_users (
    id CHAR(32) NOT NULL PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    failed_login_attempts INT UNSIGNED NOT NULL DEFAULT 0,
    locked_until DATETIME(6) NULL,
    disabled_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY ix_admin_users_locked_until (locked_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE admin_sessions (
    id CHAR(32) NOT NULL PRIMARY KEY,
    admin_id CHAR(32) NOT NULL,
    session_token_hash BINARY(32) NOT NULL UNIQUE,
    expires_at DATETIME(6) NOT NULL,
    revoked_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_admin_sessions_admin
        FOREIGN KEY (admin_id) REFERENCES admin_users (id) ON DELETE CASCADE,
    KEY ix_admin_sessions_admin_expiry (admin_id, expires_at),
    KEY ix_admin_sessions_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE platform_audit_events (
    id CHAR(32) NOT NULL PRIMARY KEY,
    event_type VARCHAR(80) NOT NULL,
    actor_type ENUM('user', 'admin', 'anonymous', 'system') NOT NULL,
    actor_id VARCHAR(64) NULL,
    subject_account_id VARCHAR(64) NULL,
    outcome ENUM('success', 'failure', 'denied') NOT NULL,
    request_id CHAR(32) NOT NULL,
    metadata JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY ix_platform_audit_subject_time (subject_account_id, created_at, id),
    KEY ix_platform_audit_type_time (event_type, created_at),
    KEY ix_platform_audit_actor_time (actor_type, actor_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TRIGGER prevent_platform_audit_update
BEFORE UPDATE ON platform_audit_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit events are append-only';

CREATE TRIGGER prevent_platform_audit_delete
BEFORE DELETE ON platform_audit_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit events are append-only';
