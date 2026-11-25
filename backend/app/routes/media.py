import hashlib
import io
import json
import logging
import uuid
import warnings
from datetime import UTC, datetime, timedelta
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
from app.routes.auth import CurrentAccount, IdentityVerifiedAccount, get_app_settings, require_csrf
from app.routes.profiles import _visible_profile_rows
from app.schemas import MediaUploadResponse, VerificationDocumentType
from app.feature_schemas import StatusResponse
from app.storage import ObjectStorage, get_object_storage

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/media", tags=["media"])
status_router = APIRouter(tags=["content"])
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
    purpose: Literal[
        "profile-photo",
        "identity-document",
        "status-media",
        "profile-video",
        "post-video",
        "chat-attachment",
    ],
    content: bytes,
    content_type: str = "image/jpeg",
    document_type: VerificationDocumentType | None = None,
) -> None:
    try:
        storage.put(object_key, content, content_type)
    except ServiceUnavailable:
        event_type = {
            "identity-document": "media.identity_document.uploaded",
            "profile-photo": "media.profile_photo.uploaded",
            "status-media": "media.status.uploaded",
            "profile-video": "media.profile_video.uploaded",
            "post-video": "media.post_video.uploaded",
            "chat-attachment": "chat.attachment_uploaded",
        }[purpose]
        record_audit_event(
            db,
            request,
            event_type=event_type,
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
                "content_type": content_type,
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
        event_type = {
            "identity-document": "media.identity_document.uploaded",
            "profile-photo": "media.profile_photo.uploaded",
            "status-media": "media.status.uploaded",
            "profile-video": "media.profile_video.uploaded",
            "post-video": "media.post_video.uploaded",
            "chat-attachment": "chat.attachment_uploaded",
        }[purpose]
        record_audit_event(
            db,
            request,
            event_type=event_type,
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
            storage.delete(object_key, content_type)
        except ServiceUnavailable:
            logger.error("Failed to clean up an orphaned uploaded object.")
        raise ServiceUnavailable("Could not save uploaded media metadata.") from exc


def _response(media_id: str, size_bytes: int, content_type: str = "image/jpeg") -> MediaUploadResponse:
    return MediaUploadResponse(
        media_id=media_id,
        url=f"/media/{media_id}",
        content_type=content_type,
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


@router.post("/videos", response_model=MediaUploadResponse, status_code=201, dependencies=[Depends(require_csrf)])
def upload_video(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
    storage: StorageDependency,
    settings: SettingsDependency,
    file: Annotated[UploadFile, File()],
    purpose: Literal["profile", "post"] = "profile",
) -> MediaUploadResponse:
    if not account["email_verified"]:
        raise ApiException("CONTACT_NOT_VERIFIED", "Verify your contact before uploading media.", 403)
    if not account["onboarding_complete"]:
        raise ApiException("ONBOARDING_REQUIRED", "Complete onboarding before uploading a video.", 403)
    profile = db.execute(
        text("SELECT moderation_status FROM profiles WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    ).scalar_one_or_none()
    if profile != "approved":
        raise ApiException("PROFILE_NOT_APPROVED", "Your profile must be approved before uploading a video.", 403)
    if not file.content_type or file.content_type.lower() not in {"video/mp4", "video/webm"}:
        raise ApiException("UNSUPPORTED_MEDIA_TYPE", "Upload an MP4 or WebM video.", 415)
    content = file.file.read(settings.video_upload_max_bytes + 1)
    if len(content) > settings.video_upload_max_bytes:
        raise ApiException("UPLOAD_TOO_LARGE", "The uploaded video exceeds the size limit.", 413)
    if not content:
        raise ApiException("EMPTY_UPLOAD", "Choose a video to upload.", 400)
    if file.content_type.lower() == "video/mp4" and b"ftyp" not in content[:32]:
        raise ApiException("INVALID_VIDEO", "The uploaded file is not a valid MP4 video.", 400)
    if file.content_type.lower() == "video/webm" and not content.startswith(b"\x1a\x45\xdf\xa3"):
        raise ApiException("INVALID_VIDEO", "The uploaded file is not a valid WebM video.", 400)
    media_id = uuid.uuid4().hex
    media_purpose = "profile-video" if purpose == "profile" else "post-video"
    object_key = f"accounts/{account.account_id}/{media_purpose}/{media_id}"
    _persist_upload(
        request=request,
        db=db,
        storage=storage,
        account_id=account.account_id,
        media_id=media_id,
        object_key=object_key,
        purpose=media_purpose,
        content=content,
        content_type=file.content_type.lower(),
    )
    return _response(media_id, len(content), file.content_type.lower())


@status_router.post(
    "/statuses",
    response_model=StatusResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_status(
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    storage: StorageDependency,
    settings: SettingsDependency,
    file: Annotated[UploadFile, File()],
) -> StatusResponse:
    if not account["email_verified"] or not account["onboarding_complete"]:
        raise ApiException("ONBOARDING_REQUIRED", "Complete verification and onboarding before posting a status.", 403)
    profile = db.execute(
        text(
            """
            SELECT display_name, photos, moderation_status
            FROM profiles WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    ).mappings().first()
    if profile is None:
        raise ApiException("NO_PROFILE", "Finish onboarding before posting a status.", 404)
    if profile["moderation_status"] != "approved":
        raise ApiException("PROFILE_NOT_APPROVED", "Your profile must be approved before posting a status.", 403)
    is_video = bool(file.content_type and file.content_type.lower() in {"video/mp4", "video/webm"})
    if is_video:
        content = file.file.read(settings.video_upload_max_bytes + 1)
        if len(content) > settings.video_upload_max_bytes:
            raise ApiException("UPLOAD_TOO_LARGE", "The uploaded video exceeds the size limit.", 413)
        if not content:
            raise ApiException("EMPTY_UPLOAD", "Choose a video to upload.", 400)
        content_type = file.content_type.lower()
        if content_type == "video/mp4" and b"ftyp" not in content[:32]:
            raise ApiException("INVALID_VIDEO", "The uploaded file is not a valid MP4 video.", 400)
        if content_type == "video/webm" and not content.startswith(b"\x1a\x45\xdf\xa3"):
            raise ApiException("INVALID_VIDEO", "The uploaded file is not a valid WebM video.", 400)
    else:
        if file.content_type and file.content_type.lower().startswith("video/"):
            raise ApiException("UNSUPPORTED_MEDIA_TYPE", "Upload an MP4 or WebM video.", 415)
        content = _normalize_image(
            _read_bounded_upload(file, settings.media_upload_max_bytes),
            settings.media_upload_max_bytes,
        )
        content_type = "image/jpeg"
    now = datetime.now(UTC).replace(tzinfo=None)
    media_id = uuid.uuid4().hex
    object_key = f"accounts/{account.account_id}/statuses/{media_id}"
    _persist_upload(
        request=request,
        db=db,
        storage=storage,
        account_id=account.account_id,
        media_id=media_id,
        object_key=object_key,
        purpose="status-media",
        content=content,
        content_type=content_type,
    )
    status_id = uuid.uuid4().hex
    db.execute(
        text(
            """
            INSERT INTO member_statuses (
                id, author_id, media_url, media_kind, created_at, expires_at
            )
            VALUES (
                :id, :author_id, :media_url, :media_kind, :created_at, :expires_at
            )
            """
        ),
        {
            "id": status_id,
            "author_id": account.account_id,
            "media_url": f"/media/{media_id}",
            "media_kind": "video" if is_video else "image",
            "created_at": now,
            "expires_at": now + timedelta(hours=24),
        },
    )
    photos = json.loads(profile["photos"]) if isinstance(profile["photos"], str) else profile["photos"]
    record_audit_event(
        db,
        request,
        event_type="content.status_created",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"statusId": status_id, "kind": "video" if is_video else "image"},
    )
    db.commit()
    return StatusResponse(
        id=status_id,
        author_id=account.account_id,
        author_name=profile["display_name"],
        author_photo=photos[0] if photos else "",
        media=f"/media/{media_id}",
        kind="video" if is_video else "image",
        created_at=now,
    )


@router.get("/{media_id}")
def get_media(
    media_id: str,
    request: Request,
    account: CurrentAccount,
    db: DbSession,
    storage: StorageDependency,
    settings: SettingsDependency,
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
            SELECT m.account_id, m.purpose, m.object_key, m.content_type,
                   p.moderation_status
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
    is_visible_status = False
    if item["purpose"] == "status-media":
        is_visible_status = (
            db.execute(
                text(
                    """
                    SELECT 1
                    FROM member_statuses s
                    JOIN accounts a ON a.id = s.author_id
                    JOIN profiles p ON p.account_id = a.id
                    JOIN profiles viewer ON viewer.account_id = :viewer_id
                    WHERE s.media_url = :media_url
                      AND s.expires_at > :now
                      AND a.email_verified = TRUE
                      AND p.onboarding_complete = TRUE
                      AND p.document_verification = 'verified'
                      AND p.moderation_status = 'approved'
                      AND (
                          p.discoverable_by = 'everyone'
                          OR p.discoverable_by = CASE viewer.identity
                              WHEN 'man' THEN 'men' ELSE 'women' END
                      )
                      AND (
                          p.wants_to_discover = 'everyone'
                          OR p.wants_to_discover = CASE viewer.identity
                              WHEN 'man' THEN 'men' ELSE 'women' END
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM safety_blocks b
                          WHERE (b.blocker_id = :viewer_id AND b.blocked_id = a.id)
                             OR (b.blocker_id = a.id AND b.blocked_id = :viewer_id)
                      )
                    LIMIT 1
                    """
                ),
                {
                    "viewer_id": account.account_id,
                    "media_url": f"/media/{media_id}",
                    "now": datetime.now(UTC).replace(tzinfo=None),
                },
            ).first()
            is not None
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
    is_visible_profile_video = False
    is_visible_post_video = False
    is_accessible_chat_attachment = False
    if item["purpose"] == "profile-video" and not is_owner:
        profile_videos = db.execute(
            text("SELECT videos FROM profiles WHERE account_id = :account_id"),
            {"account_id": item["account_id"]},
        ).scalar_one_or_none()
        profile_videos = json.loads(profile_videos) if isinstance(profile_videos, str) else profile_videos
        matching_video = next(
            (
                video for video in profile_videos or []
                if isinstance(video, dict) and video.get("url") == f"/media/{media_id}"
            ),
            None,
        )
        viewer_identity = db.execute(
            text("SELECT identity FROM profiles WHERE account_id = :account_id"),
            {"account_id": account.account_id},
        ).scalar_one_or_none()
        visible = viewer_identity is not None and any(
            str(row["id"]) == str(item["account_id"])
            for row in _visible_profile_rows(
                db,
                account.account_id,
                viewer_identity,
                settings.demo_profiles_enabled,
                profile_id=str(item["account_id"]),
            )
        )
        unlocked = db.execute(
            text(
                """
                SELECT 1 FROM video_unlocks
                WHERE viewer_id = :viewer_id AND media_id = :media_id
                LIMIT 1
                """
            ),
            {"viewer_id": account.account_id, "media_id": media_id},
        ).first() is not None
        is_visible_profile_video = bool(
            visible
            and matching_video is not None
            and (not matching_video.get("locked") or unlocked)
        )
    if item["purpose"] == "post-video" and not is_owner:
        viewer_identity = db.execute(
            text("SELECT identity FROM profiles WHERE account_id = :account_id"),
            {"account_id": account.account_id},
        ).scalar_one_or_none()
        visible = viewer_identity is not None and any(
            str(row["id"]) == str(item["account_id"])
            for row in _visible_profile_rows(
                db,
                account.account_id,
                viewer_identity,
                settings.demo_profiles_enabled,
                profile_id=str(item["account_id"]),
            )
        )
        is_visible_post_video = bool(
            visible
            and db.execute(
                text(
                    """
                    SELECT 1 FROM member_posts
                    WHERE author_id = :owner_id AND video_url = :media_url
                    LIMIT 1
                    """
                ),
                {
                    "owner_id": item["account_id"],
                    "media_url": f"/media/{media_id}",
                },
            ).first()
        )
    if item["purpose"] == "chat-attachment":
        is_accessible_chat_attachment = db.execute(
            text(
                """
                SELECT 1
                FROM chat_messages m
                JOIN chat_threads t ON t.id = m.thread_id
                WHERE m.attachment_media_id = :media_id
                  AND (t.participant_a_id = :viewer_id OR t.participant_b_id = :viewer_id)
                  AND NOT EXISTS (
                      SELECT 1 FROM safety_blocks b
                      WHERE (b.blocker_id = :viewer_id AND b.blocked_id = :owner_id)
                         OR (b.blocker_id = :owner_id AND b.blocked_id = :viewer_id)
                  )
                LIMIT 1
                """
            ),
            {
                "media_id": media_id,
                "viewer_id": account.account_id,
                "owner_id": item["account_id"],
            },
        ).first() is not None
    if not is_owner and not (
        is_approved_public_photo
        or is_visible_status
        or is_visible_profile_video
        or is_visible_post_video
        or is_accessible_chat_attachment
    ):
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
        signed_url = storage.get_url(item["object_key"], item["content_type"])
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
