ALTER TABLE profiles
    ADD COLUMN demo_cohort_id VARCHAR(64) NULL,
    ADD KEY ix_profiles_demo_cohort_id (demo_cohort_id);
