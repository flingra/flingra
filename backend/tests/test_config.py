from app.config import Settings


def test_paystack_settings_are_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("FLINGRA_PAYMENT_PROVIDER", "paystack")
    monkeypatch.setenv("FLINGRA_PAYSTACK_SECRET_KEY", "sk_test_example")

    settings = Settings(_env_file=None)

    assert settings.payment_provider == "paystack"
    assert settings.paystack_secret_key is not None
    assert settings.paystack_secret_key.get_secret_value() == "sk_test_example"
