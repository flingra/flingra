import io

from PIL import Image
from sqlalchemy import text

from app.routes import auth


def signup(client, **overrides):
    payload = {
        "sex": "woman",
        "identifier": "test@example.com",
        "password": "secure-password-123",
        "dateOfBirth": "1995-02-10",
        "acceptedTerms": True,
    }
    payload.update(overrides)
    return client.post("/auth/signup", json=payload)


def upload_profile_photo(client) -> str:
    image = Image.new("RGB", (4, 4), color=(200, 30, 50))
    content = io.BytesIO()
    image.save(content, format="PNG")
    response = client.post(
        "/media/photos",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        files={"file": ("profile.png", content.getvalue(), "image/png")},
    )
    assert response.status_code == 201
    return response.json()["url"]


def test_signup_verify_login_and_profile_round_trip(api_client, monkeypatch) -> None:
    client, delivered_codes = api_client

    def capture_code(_settings, _recipient, code):
        delivered_codes.append(code)

    monkeypatch.setattr(auth, "send_verification_code", capture_code)

    response = signup(client)

    assert response.status_code == 201
    assert response.json() == {"stage": "needs-verification"}
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.headers["X-CSRF-Token"] == client.cookies["flingra_csrf"]
    session_response = client.get("/auth/session")
    assert session_response.json()["stage"] == "needs-verification"
    assert session_response.headers["X-CSRF-Token"] == client.cookies["flingra_csrf"]
    draft = client.get("/profiles/me")
    assert draft.status_code == 200
    assert draft.json()["identity"] == "woman"
    assert draft.json()["documentVerification"] == "unverified"

    verified = client.post(
        "/auth/verify-contact",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"code": delivered_codes[0]},
    )
    assert verified.status_code == 200
    assert verified.json() == {"stage": "needs-onboarding"}
    assert client.get("/auth/session").json()["stage"] == "needs-onboarding"

    signed_out = client.post(
        "/auth/logout",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
    )
    assert signed_out.status_code == 204
    assert client.get("/auth/session").json() is None
    signed_in = client.post(
        "/auth/login",
        json={"identifier": "TEST@example.com", "password": "secure-password-123"},
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["stage"] == "needs-onboarding"

    csrf_token = client.cookies["flingra_csrf"]
    photo_url = upload_profile_photo(client)
    updated = client.patch(
        "/profiles/me",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "displayName": "Tola",
            "bio": "Hello",
            "photos": [photo_url],
            "area": "Yaba, Lagos",
            "interests": ["Music"],
            "videos": [{"url": "https://cdn.example.test/video.mp4", "locked": True, "priceNaira": 500}],
            "identity": "woman",
            "distanceKm": 0,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["displayName"] == "Tola"
    assert updated.json()["photos"] == [photo_url]
    assert updated.json()["videos"][0]["priceNaira"] == 500
    assert client.get("/profiles/me").json()["area"] == "Yaba, Lagos"


def test_signup_rejects_terms_email_and_minimum_age(api_client, monkeypatch) -> None:
    client, _ = api_client
    monkeypatch.setattr(auth, "send_verification_code", lambda *_: None)

    no_terms = signup(client, acceptedTerms=False)
    assert no_terms.status_code == 400
    assert no_terms.json()["error"]["code"] == "TERMS_REQUIRED"

    no_email = signup(client, identifier="not-an-email")
    assert no_email.status_code == 400
    assert no_email.json()["error"]["code"] == "EMAIL_REQUIRED"

    underage = signup(client, dateOfBirth="2008-01-01")
    assert underage.status_code == 400
    assert underage.json()["error"]["code"] == "INELIGIBLE_AGE"

    underage_man = signup(
        client,
        sex="man",
        identifier="young-man@example.com",
        dateOfBirth="2008-01-01",
    )
    assert underage_man.status_code == 400
    assert underage_man.json()["error"]["code"] == "INELIGIBLE_AGE"


def test_signup_rejects_duplicate_identifier(api_client, monkeypatch) -> None:
    client, _ = api_client
    monkeypatch.setattr(auth, "send_verification_code", lambda *_: None)

    first = signup(client)
    assert first.status_code == 201
    duplicate = signup(client)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "ACCOUNT_EXISTS"


def test_referral_signup_does_not_credit_bonus_until_policy_is_decided(
    api_client, monkeypatch
) -> None:
    client, delivered_codes = api_client
    monkeypatch.setattr(
        auth,
        "send_verification_code",
        lambda _settings, _recipient, code: delivered_codes.append(code),
    )

    referrer = signup(client, identifier="referrer@example.test")
    assert referrer.status_code == 201
    assert client.post(
        "/auth/verify-contact",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"code": delivered_codes[0]},
    ).status_code == 200
    referral_code = client.get("/referrals/code").json()["code"]

    referred = signup(
        client,
        identifier="referred@example.test",
        referralCode=referral_code.lower(),
    )
    assert referred.status_code == 201
    assert client.post(
        "/auth/verify-contact",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"code": delivered_codes[1]},
    ).status_code == 200

    account_id = client.get("/auth/session").json()["accountId"]
    db_generator = client.app.dependency_overrides[auth.db_session]()
    db = next(db_generator)
    try:
        assert db.execute(
            text(
                "SELECT COALESCE((SELECT balance_kobo FROM wallet_accounts "
                "WHERE account_id = :account_id), 0)"
            ),
            {"account_id": account_id},
        ).scalar_one() == 0
        assert db.execute(
            text("SELECT COUNT(*) FROM referral_rewards WHERE referred_account_id = :account_id"),
            {"account_id": account_id},
        ).scalar_one() == 0
        assert db.execute(
            text(
                "SELECT COUNT(*) FROM wallet_transactions "
                "WHERE account_id = :account_id AND transaction_type = 'referral-bonus'"
            ),
            {"account_id": account_id},
        ).scalar_one() == 0
    finally:
        db_generator.close()

    assert client.get("/referrals").json() == []


