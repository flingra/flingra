from typing import Any

import pytest

from app.routes import auth

GOOGLE_NONCE = "test-google-nonce-1234567890"
GOOGLE_CREDENTIAL = "g" * 200


def install_google_claims(monkeypatch, **overrides: Any) -> None:
    claims = {
        "sub": "google-user-123",
        "email": "google@example.com",
        "email_verified": True,
        "name": "Google User",
        "nonce": GOOGLE_NONCE,
    }
    claims.update(overrides)
    monkeypatch.setattr(auth, "verify_oauth2_token", lambda *_args: claims)


def google_auth(client, **overrides: Any):
    payload: dict[str, Any] = {
        "credential": GOOGLE_CREDENTIAL,
        "nonce": GOOGLE_NONCE,
    }
    payload.update(overrides)
    return client.post("/auth/oauth/google", json=payload)


def test_google_config_returns_only_public_client_id(api_client) -> None:
    client, _ = api_client

    response = client.get("/auth/oauth/google/config")

    assert response.status_code == 200
    assert response.json() == {"clientId": "test-google-client-id"}


def test_google_signup_requires_account_details_before_creation(api_client, monkeypatch) -> None:
    client, _ = api_client
    install_google_claims(monkeypatch)

    response = google_auth(client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GOOGLE_SIGNUP_REQUIRED"
    assert client.get("/auth/session").json() is None


def test_google_signup_creates_verified_account_and_session(api_client, monkeypatch) -> None:
    client, _ = api_client
    install_google_claims(monkeypatch)

    response = google_auth(
        client,
        sex="woman",
        username="googleuser",
        dateOfBirth="1995-02-10",
        acceptedTerms=True,
        referralCode="FRIEND-123",
    )

    assert response.status_code == 200
    assert response.json()["stage"] == "needs-onboarding"
    assert response.json()["maskedContact"] == "g•••@example.com"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/auth/session").json()["stage"] == "needs-onboarding"
    profile = client.get("/profiles/me")
    assert profile.status_code == 200
    assert profile.json()["identity"] == "woman"
    assert profile.json()["documentVerification"] == "unverified"

    db_generator = client.app.dependency_overrides[auth.db_session]()
    db = next(db_generator)
    try:
        account = db.execute(
            auth.text(
                """
                SELECT id, email, email_verified, gender, date_of_birth, google_sub, referred_by_code
                FROM accounts WHERE identifier = :identifier
                """
            ),
            {"identifier": "google@example.com"},
        ).mappings().one()
        assert bool(account["email_verified"]) is True
        assert account["gender"] == "woman"
        assert str(account["date_of_birth"]) == "1995-02-10"
        assert account["google_sub"] == "google-user-123"
        assert account["referred_by_code"] == "FRIEND-123"
        display_name = db.execute(
            auth.text("SELECT display_name FROM profiles WHERE account_id = :account_id"),
            {"account_id": account["id"]},
        ).scalar_one()
        assert display_name == "Google User"
        assert db.execute(auth.text("SELECT COUNT(*) FROM email_verification_tokens")).scalar_one() == 0
    finally:
        db_generator.close()


def test_google_login_links_verified_email_account_and_verifies_contact(api_client, monkeypatch) -> None:
    client, _ = api_client
    monkeypatch.setattr(auth, "send_verification_code", lambda *_args: None)
    assert client.post(
        "/auth/signup",
        json={
            "sex": "woman",
            "username": "googleexisting",
            "identifier": "google@example.com",
            "password": "secure-password-123",
            "dateOfBirth": "1995-02-10",
            "acceptedTerms": True,
        },
    ).status_code == 201
    install_google_claims(monkeypatch)

    response = google_auth(client)

    assert response.status_code == 200
    assert response.json()["stage"] == "needs-onboarding"
    db_generator = client.app.dependency_overrides[auth.db_session]()
    db = next(db_generator)
    try:
        account = db.execute(
            auth.text(
                "SELECT email_verified, google_sub FROM accounts WHERE identifier = :identifier"
            ),
            {"identifier": "google@example.com"},
        ).mappings().one()
        assert bool(account["email_verified"]) is True
        assert account["google_sub"] == "google-user-123"
        assert db.execute(auth.text("SELECT COUNT(*) FROM email_verification_tokens")).scalar_one() == 0
    finally:
        db_generator.close()


@pytest.mark.parametrize(
    ("claims", "overrides", "error_code"),
    [
        ({"email_verified": False}, {}, "INVALID_GOOGLE_CREDENTIAL"),
        ({}, {"nonce": "another-google-nonce-1234567"}, "INVALID_GOOGLE_CREDENTIAL"),
        (
            {},
            {
                "acceptedTerms": False,
                "sex": "woman",
                "username": "termsuser",
                "dateOfBirth": "1995-02-10",
            },
            "TERMS_REQUIRED",
        ),
        (
            {},
            {
                "acceptedTerms": True,
                "sex": "woman",
                "username": "youngwoman",
                "dateOfBirth": "2008-02-10",
            },
            "INELIGIBLE_AGE",
        ),
        (
            {},
            {
                "acceptedTerms": True,
                "sex": "man",
                "username": "youngman",
                "dateOfBirth": "2008-02-10",
            },
            "INELIGIBLE_AGE",
        ),
    ],
)
def test_google_signup_rejects_invalid_claims_or_profile_data(
    api_client,
    monkeypatch,
    claims: dict[str, Any],
    overrides: dict[str, Any],
    error_code: str,
) -> None:
    client, _ = api_client
    install_google_claims(monkeypatch, **claims)

    response = google_auth(client, **overrides)

    assert response.status_code == (401 if error_code == "INVALID_GOOGLE_CREDENTIAL" else 400)
    assert response.json()["error"]["code"] == error_code
    assert client.get("/auth/session").json() is None


def test_google_signin_rejects_unverified_id_token(api_client, monkeypatch) -> None:
    client, _ = api_client
    monkeypatch.setattr(
        auth,
        "verify_oauth2_token",
        lambda *_args: (_ for _ in ()).throw(ValueError("invalid signature")),
    )

    response = google_auth(client)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_GOOGLE_CREDENTIAL"


def test_google_signin_rejects_existing_account_under_21(api_client, monkeypatch) -> None:
    client, _ = api_client
    monkeypatch.setattr(auth, "send_verification_code", lambda *_args: None)
    assert client.post(
        "/auth/signup",
        json={
            "sex": "man",
            "username": "googleexisting",
            "identifier": "google@example.com",
            "password": "secure-password-123",
            "dateOfBirth": "1995-02-10",
            "acceptedTerms": True,
        },
    ).status_code == 201
    db_generator = client.app.dependency_overrides[auth.db_session]()
    db = next(db_generator)
    try:
        db.execute(
            auth.text(
                "UPDATE accounts SET date_of_birth = :date_of_birth WHERE identifier = :identifier"
            ),
            {"date_of_birth": "2008-02-10", "identifier": "google@example.com"},
        )
        db.commit()
    finally:
        db_generator.close()
    install_google_claims(monkeypatch)

    response = google_auth(client)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INELIGIBLE_AGE"
