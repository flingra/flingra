import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.dependencies import db_session
from app.routes import auth


def _session(client):
    generator = client.app.dependency_overrides[db_session]()
    return next(generator), generator


def _create_viewer(client, monkeypatch, *, document_status="verified"):
    monkeypatch.setattr(auth, "send_verification_code", lambda *_: None)
    response = client.post(
        "/auth/signup",
        json={
            "sex": "man",
            "identifier": "viewer@example.test",
            "password": "secure-password-123",
            "dateOfBirth": "1990-02-10",
            "acceptedTerms": True,
        },
    )
    assert response.status_code == 201
    account_id = client.get("/auth/session").json()["accountId"]
    db, generator = _session(client)
    try:
        db.execute(
            text("UPDATE accounts SET email_verified = TRUE WHERE id = :account_id"),
            {"account_id": account_id},
        )
        db.execute(
            text(
                """
                UPDATE profiles
                SET display_name = 'Viewer', bio = '', photos = '[]', interests = '[]',
                    identity = 'man', latitude = 6.5, longitude = 3.4,
                    onboarding_complete = TRUE, moderation_status = 'approved',
                    document_verification = :document_status
                WHERE account_id = :account_id
                """
            ),
            {"account_id": account_id, "document_status": document_status},
        )
        db.commit()
    finally:
        generator.close()
    return account_id


