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

    def delete(self, key: str, content_type: str = "image/jpeg") -> None: ...

    def get_url(self, key: str, content_type: str = "image/jpeg") -> str: ...


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
        if content_type.startswith("image/"):
            resource_type = "image"
        elif content_type.startswith("video/"):
            resource_type = "video"
        elif content_type == "application/pdf":
            resource_type = "raw"
        else:
            raise ValueError("Unsupported Cloudinary media type.")
        try:
            uploader.upload(
                BytesIO(body),
                public_id=key,
                resource_type=resource_type,
                type="authenticated",
                overwrite=False,
                use_filename=False,
                unique_filename=False,
            )
        except (CloudinaryError, HTTPError, OSError) as exc:
            raise ServiceUnavailable("Media storage is temporarily unavailable.") from exc

    def delete(self, key: str, content_type: str = "image/jpeg") -> None:
        resource_type = self._resource_type(content_type)
        try:
            result = uploader.destroy(
                key,
                resource_type=resource_type,
                type="authenticated",
                invalidate=True,
            )
        except (CloudinaryError, HTTPError, OSError) as exc:
            raise ServiceUnavailable("Media cleanup failed.") from exc
        if result.get("result") not in {"ok", "not found"}:
            raise ServiceUnavailable("Media cleanup failed.")

    def get_url(self, key: str, content_type: str = "image/jpeg") -> str:
        resource_type = self._resource_type(content_type)
        extension = {
            "image/jpeg": "jpg",
            "video/mp4": "mp4",
            "video/webm": "webm",
            "application/pdf": None,
        }.get(content_type)
        try:
            return utils.private_download_url(
                key,
                extension,
                resource_type=resource_type,
                type="authenticated",
                expires_at=int(time.time()) + 120,
            )
        except (CloudinaryError, HTTPError, OSError) as exc:
            raise ServiceUnavailable("Media storage is temporarily unavailable.") from exc

    @staticmethod
    def _resource_type(content_type: str) -> str:
        if content_type.startswith("image/"):
            return "image"
        if content_type.startswith("video/"):
            return "video"
        if content_type == "application/pdf":
            return "raw"
        raise ValueError("Unsupported Cloudinary media type.")


def get_object_storage(request: Request) -> ObjectStorage:
    storage = request.app.state.media_storage
    if storage is None:
        storage = CloudinaryObjectStorage(request.app.state.settings)
        request.app.state.media_storage = storage
    return storage
