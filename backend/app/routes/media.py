import hashlib
import io
import logging
import uuid
import warnings
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException, ServiceUnavailable
from app.routes.auth import CurrentAccount, get_app_settings, require_csrf
from app.schemas import MediaUploadResponse, VerificationDocumentType
from app.storage import ObjectStorage, get_object_storage

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/media", tags=["media"])
DbSession = Annotated[Session, Depends(db_session)]
StorageDependency = Annotated[ObjectStorage, Depends(get_object_storage)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
MAX_IMAGE_PIXELS = 12_000_000
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def _read_bounded_upload(file: UploadFile, max_bytes: int) -> bytes:
    content = file.file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ApiException("UPLOAD_TOO_LARGE", "The uploaded image exceeds the size limit.", 413)
    if not content:
        raise ApiException("EMPTY_UPLOAD", "Choose an image to upload.", 400)
    return content


def _normalize_image(content: bytes, max_bytes: int) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if source.format not in ALLOWED_IMAGE_FORMATS:
                    raise ApiException(
                        "UNSUPPORTED_MEDIA_TYPE",
                        "Upload a JPEG, PNG, or WebP image.",
                        415,
                    )
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ApiException("INVALID_IMAGE", "The image dimensions are too large.", 413)
                source.verify()
            with Image.open(io.BytesIO(content)) as source:
                image = ImageOps.exif_transpose(source)
                if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    flattened = Image.new("RGB", rgba.size, "white")
                    flattened.paste(rgba, mask=rgba.getchannel("A"))
                    image = flattened
                else:
                    image = image.convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=88, optimize=True)
                normalized = output.getvalue()
                if len(normalized) > max_bytes:
                    raise ApiException("UPLOAD_TOO_LARGE", "The processed image exceeds the size limit.", 413)
                return normalized
    except ApiException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ApiException("INVALID_IMAGE", "The uploaded file is not a valid image.", 400) from exc


