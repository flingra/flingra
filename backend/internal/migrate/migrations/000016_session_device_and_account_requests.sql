ALTER TABLE sessions
    ADD COLUMN device_label VARCHAR(255) NOT NULL DEFAULT 'Unknown device';

ALTER TABLE sessions
    ADD COLUMN last_active_at DATETIME(6) NULL;

UPDATE sessions
SET last_active_at = created_at
WHERE last_active_at IS NULL;
