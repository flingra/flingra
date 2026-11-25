ALTER TABLE profiles
    ADD COLUMN live_latitude DECIMAL(9,6) NULL;

ALTER TABLE profiles
    ADD COLUMN live_longitude DECIMAL(9,6) NULL;

ALTER TABLE profiles
    ADD COLUMN location_shared_at DATETIME(6) NULL;