def _create_candidate(
    client,
    *,
    identity="woman",
    email_verified=True,
    moderation_status="approved",
    document_status="verified",
    discoverable_by="men",
    wants_to_discover="men",
    latitude=6.51,
    longitude=3.4,
    demo_cohort_id=None,
):
    account_id = uuid.uuid4().hex
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                INSERT INTO accounts (
                    id, email, identifier, identifier_type, password_hash, date_of_birth,
                    gender, terms_version, privacy_version, email_verified, account_state
                )
                VALUES (
                    :id, :email, :email, 'email', 'test-hash', '1995-02-10',
                    :identity, 'test', 'test', :email_verified, 'active'
                )
                """
            ),
            {
                "id": account_id,
                "email": f"{account_id}@example.test",
                "identity": identity,
                "email_verified": email_verified,
            },
        )
        db.execute(
            text(
                """
                INSERT INTO profiles (
                    account_id, display_name, bio, photos, videos, age_range, area,
                    interests, discoverable_by, wants_to_discover, identity, show_identity,
                    subscription_tier, moderation_status, onboarding_complete,
                    document_verification, latitude, longitude, demo_cohort_id
                )
                VALUES (
                    :account_id, 'Candidate', 'A test profile', '["/media/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]',
                    '[{"url":"https://media.example.test/demo.mp4"}]', '30–35', 'Yaba, Lagos',
                    '["Tech"]', :discoverable_by, :wants_to_discover, :identity, TRUE,
                    'free', :moderation_status, TRUE, :document_status, :latitude, :longitude,
                    :demo_cohort_id
                )
                """
            ),
            {
                "account_id": account_id,
                "identity": identity,
                "discoverable_by": discoverable_by,
                "wants_to_discover": wants_to_discover,
                "moderation_status": moderation_status,
                "document_status": document_status,
                "latitude": latitude,
                "longitude": longitude,
                "demo_cohort_id": demo_cohort_id,
            },
        )
        db.commit()
    finally:
        generator.close()
    return account_id


def test_discovery_feed_filters_verified_profiles_and_paginates(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    candidate_ids = [_create_candidate(client) for _ in range(7)]
    _create_candidate(client, document_status="pending")
    _create_candidate(client, moderation_status="pending")
    _create_candidate(client, email_verified=False)
    _create_candidate(client, discoverable_by="women")
    _create_candidate(client, wants_to_discover="women")
    _create_candidate(client, identity="man")
    _create_candidate(client, latitude=7.0)

    query = (
        "minAge=21&maxAge=45&lookingFor=women&interests=Tech"
        "&latitude=6.5&longitude=3.4&maxDistanceKm=10"
    )
    first_page = client.get(f"/discovery?{query}")
    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert len(first_payload["items"]) == 6
    assert first_payload["nextCursor"] == 6
    assert all(item["id"] in candidate_ids for item in first_payload["items"])
    assert first_payload["items"][0]["photos"] == ["/media/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
    assert first_payload["items"][0]["videos"][0]["url"] == "https://media.example.test/demo.mp4"
    assert first_payload["items"][0]["ageRange"] == "30–35"
    assert first_payload["items"][0]["distanceKm"] == 1.1

    second_page = client.get(f"/discovery?{query}&cursor=6")
    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["nextCursor"] is None
    assert first_payload["items"][0]["id"] != second_page.json()["items"][0]["id"]


def test_discovery_requires_document_verification_and_rejects_live_filter(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch, document_status="pending")

    denied = client.get("/discovery")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "IDENTITY_VERIFICATION_REQUIRED"

    db, generator = _session(client)
    try:
        db.execute(
            text("UPDATE profiles SET document_verification = 'verified' WHERE display_name = 'Viewer'")
        )
        db.commit()
    finally:
        generator.close()

    live_only = client.get("/discovery?liveOnly=true")
    assert live_only.status_code == 200
    assert live_only.json()["items"] == []


def test_profile_detail_only_returns_discoverable_verified_profiles(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    visible_id = _create_candidate(client)
    hidden_id = _create_candidate(client, document_status="pending")

    visible = client.get(f"/profiles/{visible_id}")
    assert visible.status_code == 200
    assert visible.json()["id"] == visible_id

    hidden = client.get(f"/profiles/{hidden_id}")
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "PROFILE_NOT_FOUND"


def test_demo_profiles_require_flag_and_are_marked(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    demo_id = _create_candidate(client, demo_cohort_id="discover-test")

    hidden = client.get("/discovery", params={"lookingFor": "women"})
    assert hidden.status_code == 200
    assert demo_id not in {profile["id"] for profile in hidden.json()["items"]}

    client.app.state.settings.demo_profiles_enabled = True
    visible = client.get("/discovery", params={"lookingFor": "women"})
    assert visible.status_code == 200
    demo = next(profile for profile in visible.json()["items"] if profile["id"] == demo_id)
    assert demo["isDemo"] is True
    assert client.get(f"/profiles/{demo_id}").json()["isDemo"] is True

    client.app.state.settings.demo_profiles_enabled = False
    assert client.get(f"/profiles/{demo_id}").status_code == 404


def test_current_location_sharing_can_be_enabled_and_stopped(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    csrf_token = client.cookies["flingra_csrf"]

    enabled = client.put(
        "/profiles/me/location-sharing",
        headers={"X-CSRF-Token": csrf_token},
        json={"latitude": 6.51234, "longitude": 3.45678},
    )
    assert enabled.status_code == 200
    assert enabled.json() == {"locationSharingEnabled": True}
    assert client.get("/profiles/me").json()["locationSharingEnabled"] is True

    db, generator = _session(client)
    try:
        location = db.execute(
            text(
                """
                SELECT live_latitude, live_longitude, location_shared_at
                FROM profiles WHERE display_name = 'Viewer'
                """
            )
        ).mappings().one()
        assert float(location["live_latitude"]) == 6.51234
        assert float(location["live_longitude"]) == 3.45678
        assert location["location_shared_at"] is not None
    finally:
        generator.close()

    stopped = client.delete(
        "/profiles/me/location-sharing",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert stopped.status_code == 200
    assert stopped.json() == {"locationSharingEnabled": False}
    assert client.get("/profiles/me").json()["locationSharingEnabled"] is False


def test_discovery_uses_recent_live_coordinates_and_returns_coarse_location(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    candidate_id = _create_candidate(client, latitude=7.0, longitude=3.4)
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                UPDATE profiles
                SET live_latitude = 6.51234, live_longitude = 3.45678,
                    location_shared_at = :shared_at
                WHERE account_id = :account_id
                """
            ),
            {
                "account_id": candidate_id,
                "shared_at": datetime.now(timezone.utc).replace(tzinfo=None),
            },
        )
        db.commit()
    finally:
        generator.close()

    nearby = client.get(
        "/discovery",
        params={
            "lookingFor": "women",
            "latitude": 6.5,
            "longitude": 3.4,
            "maxDistanceKm": 10,
        },
    )
    assert nearby.status_code == 200
    candidate = next(item for item in nearby.json()["items"] if item["id"] == candidate_id)
    assert candidate["latitude"] == 6.51
    assert candidate["longitude"] == 3.46
    assert candidate["distanceKm"] < 10

    db, generator = _session(client)
    try:
        db.execute(
            text(
                "UPDATE profiles SET location_shared_at = :shared_at WHERE account_id = :account_id"
            ),
            {
                "account_id": candidate_id,
                "shared_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=6),
            },
        )
        db.commit()
    finally:
        generator.close()

    no_longer_nearby = client.get(
        "/discovery",
        params={
            "lookingFor": "women",
            "latitude": 6.5,
            "longitude": 3.4,
            "maxDistanceKm": 10,
        },
    )
    assert no_longer_nearby.status_code == 200
    assert candidate_id not in {item["id"] for item in no_longer_nearby.json()["items"]}
