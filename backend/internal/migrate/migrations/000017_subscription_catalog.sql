CREATE TABLE subscription_plans (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    duration_days INT UNSIGNED NOT NULL,
    price_kobo BIGINT UNSIGNED NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY ix_subscription_plans_active_price (active, price_kobo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO subscription_plans (id, name, duration_days, price_kobo, active) VALUES
    ('vip-weekly', 'Weekly VIP', 7, 350000, TRUE),
    ('vip-monthly', 'Monthly VIP', 30, 1000000, TRUE),
    ('vip-yearly', 'Yearly VIP', 365, 8000000, TRUE);
