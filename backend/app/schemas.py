from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AccountStage = Literal["needs-verification", "needs-onboarding", "active"]
AudiencePreference = Literal["men", "women", "everyone"]
VerificationStatus = Literal["unverified", "pending", "verified", "rejected"]
VerificationDocumentType = Literal["NIN", "BVN", "voters-card"]


class ApiErrorBody(BaseModel):
    code: str
    message: str


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody


class SignUpRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sex: Literal["man", "woman"]
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    date_of_birth: date = Field(alias="dateOfBirth")
    accepted_terms: bool = Field(alias="acceptedTerms")
    referral_code: str | None = Field(default=None, alias="referralCode", max_length=64)


class SignInRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class StageResponse(BaseModel):
    stage: AccountStage


class SessionResponse(BaseModel):
    account_id: str = Field(serialization_alias="accountId")
    masked_contact: str = Field(serialization_alias="maskedContact")
    stage: AccountStage


class VerifyContactRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12)


class ProfileVideo(BaseModel):
    url: str
    locked: bool | None = None
    price_naira: int | None = Field(default=None, serialization_alias="priceNaira")


class OwnProfileResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    display_name: str = Field(serialization_alias="displayName")
    bio: str
    photos: list[str]
    videos: list[ProfileVideo] | None = None
    age_range: str = Field(serialization_alias="ageRange")
    area: str
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
    selfie_verification: VerificationStatus | None = Field(
        default=None, serialization_alias="selfieVerification"
    )
    selfie_photo: str | None = Field(default=None, serialization_alias="selfiePhoto")
    document_verification: VerificationStatus | None = Field(
        default=None, serialization_alias="documentVerification"
    )
    document_type: VerificationDocumentType | None = Field(
        default=None, serialization_alias="documentType"
    )
    vip_expires_at: datetime | None = Field(default=None, serialization_alias="vipExpiresAt")


class OwnProfilePatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    display_name: str | None = Field(default=None, alias="displayName", max_length=100)
    bio: str | None = Field(default=None, max_length=2000)
    photos: list[str] | None = None
    videos: list[ProfileVideo] | None = None
    area: str | None = Field(default=None, max_length=160)
    interests: list[str] | None = None
    discoverable_by: AudiencePreference | None = Field(default=None, alias="discoverableBy")
    wants_to_discover: AudiencePreference | None = Field(default=None, alias="wantsToDiscover")
    identity: Literal["man", "woman", "private"] | None = None
    show_identity: bool | None = Field(default=None, alias="showIdentity")
    two_factor_enabled: bool | None = Field(default=None, alias="twoFactorEnabled")
    two_factor_method: Literal["email", "authenticator"] | None = Field(
        default=None, alias="twoFactorMethod"
    )
    selfie_verification: VerificationStatus | None = Field(default=None, alias="selfieVerification")
    selfie_photo: str | None = Field(default=None, alias="selfiePhoto")
    document_verification: VerificationStatus | None = Field(
        default=None, alias="documentVerification"
    )
    document_type: VerificationDocumentType | None = Field(default=None, alias="documentType")


class CurrentSessionResponse(SessionResponse):
    created_at: datetime = Field(serialization_alias="createdAt")
