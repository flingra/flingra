import time
from typing import BinaryIO

import pytest
from cloudinary.exceptions import Error as CloudinaryError

from app import storage as storage_module
from app.config import Settings
from app.errors import ServiceUnavailable
from app.storage import CloudinaryObjectStorage


def test_cloudinary_storage_uses_authenticated_assets_and_temporary_urls(monkeypatch) -> None:
    config: dict[str, object] = {}
    upload_options: dict[str, object] = {}
    delete_options: dict[str, object] = {}
    download_options: dict[str, object] = {}

    def fake_config(**options: object) -> None:
        config.update(options)

    def fake_upload(body: BinaryIO, **options: object) -> dict[str, str]:
        assert body.read() == b"jpeg-data"
        upload_options.update(options)
        return {"public_id": str(options["public_id"]), "type": str(options["type"])}

    def fake_destroy(_public_id: str, **options: object) -> dict[str, str]:
        delete_options.update(options)
        return {"result": "ok"}

    def fake_private_download_url(
        _public_id: str,
        _format: str,
        **options: object,
    ) -> str:
        download_options.update(options)
        return "https://cloudinary.example.test/temporary"

    monkeypatch.setattr(storage_module.cloudinary, "config", fake_config)
    monkeypatch.setattr(storage_module.uploader, "upload", fake_upload)
    monkeypatch.setattr(storage_module.uploader, "destroy", fake_destroy)
    monkeypatch.setattr(storage_module.utils, "private_download_url", fake_private_download_url)

    storage = CloudinaryObjectStorage(
        Settings(
            cloudinary_cloud_name="test-cloud",
            cloudinary_api_key="test-key",
            cloudinary_api_secret="test-secret",
        )
    )
    key = "accounts/account-id/identity-documents/media-id"
    storage.put(key, b"jpeg-data", "image/jpeg")
    temporary_url = storage.get_url(key)
    storage.delete(key)

    assert config == {
        "cloud_name": "test-cloud",
        "api_key": "test-key",
        "api_secret": "test-secret",
        "secure": True,
    }
    assert upload_options == {
        "public_id": key,
        "resource_type": "image",
        "type": "authenticated",
        "overwrite": False,
        "use_filename": False,
        "unique_filename": False,
    }
    assert temporary_url == "https://cloudinary.example.test/temporary"
    assert download_options["type"] == "authenticated"
    assert download_options["resource_type"] == "image"
    assert time.time() < float(download_options["expires_at"]) <= time.time() + 121
    assert delete_options == {
        "resource_type": "image",
        "type": "authenticated",
        "invalidate": True,
    }


def test_cloudinary_storage_reports_upload_errors(monkeypatch) -> None:
    def fail_upload(*_args: object, **_options: object) -> None:
        raise CloudinaryError("upload failed")

    monkeypatch.setattr(storage_module.cloudinary, "config", lambda **_options: None)
    monkeypatch.setattr(storage_module.uploader, "upload", fail_upload)
    storage = CloudinaryObjectStorage(
        Settings(
            cloudinary_cloud_name="test-cloud",
            cloudinary_api_key="test-key",
            cloudinary_api_secret="test-secret",
        )
    )

    with pytest.raises(ServiceUnavailable, match="Media storage is temporarily unavailable"):
        storage.put("accounts/account-id/profile-photos/media-id", b"jpeg-data", "image/jpeg")
