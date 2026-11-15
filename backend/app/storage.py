from io import BytesIO
import time
from typing import Protocol

import cloudinary
from cloudinary import uploader, utils
from cloudinary.exceptions import Error as CloudinaryError
from fastapi import Request
from urllib3.exceptions import HTTPError

from app.config import Settings
from app.errors import ServiceUnavailable


class ObjectStorage(Protocol):
    def put(self, key: str, body: bytes, content_type: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def get_url(self, key: str) -> str: ...


class CloudinaryObjectStorage:
    def __init__(self, settings: Settings) -> None:
        if (
            not settings.cloudinary_cloud_name
            or not settings.cloudinary_api_key
            or not settings.cloudinary_api_secret
        ):
            raise ServiceUnavailable("Media storage is not configured.")

        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret.get_secret_value(),
            secure=True,
        )

    def put(self, key: str, body: bytes, content_type: str) -> None:
        if content_type != "image/jpeg":
            raise ValueError("Cloudinary media uploads must be JPEG images.")
        try:
            uploader.upload(
                BytesIO(body),
                public_id=key,
                resource_type="image",
                type="authenticated",
                overwrite=False,
                use_filename=False,
                unique_filename=False,
            )
        except (CloudinaryError, HTTPError, OSError) as exc:
            raise ServiceUnavailable("Media storage is temporarily unavailable.") from exc

    def delete(self, key: str) -> None:
        try:
            result = uploader.destroy(
                key,
                resource_type="image",
                type="authenticated",
                invalidate=True,
            )
        except (CloudinaryError, HTTPError, OSError) as exc:
            raise ServiceUnavailable("Media cleanup failed.") from exc
        if result.get("result") not in {"ok", "not found"}:
            raise ServiceUnavailable("Media cleanup failed.")

    def get_url(self, key: str) -> str:
        try:
            return utils.private_download_url(
                key,
                "jpg",
                resource_type="image",
                type="authenticated",
                expires_at=int(time.time()) + 120,
            )
        except (CloudinaryError, HTTPError, OSError) as exc:
            raise ServiceUnavailable("Media storage is temporarily unavailable.") from exc


def get_object_storage(request: Request) -> ObjectStorage:
    storage = request.app.state.media_storage
    if storage is None:
        storage = CloudinaryObjectStorage(request.app.state.settings)
        request.app.state.media_storage = storage
    return storage
