INSERT INTO call_credit_transactions (
    id, account_id, transaction_type, amount, description, created_at
)
SELECT REPLACE(UUID(), '-', ''), account_id, 'balance-conversion',
       FLOOR(balance / 6) - balance,
       'Converted legacy 10-second credits to per-minute credits',
       CURRENT_TIMESTAMP(6)
FROM call_credit_accounts
WHERE balance > FLOOR(balance / 6);

UPDATE call_credit_accounts
SET balance = FLOOR(balance / 6);

ALTER TABLE video_unlocks
    ADD COLUMN expires_at DATETIME(6) NULL;

UPDATE video_unlocks
SET expires_at = DATE_ADD(created_at, INTERVAL 30 DAY);

ALTER TABLE video_unlocks
    MODIFY expires_at DATETIME(6) NOT NULL;
