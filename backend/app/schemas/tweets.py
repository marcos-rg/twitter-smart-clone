"""Schemas for `POST /tweets`, `GET /tweets/{id}`, `GET /tweets/{id}/replies`,
and `GET /users/{username}/tweets` (spec §6.3 "Tweets & feed").

`TweetView` is the single response shape all four endpoints render — create,
get, replies, and profile-timeline all return the same fields (author,
viewer state, counts, ordered media, safe link data), per this task's
acceptance criteria. Building one shared shape (rather than a leaner
timeline-only DTO) means a client never has to special-case which endpoint a
tweet came from.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.tweet import CONTENT_MAX_LENGTH
from app.models.tweet_media import MAX_POSITION

#: At most `MAX_POSITION + 1` (4) images per tweet (spec §5.1 `tweet_media`:
#: "position int (0..3)").
MAX_TWEET_IMAGES = MAX_POSITION + 1

#: Sanity cap on the *raw* (pre-strip) request body, well above the 280
#: authoritative limit, so a client can't send an arbitrarily large payload
#: just to have it rejected after allocation. The real 1-280 rule is
#: enforced in `_validate_content` below, on the *stripped* content.
_RAW_CONTENT_SAFETY_CAP = 2000


class LinkEntityOut(BaseModel):
    """One `(url, start, end)` span in `content` — see
    `app.services.link_extraction` for the safety contract this implements.
    """

    url: str
    start: int
    end: int


class TweetAuthor(BaseModel):
    """The author summary embedded in every `TweetView` — enough to render a
    tweet card without a follow-up profile fetch, matching
    `NotificationActor`'s shape.
    """

    id: UUID
    username: str
    name: str
    avatar_key: str | None = None

    model_config = {"from_attributes": True}


class TweetMediaOut(BaseModel):
    """One ordered image attachment."""

    key: str
    content_type: str
    position: int


class TweetView(BaseModel):
    """The canonical tweet representation returned by every tweet-reading
    endpoint (create/get/replies/timeline).
    """

    id: UUID
    author: TweetAuthor
    content: str
    parent_tweet_id: UUID | None
    like_count: int
    reply_count: int
    #: Whether the *authenticated caller* has liked this tweet — resolved
    #: per-request from `likes` (never client-supplied), so it can't be
    #: spoofed by a request body field.
    liked_by_viewer: bool
    media: list[TweetMediaOut]
    links: list[LinkEntityOut]
    created_at: datetime


class TweetCreateRequest(BaseModel):
    """Body of `POST /tweets`. `parent_tweet_id` present ⇒ this is a flat
    reply (spec: "flat replies to one"); omitted/`null` ⇒ a root tweet.
    """

    content: str = Field(min_length=1, max_length=_RAW_CONTENT_SAFETY_CAP)
    parent_tweet_id: UUID | None = Field(default=None)
    #: Keys of previously confirmed uploads (`POST /media/confirm`,
    #: `purpose: "tweet_image"`), in display order. Ownership, confirmation
    #: status, and "not already attached to another tweet" are all
    #: re-verified server-side in `TweetsService` — never trusted from the
    #: request alone.
    media_keys: list[str] = Field(default_factory=list, max_length=MAX_TWEET_IMAGES)

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: str) -> str:
        """The approved whitespace policy (this task's human-review focus):

        - Leading/trailing whitespace (spaces, tabs, newlines) is stripped
          before length validation and storage — a tweet's displayed length
          never counts padding the author didn't mean to be content.
        - The stripped content must contain at least one non-whitespace
          character: a blank or whitespace-only tweet is rejected, not
          silently stored as an empty/space-only row.
        - Internal whitespace (including newlines) is preserved exactly as
          typed — multi-line tweets are allowed, and no run of whitespace is
          collapsed.
        - The 1-280 character limit applies to the *stripped* content,
          measured in Unicode code points (`len(str)`), consistent with how
          `bio`/`username` are measured elsewhere in this codebase.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be blank.")
        if len(stripped) > CONTENT_MAX_LENGTH:
            raise ValueError(f"content must be at most {CONTENT_MAX_LENGTH} characters.")
        return stripped

    @model_validator(mode="after")
    def _validate_media_keys(self) -> TweetCreateRequest:
        if len(self.media_keys) != len(set(self.media_keys)):
            raise ValueError("media_keys must not contain duplicates.")
        return self


class TweetListPage(BaseModel):
    next_cursor: str | None


class TweetListResponse(BaseModel):
    data: list[TweetView]
    page: TweetListPage
