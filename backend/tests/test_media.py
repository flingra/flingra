import io
from fastapi.testclient import TestClient
from PIL import Image

from app.routes import auth


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = (body, content_type)

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def get_url(self, key: str) -> str:
        assert key in self.objects
        return f"https://private-storage.example.test/{key}?temporary=signature"


def image_bytes(format_name: str = "PNG") -> bytes:
    image = Image.new("RGB", (16, 12), color=(200, 30, 50))
    result = io.BytesIO()
    image.save(result, format=format_name)
    return result.getvalue()


def verified_woman_client(client: TestClient, monkeypatch) -> None:
    codes: list[str] = []
    monkeypatch.setattr(
        auth,
        "send_verification_code",
        lambda _settings, _recipient, code: codes.append(code),
    )
    response = client.post(
        "/auth/signup",
        json={
            "sex": "woman",
            "identifier": "media@example.com",
            "password": "secure-password-123",
            "dateOfBirth": "1995-02-10",
            "acceptedTerms": True,
        },
    )
    assert response.status_code == 201
    verified = client.post(
        "/auth/verify-contact",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"code": codes[0]},
    )
    assert verified.status_code == 200


def test_profile_photo_upload_normalizes_image_and_returns_private_media_url(api_client, monkeypatch) -> None:
    client, _ = api_client
    verified_woman_client(client, monkeypatch)
    storage = FakeObjectStorage()
    client.app.state.media_storage = storage

    response = client.post(
        "/media/photos",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        files={"file": ("profile.png", image_bytes(), "text/plain")},
    )

    assert response.status_code == 201
    result = response.json()
    assert result["mediaId"]
    assert result["url"] == f"/media/{result['mediaId']}"
    assert result["contentType"] == "image/jpeg"
    stored_content, stored_type = next(iter(storage.objects.values()))
    assert stored_content.startswith(b"\xff\xd8\xff")
    assert stored_type == "image/jpeg"


def test_identity_document_upload_is_private_and_sets_review_status(api_client, monkeypatch) -> None:
    client, _ = api_client
    verified_woman_client(client, monkeypatch)
    storage = FakeObjectStorage()
    client.app.state.media_storage = storage

    response = client.post(
        "/media/documents",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        data={"documentType": "BVN"},
        files={"file": ("identity.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 201
    media_id = response.json()["mediaId"]
    assert client.get(f"/media/{media_id}", follow_redirects=False).status_code == 307
    profile = client.get("/profiles/me").json()
    assert profile["documentType"] == "BVN"
    assert profile["documentVerification"] == "pending"


def test_upload_requires_csrf(api_client, monkeypatch) -> None:
    client, _ = api_client
    verified_woman_client(client, monkeypatch)
    client.app.state.media_storage = FakeObjectStorage()

    response = client.post("/media/photos", files={"file": ("photo.png", image_bytes(), "image/png")})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"


def test_document_upload_rejects_male_account(api_client, monkeypatch) -> None:
    client, _ = api_client
    codes: list[str] = []
    monkeypatch.setattr(auth, "send_verification_code", lambda _settings, _recipient, code: codes.append(code))
    response = client.post(
        "/auth/signup",
        json={
            "sex": "man",
            "identifier": "man@example.com",
            "password": "secure-password-123",
            "dateOfBirth": "1995-02-10",
            "acceptedTerms": True,
        },
    )
    assert response.status_code == 201
    assert client.post(
        "/auth/verify-contact",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"code": codes[0]},
    ).status_code == 200
    storage = FakeObjectStorage()
    client.app.state.media_storage = storage

    response = client.post(
        "/media/documents",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        data={"documentType": "NIN"},
        files={"file": ("identity.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_REQUIRED"
    assert storage.objects == {}


def test_invalid_image_is_rejected_without_storage_write(api_client, monkeypatch) -> None:
    client, _ = api_client
    verified_woman_client(client, monkeypatch)
    storage = FakeObjectStorage()
    client.app.state.media_storage = storage

    response = client.post(
        "/media/photos",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        files={"file": ("spoof.png", b"not an image", "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_IMAGE"
    assert storage.objects == {}


def test_oversized_image_is_rejected(api_client, monkeypatch) -> None:
    client, _ = api_client
    verified_woman_client(client, monkeypatch)
    client.app.state.settings.r2_upload_max_bytes = 16

    response = client.post(
        "/media/photos",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        files={"file": ("large.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


def test_profile_cannot_reference_external_or_unowned_media(api_client, monkeypatch) -> None:
    client, _ = api_client
    verified_woman_client(client, monkeypatch)
    csrf_token = client.cookies["flingra_csrf"]

    external = client.patch(
        "/profiles/me",
        headers={"X-CSRF-Token": csrf_token},
        json={"photos": ["https://attacker.example/image.jpg"]},
    )
    unknown_media = client.patch(
        "/profiles/me",
        headers={"X-CSRF-Token": csrf_token},
        json={"photos": ["/media/" + "a" * 32]},
    )

    assert external.status_code == 400
    assert external.json()["error"]["code"] == "INVALID_PROFILE_MEDIA"
    assert unknown_media.status_code == 400
    assert unknown_media.json()["error"]["code"] == "INVALID_PROFILE_MEDIA"


def test_non_owner_cannot_read_pending_photo_or_identity_document(api_client, monkeypatch) -> None:
    client, _ = api_client
    verified_woman_client(client, monkeypatch)
    storage = FakeObjectStorage()
    client.app.state.media_storage = storage
    photo = client.post(
        "/media/photos",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        files={"file": ("profile.png", image_bytes(), "image/png")},
    ).json()
    document = client.post(
        "/media/documents",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        data={"documentType": "NIN"},
        files={"file": ("identity.png", image_bytes(), "image/png")},
    ).json()
    assert client.get(photo["url"], follow_redirects=False).status_code == 307
    assert client.get(document["url"], follow_redirects=False).status_code == 307

    with TestClient(client.app) as other_client:
        codes: list[str] = []
        monkeypatch.setattr(
            auth,
            "send_verification_code",
            lambda _settings, _recipient, code: codes.append(code),
        )
        signed_up = other_client.post(
            "/auth/signup",
            json={
                "sex": "man",
                "identifier": "another@example.com",
                "password": "secure-password-123",
                "dateOfBirth": "1995-02-10",
                "acceptedTerms": True,
            },
        )
        assert signed_up.status_code == 201
        verified = other_client.post(
            "/auth/verify-contact",
            headers={"X-CSRF-Token": other_client.cookies["flingra_csrf"]},
            json={"code": codes[0]},
        )
        assert verified.status_code == 200
        assert other_client.get(photo["url"], follow_redirects=False).status_code == 404
        assert other_client.get(document["url"], follow_redirects=False).status_code == 404
