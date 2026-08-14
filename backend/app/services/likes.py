"""Business rules for like/unlike and the transactional counter + new-like
notification side effect (spec §5.1 `likes`, §6.1, §6.3 "Likes").

Idempotency contract (this task's human-review focus, mirroring
`app.services.follows`'s follow/unfollow contract):

- **Like is idempotent**: liking an already-liked tweet leaves exactly one
  `likes` row, a `like_count` that only ever reflects real rows, and creates
  *no* second notification — the first successful like created the
  notification; every repeat call (including a genuine concurrent race,
  handled by `LikeRepository.like`'s `INSERT ... ON CONFLICT DO NOTHING`) is
  a pure no-op beyond recomputing the current state to return.
- **Unlike is idempotent**: unliking a tweet you haven't liked is not an
  error, and never creates or removes a notification (unlike never notifies
  at all, and the original like notification is never retracted).
- **Self-like never notifies**: liking your own tweet inserts the `likes`
  row and bumps `like_count` like any other like, but creates no
  notification — enforced by `NotificationsService.create_notification`'s
  own `recipient_id == actor.id` no-op guard (the same backstop
  `app.services.follows`/`app.services.tweets` rely on for self-follow/
  self-reply), not a separate check here. This is the approved decision
  this task's human review gate covers.
- **Counter update is atomic and commits with the like/unlike + notification
  in one transaction.** `like()`/`unlike()` only ever `flush()` (never an
  early `commit()`), so the like/unlike row, the `tweets.like_count` update
  (via `TweetRepository.increment_like_count`'s relative
  `UPDATE ... SET like_count = GREATEST(0, like_count + delta)`), and the
  notification insert all land together when the request's `AsyncSession`
  commits (`app.core.deps.get_db_session`), or none of them do.
- **The `like_count` returned in the response comes from `COUNT(*)` over
  `likes`** (`LikeRepository.count_for_tweet`), not from re-reading
  `tweet.like_count` off the ORM object already in this request's identity
  map. `increment_like_count` updates that row via a Core-level `UPDATE`,
  which bypasses the ORM's identity map, so the in-memory `Tweet` instance
  this service already holds would otherwise report a stale value for the
  rest of the request — `COUNT(*)` sidesteps that instead of requiring an
  explicit `session.refresh()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.errors import AppError
from app.models.notification import NotificationType
from app.models.tweet import Tweet
from app.models.user import User
from app.repositories.likes import LikeRepository
from app.repositories.tweets import TweetRepository
from app.services.notifications import NotificationsService


class TweetNotFoundError(AppError):
    status_code = 404
    code = "not_found"

    def __init__(self, message: str = "Tweet not found.") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class LikeResult:
    """The like relationship + updated like count after a like/unlike call,
    so the router can render a `LikeRelationship` response without a second
    round trip.
    """

    tweet: Tweet
    liked: bool
    like_count: int


class LikesService:
    def __init__(
        self,
        likes: LikeRepository,
        tweets: TweetRepository,
        notifications: NotificationsService,
    ) -> None:
        self.likes = likes
        self.tweets = tweets
        self.notifications = notifications

    async def like(self, current_user: User, tweet_id: UUID) -> LikeResult:
        """Like `tweet_id`. Idempotent (see module docstring): a repeat
        call — including a concurrent duplicate — leaves exactly one like
        row, one counter increment, and at most one notification, total,
        ever, for that (user, tweet) pair.
        """
        tweet = await self._get_tweet(tweet_id)

        created = await self.likes.like(current_user.id, tweet.id)
        if created:
            await self.tweets.increment_like_count(tweet.id, delta=1)
            await self.notifications.create_notification(
                recipient_id=tweet.author_id,
                actor=current_user,
                type_=NotificationType.LIKE,
                tweet_id=tweet.id,
            )

        like_count = await self.likes.count_for_tweet(tweet.id)
        return LikeResult(tweet=tweet, liked=True, like_count=like_count)

    async def unlike(self, current_user: User, tweet_id: UUID) -> LikeResult:
        """Unlike `tweet_id`. Idempotent: unliking a tweet you haven't
        liked is a no-op, not an error, and never touches a notification.
        """
        tweet = await self._get_tweet(tweet_id)

        deleted = await self.likes.unlike(current_user.id, tweet.id)
        if deleted:
            await self.tweets.increment_like_count(tweet.id, delta=-1)

        like_count = await self.likes.count_for_tweet(tweet.id)
        return LikeResult(tweet=tweet, liked=False, like_count=like_count)

    async def _get_tweet(self, tweet_id: UUID) -> Tweet:
        tweet = await self.tweets.get(tweet_id)
        if tweet is None:
            raise TweetNotFoundError()
        return tweet
