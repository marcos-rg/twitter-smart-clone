"""Schemas for `/media/*` and `/users/me/avatar` upload endpoints (spec
§8.4: media upload flow).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.pending_upload import MediaPurpose
from app.models.tweet_media import ALLOWED_CONTENT_TYPES


class PresignFileRequest(BaseModel):
    """One file the client wants to upload. `content_type` and
    `size_bytes` are the client's *declaration*, checked against limits now
    and against the actual uploaded object's metadata at confirm time.
    """

    content_type: str = Field(examples=list(ALLOWED_CONTENT_TYPES))
    size_bytes: int = Field(gt=0, examples=[204_800])


class PresignRequest(BaseModel):
    """A batch presign request. `purpose=avatar` must contain exactly one
    file (a profile has one avatar); `purpose=tweet_image` may contain up to
    `Settings.media_max_tweet_images` (spec §8.4: "max 4 images/tweet") —
    there's no `Tweet` row yet to attach to, so the whole batch a client
    intends for one tweet is presigned together and the count limit is
    enforced here, at the media layer (see TSC-MEDIA-001's task notes).
    """

    purpose: MediaPurpose
    files: list[PresignFileRequest] = Field(min_length=1)


class PresignedUpload(BaseModel):
    key: str
    upload_url: str
    content_type: str
    expires_at: datetime


class PresignResponse(BaseModel):
    uploads: list[PresignedUpload]


class ConfirmRequest(BaseModel):
    """Confirm one or more previously presigned keys (spec §8.4 step 4:
    "Client confirms by sending the `s3_key`(s)"). All keys must share the
    same `purpose` and belong to the caller.
    """

    purpose: MediaPurpose
    keys: list[str] = Field(min_length=1)


class ConfirmedMedia(BaseModel):
    key: str
    content_type: str
    size_bytes: int


class ConfirmResponse(BaseModel):
    media: list[ConfirmedMedia]


class AvatarConfirmRequest(BaseModel):
    key: str
