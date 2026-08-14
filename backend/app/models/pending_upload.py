"""`pending_uploads`: server-side record of every presigned upload URL issued.

Not part of spec §5.1's entity list (the spec only documents the durable
`users.avatar_key` / `tweet_media.s3_key` outcomes of a confirmed upload),
but required to implement §8.4's "server verifies the object exists" step
safely: without a row *scoped to the requester*, confirming a key would
either trust a client-supplied user id or have no way to reject a key
presigned for (and thus notionally owned by) a different user, and no way to
tell "a key nobody ever presigned" apart from "a key this same user
presigned but never uploaded" for cleanup purposes.

A row is created at presign time (`status=PENDING`) and flipped to
`CONFIRMED` once `MediaService.confirm_*` verifies the object landed in
storage with the declared content-type/size. Rows still `PENDING` after
`media_abandoned_upload_ttl_hours` are abandoned uploads: the client got a
URL but never completed (or never confirmed) the upload, and
`app.workers.media_cleanup` reaps them (best-effort object delete + row
delete) so orphaned bytes don't accumulate in the bucket forever.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field

from app.models.base import UUIDPrimaryKeyMixin, timestamptz_column, utcnow


class MediaPurpose(StrEnum):
    """What a presigned/confirmed object is for. `TweetMedia`'s eventual
    `tweet_id` FK doesn't exist yet at presign/confirm time (no `Tweet` row
    until `TSC-TWEET-001` creates one), so `tweet_image` uploads are tracked
    generically here rather than against a table that can't reference them
    yet.
    """

    AVATAR = "avatar"
    TWEET_IMAGE = "tweet_image"


class PendingUploadStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class PendingUpload(UUIDPrimaryKeyMixin, table=True):
    """One presigned-upload record: who requested it, what for, what was
    declared about it, and whether it has since been confirmed.
    """

    __tablename__ = "pending_uploads"

    user_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    purpose: MediaPurpose = Field(
        sa_column=Column(
            SAEnum(
                MediaPurpose,
                name="media_purpose",
                native_enum=True,
                values_callable=lambda enum_cls: [member.value for member in enum_cls],
            ),
            nullable=False,
        )
    )
    #: Randomized, user-scoped object key (see `app.core.storage.build_object_key`).
    s3_key: str = Field(nullable=False, unique=True, index=True)
    #: What the client declared at presign time — compared against the
    #: object's actual metadata at confirm time to catch "uploaded a
    #: different file than declared" tampering.
    content_type: str = Field(nullable=False)
    size_bytes: int = Field(nullable=False)
    status: PendingUploadStatus = Field(
        sa_column=Column(
            SAEnum(
                PendingUploadStatus,
                name="pending_upload_status",
                native_enum=True,
                values_callable=lambda enum_cls: [member.value for member in enum_cls],
            ),
            nullable=False,
            server_default=PendingUploadStatus.PENDING.value,
        ),
        default=PendingUploadStatus.PENDING,
    )
    #: When the presigned PUT URL itself expires (informational + used by
    #: the readiness/expiry test; cleanup uses `created_at` + the TTL
    #: setting, not this field, since an abandoned upload should be reaped
    #: even if nobody ever probes the URL's expiry).
    presign_expires_at: datetime = Field(sa_column=timestamptz_column())
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamptz_column())
    confirmed_at: datetime | None = Field(default=None, sa_column=timestamptz_column(nullable=True))
