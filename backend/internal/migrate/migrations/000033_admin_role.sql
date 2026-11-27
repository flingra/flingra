ALTER TABLE admin_users
    MODIFY COLUMN role ENUM('super_admin', 'admin', 'reviewer', 'safety_admin', 'auditor')
        NOT NULL DEFAULT 'reviewer';