def test_profile_patch_requires_csrf(api_client, monkeypatch) -> None:
    client, _ = api_client
    monkeypatch.setattr(auth, "send_verification_code", lambda *_: None)
    assert signup(client).status_code == 201

    response = client.patch("/profiles/me", json={"displayName": "Tola"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"


def test_csrf_requires_an_allowlisted_origin_when_configured(api_client, monkeypatch) -> None:
    client, _ = api_client
    monkeypatch.setattr(auth, "send_verification_code", lambda *_: None)
    assert signup(client).status_code == 201
    client.app.state.settings.allowed_origins = ["https://app.example.test"]
    csrf_token = client.cookies["flingra_csrf"]

    missing_origin = client.patch(
        "/profiles/me",
        headers={"X-CSRF-Token": csrf_token},
        json={"displayName": "Tola"},
    )
    denied_origin = client.patch(
        "/profiles/me",
        headers={"X-CSRF-Token": csrf_token, "Origin": "https://evil.example"},
        json={"displayName": "Tola"},
    )
    allowed_origin = client.patch(
        "/profiles/me",
        headers={"X-CSRF-Token": csrf_token, "Origin": "https://app.example.test"},
        json={"displayName": "Tola"},
    )

    assert missing_origin.status_code == 403
    assert denied_origin.status_code == 403
    assert allowed_origin.status_code == 200


def test_login_locks_account_after_five_incorrect_passwords(api_client, monkeypatch) -> None:
    client, _ = api_client
    monkeypatch.setattr(auth, "send_verification_code", lambda *_: None)
    assert signup(client).status_code == 201

    for _ in range(4):
        response = client.post(
            "/auth/login",
            json={"identifier": "test@example.com", "password": "incorrect-password"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    locked = client.post(
        "/auth/login",
        json={"identifier": "test@example.com", "password": "incorrect-password"},
    )
    assert locked.status_code == 423
    assert locked.json()["error"]["code"] == "ACCOUNT_LOCKED"

    correct_password = client.post(
        "/auth/login",
        json={"identifier": "test@example.com", "password": "secure-password-123"},
    )
    assert correct_password.status_code == 423


def test_login_rejects_existing_account_under_21(api_client, monkeypatch) -> None:
    client, _ = api_client
    monkeypatch.setattr(auth, "send_verification_code", lambda *_: None)
    assert signup(client, sex="man").status_code == 201

    db_generator = client.app.dependency_overrides[auth.db_session]()
    db = next(db_generator)
    try:
        db.execute(
            auth.text(
                "UPDATE accounts SET date_of_birth = :date_of_birth WHERE identifier = :identifier"
            ),
            {"date_of_birth": "2008-01-01", "identifier": "test@example.com"},
        )
        db.commit()
    finally:
        db_generator.close()

    existing_session = client.get("/profiles/me")
    assert existing_session.status_code == 403
    assert existing_session.json()["error"]["code"] == "INELIGIBLE_AGE"

    response = client.post(
        "/auth/login",
        json={"identifier": "test@example.com", "password": "secure-password-123"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INELIGIBLE_AGE"


def test_identity_verification_dependency_blocks_unapproved_profiles(api_client, monkeypatch) -> None:
    client, _ = api_client
    monkeypatch.setattr(auth, "send_verification_code", lambda *_: None)
    assert signup(client, sex="man").status_code == 201
    account_id = client.get("/auth/session").json()["accountId"]

    @client.app.get("/test/identity-verified")
    def protected_identity_route(account: auth.IdentityVerifiedAccount) -> dict[str, str]:
        return {"accountId": account.account_id}

    db_generator = client.app.dependency_overrides[auth.db_session]()
    db = next(db_generator)
    try:
        for status in ("unverified", "pending", "rejected"):
            db.execute(
                auth.text(
                    """
                    UPDATE profiles
                    SET document_verification = :status
                    WHERE account_id = :account_id
                    """
                ),
                {"status": status, "account_id": account_id},
            )
            db.commit()
            blocked = client.get("/test/identity-verified")
            assert blocked.status_code == 403
            assert blocked.json()["error"]["code"] == "IDENTITY_VERIFICATION_REQUIRED"
        db.execute(
            auth.text(
                "UPDATE profiles SET document_verification = 'verified' WHERE account_id = :account_id"
            ),
            {"account_id": account_id},
        )
        db.commit()
    finally:
        db_generator.close()

    verified = client.get("/test/identity-verified")
    assert verified.status_code == 200
    assert verified.json() == {"accountId": account_id}


def test_onboarding_completes_without_facial_verification_and_stays_pending_review(api_client, monkeypatch) -> None:
    client, delivered_codes = api_client
    monkeypatch.setattr(auth, "send_verification_code", lambda _settings, _recipient, code: delivered_codes.append(code))
    assert signup(client).status_code == 201
    assert client.post(
        "/auth/verify-contact",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"code": delivered_codes[0]},
    ).json() == {"stage": "needs-onboarding"}

    csrf_token = client.cookies["flingra_csrf"]
    photo_url = upload_profile_photo(client)
    patched = client.patch(
        "/profiles/me",
        headers={"X-CSRF-Token": csrf_token},
        json={"displayName": "Tola", "photos": [photo_url]},
    )
    assert patched.status_code == 200

    response = client.post(
        "/auth/onboarding/complete",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert response.json()["stage"] == "active"
    completed_profile = client.get("/profiles/me").json()
    assert completed_profile["onboardingComplete"] is True
    assert completed_profile["moderationStatus"] == "pending"
    assert "selfieVerification" not in completed_profile
    assert "selfiePhoto" not in completed_profile
