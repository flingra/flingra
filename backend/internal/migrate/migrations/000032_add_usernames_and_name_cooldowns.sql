ALTER TABLE profiles
    ADD COLUMN username VARCHAR(40) NULL;

ALTER TABLE profiles
    ADD COLUMN username_changed_at DATETIME(6) NULL;

ALTER TABLE profiles
    ADD COLUMN display_name_changed_at DATETIME(6) NULL;

UPDATE profiles
SET username = CONCAT('u', SUBSTR(SHA2(account_id, 256), 1, 29))
WHERE username IS NULL;

CREATE UNIQUE INDEX uq_profiles_username ON profiles (username);
