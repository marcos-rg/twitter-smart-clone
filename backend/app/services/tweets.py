"""Business rules for tweet creation/retrieval, flat replies, and profile
timelines (spec §5.1 `tweets`/`tweet_media`, §5.3 counters, §6.3 "Tweets &
feed").

Flat-reply contract (this task's human-review focus, alongside the
whitespace/link contract in `app.schemas.tweets`/`app.services.link_extraction`):

- **Replies can only target root tweets.** `create_tweet` rejects
  `parent_tweet_id` pointing at a tweet that is itself a reply
  (`parent.parent_tweet_id is not None`) with a `422`. This is the
  service-layer enforcement the spec calls for (`app.models.tweet`'s
  docstring: a `CHECK` constraint can't express "does this row's parent have
  a NULL parent" without a subquery).
- **Reply insert + counter increment + notification are one transaction.**
  All three writes go through the same request-scoped `AsyncSession` (no
  early `commit()` anywhere in this service — only `flush()`), so
  `app.core.deps.get_db_session` commits them together, once, at the end of
  the request. `TweetRepository.increment_reply_count` uses a relative SQL
  `UPDATE ... SET reply_count = reply_count + 1` (not a read-modify-write
  through the ORM), which is what keeps concurrent replies to the same
  parent correct: two overlapping transactions each issue their own atomic
  increment: PostgreSQL serializes the two `UPDATE`s (one waits for the
  other's row lock), and both increments land — no lost update, unlike a
  "read count, add one, write count back" pattern would produce under a race.
"""

from __future__ import annotations

from uuid import UUID

from app.core.errors import AppError
from app.models.notification import NotificationType
from app.models.pending_upload import MediaPurpose, PendingUpload, PendingUploadStatus
from app.models.tweet import Tweet
from app.models.tweet_media import TweetMedia
from app.models.user import User
from app.repositories.likes import LikeRepository
from app.repositories.pagination import Cursor, InvalidCursorError, Page, decode_cursor
from app.repositories.pending_uploads import PendingUploadRepository
from app.repositories.tweet_media import TweetMediaRepository
from app.repositories.tweets import TweetRepository
from app.repositories.users import UserRepository
from app.schemas.tweets import LinkEntityOut, TweetAuthor, TweetMediaOut, TweetView
from app.services.link_extraction import extract_link_entities
from app.services.notifications import NotificationsService


class TweetNotFoundError(AppError):
    status_code = 404
    code = "not_found"

    def __init__(self, message: str = "Tweet not found.") -> None:
        super().__init__(message)


class UserNotFoundError(AppError):
    status_code = 404
    code = "not_found"

    def __init__(self, message: str = "User not found.") -> None:
        super().__init__(message)


class CannotReplyToReplyError(AppError):
    """Replies can only target root tweets (spec §5.1: "a reply cannot have
    a reply"). Modeled as `422 semantic_validation_error` — the request is
    well-formed but the operation itself is never valid for this target.
    """

    status_code = 422
    code = "semantic_validation_error"

    def __init__(self) -> None:
        super().__init__("Cannot reply to a reply; replies must target a root tweet.")


class InvalidPaginationCursorError(AppError):
    status_code = 400
    code = "validation_error"

    def __init__(self) -> None:
        super().__init__("Invalid pagination cursor.")


class MediaKeyNotFoundError(AppError):
    status_code = 404
    code = "not_found"

    def __init__(self, key: str) -> None:
        super().__init__(f"No confirmed upload found for key {key!r}.")


class MediaKeyForbiddenError(AppError):
    status_code = 403
    code = "forbidden"

    def __init__(self, key: str) -> None:
        super().__init__(f"Key {key!r} does not belong to the current user.")


class MediaKeyNotConfirmedError(AppError):
    status_code = 400
    code = "validation_error"

    def __init__(self, key: str) -> None:
        super().__init__(f"Key {key!r} has not been confirmed.")


