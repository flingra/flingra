UPDATE accounts
SET account_state = 'active'
WHERE account_state = 'needs-onboarding'
  AND email_verified = TRUE
  AND EXISTS (
      SELECT 1
      FROM profiles
      WHERE profiles.account_id = accounts.id
        AND profiles.onboarding_complete = TRUE
  );
