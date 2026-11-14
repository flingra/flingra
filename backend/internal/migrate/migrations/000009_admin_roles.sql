ALTER TABLE admin_users
    ADD COLUMN role ENUM('super_admin', 'reviewer', 'safety_admin', 'auditor')
        NOT NULL DEFAULT 'reviewer' AFTER email;
