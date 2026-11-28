from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ReportReason = Literal["fake-profile", "harassment", "inappropriate-content", "underage", "other"]
AttachmentType = Literal["image", "video", "file"]


class BlockCreateRequest(BaseModel):
    target_id: str = Field(alias="targetId", min_length=1, max_length=64)


class ReportCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    target_id: str = Field(alias="targetId", min_length=1, max_length=64)
    reason: ReportReason
    description: str | None = Field(default=None, max_length=2000)
    also_block: bool = Field(default=False, alias="alsoBlock")


class BlockedAccountResponse(BaseModel):
    id: str
    display_name: str = Field(serialization_alias="displayName")
    photo: str | None
    blocked_at: datetime = Field(serialization_alias="blockedAt")


class EmergencyContactRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=32)
    relationship: str = Field(min_length=1, max_length=80)


class EmergencyContactResponse(BaseModel):
    id: str
    name: str
    phone: str
    relationship: str


class SafetyCheckInResponse(BaseModel):
    id: str
    message: str
    notified_contacts: list[str] = Field(serialization_alias="notifiedContacts")
    status: Literal["sending", "sent", "partially_sent", "failed"]
    location_link: str | None = Field(serialization_alias="locationLink")
    created_at: datetime = Field(serialization_alias="createdAt")


class SafetyCheckInCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    message: str = Field(default="", max_length=1000)
    location_link: str | None = Field(default=None, alias="locationLink", max_length=2048)