def _persist_upload(
    *,
    request: Request,
    db: Session,
    storage: ObjectStorage,
    account_id: str,
    media_id: str,
    object_key: str,
    purpose: Literal["profile-photo", "identity-document"],
    content: bytes,
    document_type: VerificationDocumentType | None = None,
) -> None:
    try:
        storage.put(object_key, content, "image/jpeg")
    except ServiceUnavailable:
        record_audit_event(
            db,
            request,
            event_type=(
                "media.identity_document.uploaded"
                if purpose == "identity-document"
                else "media.profile_photo.uploaded"
            ),
            actor_type="user",
            actor_id=account_id,
            subject_account_id=account_id,
            outcome="failure",
            metadata={"purpose": purpose, "reason": "storage_unavailable"},
        )
        db.commit()
        raise
    try:
        db.execute(
            text(
                """
                INSERT INTO media_objects (
                    id, account_id, purpose, object_key, content_type, size_bytes, sha256
                )
                VALUES (
                    :id, :account_id, :purpose, :object_key, :content_type, :size_bytes, :sha256
                )
                """
            ),
            {
                "id": media_id,
                "account_id": account_id,
                "purpose": purpose,
                "object_key": object_key,
                "content_type": "image/jpeg",
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            },
        )
        if document_type is not None:
            db.execute(
                text(
                    """
                    UPDATE profiles
                    SET document_type = :document_type, document_verification = 'pending'
                    WHERE account_id = :account_id
                    """
                ),
                {"document_type": document_type, "account_id": account_id},
            )
        record_audit_event(
            db,
            request,
            event_type=(
                "media.identity_document.uploaded"
                if purpose == "identity-document"
                else "media.profile_photo.uploaded"
            ),
            actor_type="user",
            actor_id=account_id,
            subject_account_id=account_id,
            outcome="success",
            metadata={"mediaId": media_id, "purpose": purpose},
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            storage.delete(object_key)
        except ServiceUnavailable:
            logger.error("Failed to clean up an orphaned uploaded object.")
        raise ServiceUnavailable("Could not save uploaded media metadata.") from exc


def _response(media_id: str, size_bytes: int) -> MediaUploadResponse:
    return MediaUploadResponse(
        media_id=media_id,
        url=f"/media/{media_id}",
        content_type="image/jpeg",
        size_bytes=size_bytes,
    )


@router.post(
    "/photos",
    response_model=MediaUploadResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def upload_profile_photo(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
    storage: StorageDependency,
    settings: SettingsDependency,
    file: Annotated[UploadFile, File()],
) -> MediaUploadResponse:
    if not account["email_verified"]:
        record_audit_event(
            db,
            request,
            event_type="media.profile_photo.uploaded",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="denied",
            metadata={"reason": "contact_not_verified"},
        )
        db.commit()
        raise ApiException("CONTACT_NOT_VERIFIED", "Verify your contact before uploading media.", 403)
    try:
        content = _normalize_image(
            _read_bounded_upload(file, settings.media_upload_max_bytes),
            settings.media_upload_max_bytes,
        )
    except ApiException as exc:
        record_audit_event(
            db,
            request,
            event_type="media.profile_photo.uploaded",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="failure",
            metadata={"reason": exc.code},
        )
        db.commit()
        raise
    media_id = uuid.uuid4().hex
    object_key = f"accounts/{account.account_id}/profile-photos/{media_id}"
    _persist_upload(
        request=request,
        db=db,
        storage=storage,
        account_id=account.account_id,
        media_id=media_id,
        object_key=object_key,
        purpose="profile-photo",
        content=content,
    )
    return _response(media_id, len(content))


@router.post(
    "/documents",
    response_model=MediaUploadResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def upload_identity_document(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
    storage: StorageDependency,
    settings: SettingsDependency,
    file: Annotated[UploadFile, File()],
    document_type: Annotated[VerificationDocumentType, Form(alias="documentType")],
) -> MediaUploadResponse:
    if not account["email_verified"]:
        record_audit_event(
            db,
            request,
            event_type="media.identity_document.uploaded",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="denied",
            metadata={"reason": "contact_not_verified"},
        )
        db.commit()
        raise ApiException("CONTACT_NOT_VERIFIED", "Verify your contact before uploading media.", 403)

    identity = db.execute(
        text("SELECT identity FROM profiles WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    ).scalar_one_or_none()
    if identity != "woman":
        record_audit_event(
            db,
            request,
            event_type="media.identity_document.uploaded",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="denied",
            metadata={"reason": "document_not_required"},
        )
        db.commit()
        raise ApiException("DOCUMENT_NOT_REQUIRED", "Identity documents are not required for this account.", 403)

    try:
        content = _normalize_image(
            _read_bounded_upload(file, settings.media_upload_max_bytes),
            settings.media_upload_max_bytes,
        )
    except ApiException as exc:
        record_audit_event(
            db,
            request,
            event_type="media.identity_document.uploaded",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="failure",
            metadata={"reason": exc.code},
        )
        db.commit()
        raise
    media_id = uuid.uuid4().hex
    object_key = f"accounts/{account.account_id}/identity-documents/{media_id}"
    _persist_upload(
        request=request,
        db=db,
        storage=storage,
        account_id=account.account_id,
        media_id=media_id,
        object_key=object_key,
        purpose="identity-document",
        content=content,
        document_type=document_type,
    )
    return _response(media_id, len(content))


@router.get("/{media_id}")
def get_media(
    media_id: str,
    request: Request,
    account: CurrentAccount,
    db: DbSession,
    storage: StorageDependency,
) -> RedirectResponse:
    if len(media_id) != 32 or any(character not in "0123456789abcdef" for character in media_id):
        record_audit_event(
            db,
            request,
            event_type="media.access",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="denied",
            metadata={"reason": "invalid_media_id"},
        )
        db.commit()
        raise ApiException("MEDIA_NOT_FOUND", "This media is unavailable.", 404)

    item = db.execute(
        text(
            """
            SELECT m.account_id, m.purpose, m.object_key, p.moderation_status
            FROM media_objects m
            JOIN profiles p ON p.account_id = m.account_id
            WHERE m.id = :media_id
            """
        ),
        {"media_id": media_id},
    ).mappings().first()
    if item is None:
        record_audit_event(
            db,
            request,
            event_type="media.access",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="denied",
            metadata={"reason": "media_not_found"},
        )
        db.commit()
        raise ApiException("MEDIA_NOT_FOUND", "This media is unavailable.", 404)

    is_owner = item["account_id"] == account.account_id
    is_approved_public_photo = (
        item["purpose"] == "profile-photo" and item["moderation_status"] == "approved"
    )
    if item["purpose"] == "identity-document" and not is_owner:
        record_audit_event(
            db,
            request,
            event_type="media.access",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=str(item["account_id"]),
            outcome="denied",
            metadata={"mediaId": media_id, "purpose": item["purpose"]},
        )
        db.commit()
        raise ApiException("MEDIA_NOT_FOUND", "This media is unavailable.", 404)
    if not is_owner and not is_approved_public_photo:
        record_audit_event(
            db,
            request,
            event_type="media.access",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=str(item["account_id"]),
            outcome="denied",
            metadata={"mediaId": media_id, "purpose": item["purpose"]},
        )
        db.commit()
        raise ApiException("MEDIA_NOT_FOUND", "This media is unavailable.", 404)

    try:
        signed_url = storage.get_url(item["object_key"])
    except ServiceUnavailable:
        record_audit_event(
            db,
            request,
            event_type="media.access",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=str(item["account_id"]),
            outcome="failure",
            metadata={"mediaId": media_id, "purpose": item["purpose"]},
        )
        db.commit()
        raise
    record_audit_event(
        db,
        request,
        event_type="media.access",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=str(item["account_id"]),
        outcome="success",
        metadata={"mediaId": media_id, "purpose": item["purpose"]},
    )
    db.commit()
    return RedirectResponse(
        signed_url,
        status_code=307,
        headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
    )
