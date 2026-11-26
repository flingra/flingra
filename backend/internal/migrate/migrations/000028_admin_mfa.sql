ALTER TABLE admin_users
    ADD COLUMN totp_secret VARCHAR(64) NULL,
    ADD COLUMN totp_pending_secret VARCHAR(64) NULL,
    ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT FALSE;