class ChatAttachment(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    type: AttachmentType
    name: str = Field(min_length=1, max_length=255)


class ChatThreadCreateRequest(BaseModel):
    other_id: str = Field(alias="otherId", min_length=1, max_length=64)


class ChatInterestCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    target_id: str = Field(alias="targetId", min_length=1, max_length=64)


class ChatInterestResponse(BaseModel):
    id: str
    sender_id: str = Field(serialization_alias="senderId")
    sender_name: str = Field(serialization_alias="senderName")
    sender_photo: str = Field(serialization_alias="senderPhoto")
    status: Literal["pending", "accepted", "declined"]
    created_at: datetime = Field(serialization_alias="createdAt")


class ChatMessageCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    text: str = Field(default="", max_length=5000)
    attachment: ChatAttachment | None = None


class ChatThreadResponse(BaseModel):
    id: str
    other_id: str = Field(serialization_alias="otherId")
    other_name: str = Field(serialization_alias="otherName")
    other_photo: str = Field(serialization_alias="otherPhoto")
    last_message: str = Field(serialization_alias="lastMessage")
    last_message_at: datetime = Field(serialization_alias="lastMessageAt")


class DirectMessageResponse(BaseModel):
    id: str
    thread_id: str = Field(serialization_alias="threadId")
    author_id: str = Field(serialization_alias="authorId")
    text: str
    attachment: ChatAttachment | None = None
    payment_id: str | None = Field(default=None, serialization_alias="paymentId")
    created_at: datetime = Field(serialization_alias="createdAt")


class MeetupPaymentCreateRequest(BaseModel):
    amount_naira: int = Field(alias="amountNaira", gt=0, le=10_000_000)


class MeetupPaymentDisputeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class MeetupPaymentResolutionRequest(BaseModel):
    resolution: Literal["release", "refund"]
    reason: str = Field(min_length=1, max_length=1000)


class MeetupPaymentResponse(BaseModel):
    id: str
    from_id: str = Field(serialization_alias="fromId")
    from_name: str = Field(serialization_alias="fromName")
    to_id: str = Field(serialization_alias="toId")
    to_name: str = Field(serialization_alias="toName")
    amount_naira: int = Field(serialization_alias="amountNaira")
    status: Literal["proposed", "held", "released", "refunded", "declined", "disputed"]
    created_at: datetime = Field(serialization_alias="createdAt")
    resolved_at: datetime | None = Field(default=None, serialization_alias="resolvedAt")


class LiveStreamStartRequest(BaseModel):
    title: str = Field(default="", max_length=80)


class LiveStreamResponse(BaseModel):
    id: str
    host_id: str = Field(serialization_alias="hostId")
    host_name: str = Field(serialization_alias="hostName")
    host_photo: str = Field(serialization_alias="hostPhoto")
    host_video: str | None = Field(default=None, serialization_alias="hostVideo")
    title: str
    started_at: datetime = Field(serialization_alias="startedAt")
    participant_ids: list[str] = Field(serialization_alias="participantIds")


class LiveKitConnectionResponse(BaseModel):
    url: str
    token: str


class CallCreditPriceRequest(BaseModel):
    price_naira: int = Field(alias="priceNaira", gt=0, le=1_000_000)


class CallCreditPurchaseRequest(BaseModel):
    coins: int = Field(gt=0, le=1000)


class CallStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    target_id: str = Field(alias="targetId", min_length=1, max_length=64)
    call_type: Literal["audio", "video"] = Field(default="video", alias="callType")


class CallSessionResponse(BaseModel):
    call_id: str = Field(serialization_alias="callId")
    caller_id: str = Field(serialization_alias="callerId")
    callee_id: str = Field(serialization_alias="calleeId")
    call_type: Literal["audio", "video"] = Field(serialization_alias="callType")
    status: Literal["ringing", "connecting", "active", "declined", "ended"]
    livekit_url: str | None = Field(default=None, serialization_alias="liveKitUrl")
    token: str | None = None
    credit_balance: int | None = Field(default=None, serialization_alias="creditBalance")


class CallHistoryItemResponse(BaseModel):
    call_id: str = Field(serialization_alias="callId")
    participant_id: str = Field(serialization_alias="participantId")
    participant_name: str = Field(serialization_alias="participantName")
    participant_photo: str | None = Field(serialization_alias="participantPhoto")
    participant_identity: Literal["man", "woman", "private"] = Field(serialization_alias="participantIdentity")
    call_type: Literal["audio", "video"] = Field(serialization_alias="callType")
    direction: Literal["incoming", "outgoing"]
    status: Literal["completed", "missed", "no-answer", "declined"]
    created_at: datetime = Field(serialization_alias="createdAt")
    started_at: datetime | None = Field(serialization_alias="startedAt")
    ended_at: datetime | None = Field(serialization_alias="endedAt")
    duration_seconds: int = Field(serialization_alias="durationSeconds")


class VideoUnlockRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    price_naira: int | None = Field(default=None, alias="priceNaira", ge=1)
    author_name: str | None = Field(default=None, alias="authorName", max_length=100)


class VideoUnlockResponse(BaseModel):
    url: str
    unlocked: bool
    price_naira: int = Field(serialization_alias="priceNaira")


class LiveJoinRequestResponse(BaseModel):
    id: str
    stream_id: str = Field(serialization_alias="streamId")
    requester_id: str = Field(serialization_alias="requesterId")
    requester_name: str = Field(serialization_alias="requesterName")
    requester_photo: str = Field(serialization_alias="requesterPhoto")
    status: Literal["pending", "accepted", "declined", "expired"]
    created_at: datetime = Field(serialization_alias="createdAt")


class LiveJoinRequestDecisionRequest(BaseModel):
    accept: bool


class LiveStreamMemberResponse(BaseModel):
    id: str
    name: str
    photo: str


class LiveStreamMessageCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    text: str = Field(min_length=1, max_length=500)
    kind: Literal["message", "gift"] = "message"
    gift_id: str | None = Field(default=None, alias="giftId", min_length=1, max_length=40)


class LiveStreamMessageResponse(BaseModel):
    id: str
    stream_id: str = Field(serialization_alias="streamId")
    author_id: str = Field(serialization_alias="authorId")
    author_name: str = Field(serialization_alias="authorName")
    kind: Literal["message", "gift", "join", "warning"]
    text: str
    gift_id: str | None = Field(default=None, serialization_alias="giftId")
    created_at: datetime = Field(serialization_alias="createdAt")


class PostCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    photos: list[str] = Field(default_factory=list, max_length=10)
    video: str | None = Field(default=None, max_length=2048)
    caption: str | None = Field(default=None, max_length=2000)


class PostResponse(BaseModel):
    id: str
    author_id: str = Field(serialization_alias="authorId")
    photos: list[str]
    video: str | None = None
    caption: str | None = None
    created_at: datetime = Field(serialization_alias="createdAt")


class PostListResponse(BaseModel):
    items: list[PostResponse]
    next_cursor: int | None = Field(default=None, serialization_alias="nextCursor")


class StatusCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    media: str = Field(min_length=1, max_length=2048)
    kind: Literal["image", "video"]


class StatusResponse(BaseModel):
    id: str
    author_id: str = Field(serialization_alias="authorId")
    author_name: str = Field(serialization_alias="authorName")
    author_photo: str = Field(serialization_alias="authorPhoto")
    media: str
    kind: Literal["image", "video"]
    created_at: datetime = Field(serialization_alias="createdAt")


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    current_password: str = Field(alias="currentPassword", min_length=1, max_length=128)
    new_password: str = Field(alias="newPassword", min_length=8, max_length=128)


class DeviceSessionResponse(BaseModel):
    id: str
    device: str
    last_active: str = Field(serialization_alias="lastActive")
    current: bool


class PrivacyRequestResponse(BaseModel):
    request_id: str = Field(serialization_alias="requestId")
    status: Literal["queued"] = "queued"


class PrivacyRequestStatusResponse(BaseModel):
    request_id: str = Field(serialization_alias="requestId")
    status: Literal["queued", "processing", "completed", "failed"]
    result: dict[str, object] | None = None


class VipPlanResponse(BaseModel):
    id: str
    name: str
    duration_days: int = Field(serialization_alias="durationDays")
    price_naira: int = Field(serialization_alias="priceNaira")


class SubscriptionStatusResponse(BaseModel):
    tier: Literal["free", "vip"]
    expires_at: datetime | None = Field(default=None, serialization_alias="expiresAt")


class VipSubscriptionRequest(BaseModel):
    plan_id: str = Field(alias="planId", min_length=1, max_length=64)


class GiftPurchaseRequest(BaseModel):
    gift_type_id: str = Field(alias="giftTypeId", min_length=1, max_length=40)
    quantity: int = Field(default=1, ge=1, le=50)


class GiftSendRequest(BaseModel):
    recipient_id: str = Field(alias="recipientId", min_length=1, max_length=64)


class GiftTypeResponse(BaseModel):
    id: str
    name: str
    emoji: str
    price_naira: int = Field(serialization_alias="priceNaira")


class OwnedGiftResponse(BaseModel):
    gift_type_id: str = Field(serialization_alias="giftTypeId")
    quantity: int


class ReceivedGiftResponse(BaseModel):
    id: str
    gift_type_id: str = Field(serialization_alias="giftTypeId")
    from_id: str = Field(serialization_alias="fromId")
    from_name: str = Field(serialization_alias="fromName")
    value_naira: int = Field(serialization_alias="valueNaira")
    redeemed: bool
    created_at: datetime = Field(serialization_alias="createdAt")


class WalletTransactionResponse(BaseModel):
    id: str
    type: str
    amount_naira: int = Field(serialization_alias="amountNaira")
    description: str
    status: Literal["completed", "pending"]
    created_at: datetime = Field(serialization_alias="createdAt")


class WalletTopUpRequest(BaseModel):
    amount_naira: int = Field(alias="amountNaira", gt=0, le=10_000_000)


class WalletTopUpVerificationRequest(BaseModel):
    reference: str = Field(min_length=1, max_length=100)


class PayoutBankAccountRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    account_number: str = Field(alias="accountNumber", pattern=r"^[0-9]{10}$")
    bank_code: str = Field(alias="bankCode", min_length=1, max_length=16)


class PayoutRequestBody(BaseModel):
    amount_naira: int = Field(alias="amountNaira", gt=0, le=10_000_000)



class AdminSafetyDecisionRequest(BaseModel):
    decision: Literal["reviewed", "dismissed"]
    reason: str = Field(min_length=1, max_length=1000)
