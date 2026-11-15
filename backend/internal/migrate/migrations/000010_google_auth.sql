ALTER TABLE accounts
    ADD COLUMN google_sub VARCHAR(255) NULL,
    ADD UNIQUE KEY uq_accounts_google_sub (google_sub);
