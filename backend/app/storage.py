from typing import Protocol

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Request

from app.config import Settings
from app.errors import ServiceUnavailable


class ObjectStorage(Protocol):
    def put(self, key: str, body: bytes, content_type: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def get_url(self, key: str) -> str: ...


class R2ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        if (
            not settings.r2_account_id
            or not settings.r2_bucket
            or not settings.r2_access_key_id
            or not settings.r2_secret_access_key
        ):
            raise ServiceUnavailable("Media storage is not configured.")

        endpoint = settings.r2_endpoint or f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
        self.bucket = settings.r2_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=settings.r2_region,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key.get_secret_value(),
            config=BotoConfig(
                signature_version="s3v4",
                connect_timeout=3,
                read_timeout=10,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    def put(self, key: str, body: bytes, content_type: str) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                CacheControl="private, no-store",
            )
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailable("Media storage is temporarily unavailable.") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailable("Media cleanup failed.") from exc

    def get_url(self, key: str) -> str:
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=120,
            )
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailable("Media storage is temporarily unavailable.") from exc


def get_object_storage(request: Request) -> ObjectStorage:
    storage = request.app.state.media_storage
    if storage is None:
        storage = R2ObjectStorage(request.app.state.settings)
        request.app.state.media_storage = storage
    return storage