class MediaKeyWrongPurposeError(AppError):
    status_code = 400
    code = "validation_error"

    def __init__(self, key: str) -> None:
        super().__init__(f"Key {key!r} was not uploaded as a tweet image.")


class MediaKeyAlreadyUsedError(AppError):
    """A confirmed upload key can back at most one tweet's `tweet_media`
    row, ever — reusing a key across two `POST /tweets` calls (sequential or
    racing) is rejected rather than silently attaching the same object to
    two tweets.
    """

    status_code = 409
    code = "conflict"

    def __init__(self, key: str) -> None:
        super().__init__(f"Key {key!r} is already attached to another tweet.")


class TweetsService:
    def __init__(
        self,
        tweets: TweetRepository,
        tweet_media: TweetMediaRepository,
        pending_uploads: PendingUploadRepository,
        users: UserRepository,
        likes: LikeRepository,
        notifications: NotificationsService,
    ) -> None:
        self.tweets = tweets
        self.tweet_media = tweet_media
        self.pending_uploads = pending_uploads
        self.users = users
        self.likes = likes
        self.notifications = notifications

    async def create_tweet(
        self,
        current_user: User,
        *,
        content: str,
        parent_tweet_id: UUID | None,
        media_keys: list[str],
    ) -> TweetView:
        """Create a root tweet or (with `parent_tweet_id`) a flat reply.

        `content` is assumed already validated/whitespace-normalized by
        `TweetCreateRequest` (1-280 chars, stripped). `media_keys` are
        re-verified here — ownership, confirmation, purpose, and "not
        already used" are never trusted from the request alone.
        """
        parent: Tweet | None = None
        if parent_tweet_id is not None:
            parent = await self.tweets.get(parent_tweet_id)
            if parent is None:
                raise TweetNotFoundError("The tweet you are replying to was not found.")
            if parent.parent_tweet_id is not None:
                raise CannotReplyToReplyError()

        confirmed_uploads = await self._verify_media_keys(current_user, media_keys)

        tweet = await self.tweets.add(
            Tweet(author_id=current_user.id, content=content, parent_tweet_id=parent_tweet_id)
        )

        media_rows: list[TweetMedia] = []
        for position, pending in enumerate(confirmed_uploads):
            media_rows.append(
                await self.tweet_media.add(
                    TweetMedia(
                        tweet_id=tweet.id,
                        s3_key=pending.s3_key,
                        content_type=pending.content_type,
                        position=position,
                    )
                )
            )

        if parent is not None:
            await self.tweets.increment_reply_count(parent.id)
            await self.notifications.create_notification(
                recipient_id=parent.author_id,
                actor=current_user,
                type_=NotificationType.REPLY,
                tweet_id=parent.id,
            )

        return self._build_view(tweet, author=current_user, media=media_rows, liked_by_viewer=False)

    async def get_tweet(self, tweet_id: UUID, viewer: User) -> TweetView:
        tweet = await self.tweets.get(tweet_id)
        if tweet is None:
            raise TweetNotFoundError()
        page = await self._to_view_page(Page(items=[tweet], next_cursor=None), viewer)
        return page.items[0]

    async def list_replies(
        self, tweet_id: UUID, viewer: User, *, cursor: str | None, limit: int | None
    ) -> Page[TweetView]:
        """Flat replies to `tweet_id`, oldest first. `tweet_id` must exist
        (404 otherwise); it may itself be a reply, in which case the result
        is always empty — a reply can never have replies, so there is
        nothing to list, not an error.
        """
        parent = await self.tweets.get(tweet_id)
        if parent is None:
            raise TweetNotFoundError()
        decoded_cursor = self._decode_cursor(cursor)
        page = await self.tweets.list_replies(tweet_id, cursor=decoded_cursor, limit=limit)
        return await self._to_view_page(page, viewer)

    async def get_user_timeline(
        self, username: str, viewer: User, *, cursor: str | None, limit: int | None
    ) -> Page[TweetView]:
        """`username`'s tweets (including their replies), newest first."""
        author = await self.users.get_by_username(username)
        if author is None:
            raise UserNotFoundError()
        decoded_cursor = self._decode_cursor(cursor)
        page = await self.tweets.list_by_author(author.id, cursor=decoded_cursor, limit=limit)
        return await self._to_view_page(page, viewer)

    # --- media verification --------------------------------------------------

    async def _verify_media_keys(self, user: User, keys: list[str]) -> list[PendingUpload]:
        """Resolve and validate every key in `keys`, in order. Rejects the
        whole batch (no partial attachment) on the first invalid key, so a
        tweet's images are attached atomically, mirroring
        `MediaService.confirm_keys`'s all-or-nothing batch contract.
        """
        if not keys:
            return []
        already_used = await self.tweet_media.list_already_used_keys(keys)
        confirmed: list[PendingUpload] = []
        for key in keys:
            if key in already_used:
                raise MediaKeyAlreadyUsedError(key)
            pending = await self.pending_uploads.get_by_key(key)
            if pending is None:
                raise MediaKeyNotFoundError(key)
            if pending.user_id != user.id:
                raise MediaKeyForbiddenError(key)
            if pending.purpose is not MediaPurpose.TWEET_IMAGE:
                raise MediaKeyWrongPurposeError(key)
            if pending.status is not PendingUploadStatus.CONFIRMED:
                raise MediaKeyNotConfirmedError(key)
            confirmed.append(pending)
        return confirmed

    # --- view assembly --------------------------------------------------------

    async def _to_view_page(self, page: Page[Tweet], viewer: User) -> Page[TweetView]:
        """Batch-resolve authors, media, and the viewer's like state for a
        whole page of tweets in three queries total, regardless of page
        size (rather than one query per row per concern).
        """
        if not page.items:
            return Page(items=[], next_cursor=page.next_cursor)

        tweet_ids = [tweet.id for tweet in page.items]
        author_ids = list({tweet.author_id for tweet in page.items})
        authors_by_id = {user.id: user for user in await self.users.get_many(author_ids)}
        media_by_tweet = await self.tweet_media.list_for_tweets(tweet_ids)
        liked_tweet_ids = await self.likes.list_liked_tweet_ids(viewer.id, tweet_ids)

        items: list[TweetView] = []
        for tweet in page.items:
            author = authors_by_id.get(tweet.author_id)
            if author is None:  # pragma: no cover - defensive; author FK guarantees this
                continue
            items.append(
                self._build_view(
                    tweet,
                    author=author,
                    media=media_by_tweet.get(tweet.id, []),
                    liked_by_viewer=tweet.id in liked_tweet_ids,
                )
            )
        return Page(items=items, next_cursor=page.next_cursor)

    @staticmethod
    def _build_view(
        tweet: Tweet, *, author: User, media: list[TweetMedia], liked_by_viewer: bool
    ) -> TweetView:
        return TweetView(
            id=tweet.id,
            author=TweetAuthor.model_validate(author),
            content=tweet.content,
            parent_tweet_id=tweet.parent_tweet_id,
            like_count=tweet.like_count,
            reply_count=tweet.reply_count,
            liked_by_viewer=liked_by_viewer,
            media=[
                TweetMediaOut(
                    key=item.s3_key, content_type=item.content_type, position=item.position
                )
                for item in media
            ],
            links=[
                LinkEntityOut(url=entity.url, start=entity.start, end=entity.end)
                for entity in extract_link_entities(tweet.content)
            ],
            created_at=tweet.created_at,
        )

    @staticmethod
    def _decode_cursor(cursor: str | None) -> Cursor | None:
        if cursor is None:
            return None
        try:
            return decode_cursor(cursor)
        except InvalidCursorError as exc:
            raise InvalidPaginationCursorError() from exc
