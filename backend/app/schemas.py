from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AccountStage = Literal["needs-verification", "needs-onboarding", "active"]
AudiencePreference = Literal["men", "women", "everyone"]
VerificationStatus = Literal["unverified", "pending", "verified", "rejected"]
VerificationDocumentType = Literal["NIN", "BVN", "voters-card"]
AdminRole = Literal["super_admin", "reviewer", "safety_admin", "auditor"]


class ApiErrorBody(BaseModel):
    code: str
    message: str


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody


class SignUpRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sex: Literal["man", "woman"]
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    date_of_birth: date = Field(alias="dateOfBirth")
    accepted_terms: bool = Field(alias="acceptedTerms")
    referral_code: str | None = Field(default=None, alias="referralCode", max_length=64)


class SignInRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class GoogleAuthRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    credential: str = Field(min_length=100, max_length=8192)
    nonce: str = Field(min_length=16, max_length=256)
    sex: Literal["man", "woman"] | None = None
    date_of_birth: date | None = Field(default=None, alias="dateOfBirth")
    accepted_terms: bool = Field(default=False, alias="acceptedTerms")
    referral_code: str | None = Field(default=None, alias="referralCode", max_length=64)


class AdminLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class AdminSessionResponse(BaseModel):
    admin_id: str = Field(serialization_alias="adminId")
    email: str
    role: AdminRole


class AdminAccountUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    role: AdminRole | None = None
    disabled: bool | None = None

    @model_validator(mode="after")
    def require_update(self) -> "AdminAccountUpdateRequest":
        if self.role is None and self.disabled is None:
            raise ValueError("At least one admin account field must be provided.")
        return self


class AdminAccountCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=14, max_length=128)
    role: AdminRole = "reviewer"


class AdminReviewDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=1, max_length=1000)


class StageResponse(BaseModel):
    stage: AccountStage


class SessionResponse(BaseModel):
    account_id: str = Field(serialization_alias="accountId")
    masked_contact: str = Field(serialization_alias="maskedContact")
    stage: AccountStage


class VerifyContactRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12)


class TwoFactorCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12)


class PasswordResetRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=8, max_length=128)


class ProfileVideo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str = Field(min_length=1, max_length=2048)
    locked: bool | None = None
    price_naira: int | None = Field(
        default=None,
        validation_alias="priceNaira",
        serialization_alias="priceNaira",
        ge=1,
        le=10_000_000,
    )


class OwnProfileResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    display_name: str = Field(serialization_alias="displayName")
    bio: str
    photos: list[str]
    videos: list[ProfileVideo] | None = None
    age_range: str = Field(serialization_alias="ageRange")
    area: str
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float = Field(serialization_alias="distanceKm")
    interests: list[str]
    discoverable_by: AudiencePreference = Field(serialization_alias="discoverableBy")
    wants_to_discover: AudiencePreference = Field(serialization_alias="wantsToDiscover")
    identity: Literal["man", "woman", "private"]
    show_identity: bool = Field(serialization_alias="showIdentity")
    subscription_tier: Literal["free", "vip"] = Field(serialization_alias="subscriptionTier")
    moderation_status: Literal["approved", "pending", "rejected"] = Field(
        serialization_alias="moderationStatus"
    )
    two_factor_enabled: bool | None = Field(default=None, serialization_alias="twoFactorEnabled")
    two_factor_method: Literal["email", "authenticator"] | None = Field(
        default=None, serialization_alias="twoFactorMethod"
    )
    onboarding_complete: bool | None = Field(default=None, serialization_alias="onboardingComplete")
    document_verification: VerificationStatus | None = Field(
        default=None, serialization_alias="documentVerification"
    )
    document_type: VerificationDocumentType | None = Field(
        default=None, serialization_alias="documentType"
    )
    vip_expires_at: datetime | None = Field(default=None, serialization_alias="vipExpiresAt")
    location_sharing_enabled: bool = Field(
        default=False,
        serialization_alias="locationSharingEnabled",
    )


class DiscoveryProfileResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    display_name: str = Field(serialization_alias="displayName")
    bio: str
    photos: list[str]
    videos: list[ProfileVideo] | None = None
    age_range: str = Field(serialization_alias="ageRange")
    area: str
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = Field(serialization_alias="distanceKm")
    interests: list[str]
    discoverable_by: AudiencePreference = Field(serialization_alias="discoverableBy")
    wants_to_discover: AudiencePreference = Field(serialization_alias="wantsToDiscover")
    identity: Literal["man", "woman", "private"]
    show_identity: bool = Field(serialization_alias="showIdentity")
    subscription_tier: Literal["free", "vip"] = Field(serialization_alias="subscriptionTier")
    is_demo: bool = Field(default=False, serialization_alias="isDemo")


class LiveLocationUpdate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class LocationSharingResponse(BaseModel):
    location_sharing_enabled: bool = Field(serialization_alias="locationSharingEnabled")


class DiscoveryFeedResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[DiscoveryProfileResponse]
    next_cursor: int | None = Field(serialization_alias="nextCursor")


class OwnProfilePatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    display_name: str | None = Field(default=None, alias="displayName", max_length=100)
    bio: str | None = Field(default=None, max_length=2000)
    photos: list[Annotated[str, Field(min_length=1, max_length=2048)]] | None = Field(
        default=None,
        max_length=10,
    )
    videos: list[ProfileVideo] | None = Field(default=None, max_length=10)
    distance_km: float | None = Field(default=None, alias="distanceKm", ge=0)
    area: str | None = Field(default=None, max_length=160)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    interests: list[Annotated[str, Field(min_length=1, max_length=100)]] | None = Field(
        default=None,
        max_length=30,
    )
    discoverable_by: AudiencePreference | None = Field(default=None, alias="discoverableBy")
    wants_to_discover: AudiencePreference | None = Field(default=None, alias="wantsToDiscover")
    identity: Literal["man", "woman", "private"] | None = None
    show_identity: bool | None = Field(default=None, alias="showIdentity")
    two_factor_enabled: bool | None = Field(default=None, alias="twoFactorEnabled")
    two_factor_method: Literal["email", "authenticator"] | None = Field(
        default=None, alias="twoFactorMethod"
    )


class CurrentSessionResponse(SessionResponse):
    created_at: datetime = Field(serialization_alias="createdAt")


class MediaUploadResponse(BaseModel):
    media_id: str = Field(serialization_alias="mediaId")
    url: str
    content_type: Literal["image/jpeg", "video/mp4", "video/webm"] = Field(
        serialization_alias="contentType"
    )
    size_bytes: int = Field(serialization_alias="sizeBytes", ge=1)
