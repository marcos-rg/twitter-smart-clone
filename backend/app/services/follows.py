"""Business rules for follow/unfollow, follower/following lists, and the
transactional follow-notification side effect (spec §5.1 `follows`, §6.1,
§6.3 "Follows").

Idempotency contract (this task's human-review focus):

- **Follow** is idempotent: following an already-followed user leaves
  exactly one `follows` row and creates *no* second notification — the
  first successful follow created the notification; every repeat call
  (including a genuine concurrent race, handled by
  `FollowRepository.follow`'s `SAVEPOINT`) is a pure no-op beyond
  recomputing the current state to return.
- **Unfollow** is idempotent: unfollowing a user you don't follow is not an
  error, and never creates a notification (unfollow never notifies at all).
- **Self-follow is impossible**, not merely rejected: the check is
  `current_user.id == target.id`, which is never a race (it depends only on
  the caller's own id), so it's rejected deterministically before any
  database write, and `NotificationsService.create_notification`'s own
  `recipient_id == actor.id` guard is a second, independent backstop.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.core.errors import AppError
from app.models.follow import Follow
from app.models.notification import NotificationType
from app.models.user import User
from app.repositories.follows import FollowRepository
from app.repositories.pagination import Cursor, InvalidCursorError, Page, decode_cursor
from app.repositories.users import UserRepository
from app.services.notifications import NotificationsService


class UserNotFoundError(AppError):
    status_code = 404
    code = "not_found"

    def __init__(self, message: str = "User not found.") -> None:
        super().__init__(message)


class CannotFollowSelfError(AppError):
    """Raised by both `follow()` and `unfollow()` for `username == self` —
    a `422`, matching the spec's "semantic validation" bucket (the request
    is well-formed but not a valid operation), not a `400` malformed
    request or a `409` conflict (there is no conflicting resource: the
    operation itself is never valid, regardless of state).
    """

    status_code = 422
    code = "semantic_validation_error"

    def __init__(self) -> None:
        super().__init__("You cannot follow yourself.")


class InvalidPaginationCursorError(AppError):
    status_code = 400
    code = "validation_error"

    def __init__(self) -> None:
        super().__init__("Invalid pagination cursor.")


@dataclass(frozen=True)
class FollowResult:
    """The relationship + updated follower count after a follow/unfollow
    call, so the router can render a `FollowRelationship` response without
    a second round trip.
    """

    target: User
    is_following: bool
    followers_count: int


class FollowsService:
    def __init__(
        self,
        follows: FollowRepository,
        users: UserRepository,
        notifications: NotificationsService,
    ) -> None:
        self.follows = follows
        self.users = users
        self.notifications = notifications

    async def follow(self, current_user: User, username: str) -> FollowResult:
        """Follow `username`. Idempotent (see module docstring): a repeat
        call — including a concurrent duplicate — leaves exactly one follow
        edge and creates at most one notification, total, ever, for that
        edge.
        """
        target = await self._get_target(username, current_user)

        created = await self.follows.follow(current_user.id, target.id)
        if created:
            await self.notifications.create_notification(
                recipient_id=target.id,
                actor=current_user,
                type_=NotificationType.FOLLOW,
                tweet_id=None,
            )

        followers_count = await self.follows.count_followers(target.id)
        return FollowResult(target=target, is_following=True, followers_count=followers_count)

    async def unfollow(self, current_user: User, username: str) -> FollowResult:
        """Unfollow `username`. Idempotent: unfollowing when not following
        is a no-op, not an error, and never creates a notification.
        """
        target = await self._get_target(username, current_user)

        await self.follows.unfollow(current_user.id, target.id)
        followers_count = await self.follows.count_followers(target.id)
        return FollowResult(target=target, is_following=False, followers_count=followers_count)

    async def list_followers(
        self, username: str, *, cursor: str | None, limit: int | None
    ) -> Page[User]:
        """`username`'s followers, newest follow first, cursor-paginated
        and free of duplicates across pages (keyset pagination on the
        immutable `(created_at, follower_id)` pair — see
        `app.repositories.pagination`).
        """
        target = await self._get_target_for_read(username)
        decoded_cursor = self._decode_cursor(cursor)
        page = await self.follows.list_followers(target.id, cursor=decoded_cursor, limit=limit)
        return await self._resolve_users(page, id_of=lambda f: f.follower_id)

    async def list_following(
        self, username: str, *, cursor: str | None, limit: int | None
    ) -> Page[User]:
        """Users `username` follows, newest follow first, cursor-paginated
        and free of duplicates across pages.
        """
        target = await self._get_target_for_read(username)
        decoded_cursor = self._decode_cursor(cursor)
        page = await self.follows.list_following(target.id, cursor=decoded_cursor, limit=limit)
        return await self._resolve_users(page, id_of=lambda f: f.followee_id)

    async def _get_target_for_read(self, username: str) -> User:
        user = await self.users.get_by_username(username)
        if user is None:
            raise UserNotFoundError()
        return user

    async def _get_target(self, username: str, current_user: User) -> User:
        """Resolve `username` for a follow/unfollow call: `404` if it
        doesn't exist, `422` if it's the caller's own username.
        """
        target = await self._get_target_for_read(username)
        if target.id == current_user.id:
            raise CannotFollowSelfError()
        return target

    async def _resolve_users(
        self, page: Page[Follow], *, id_of: Callable[[Follow], UUID]
    ) -> Page[User]:
        """Batch-resolve a page of `Follow` edges into the `User` rows they
        reference, preserving page order (mirrors
        `NotificationsService.list_for_recipient`'s actor resolution).
        """
        if not page.items:
            return Page(items=[], next_cursor=page.next_cursor)
        ordered_ids = [id_of(edge) for edge in page.items]
        users_by_id = {user.id: user for user in await self.users.get_many(ordered_ids)}
        items = [users_by_id[user_id] for user_id in ordered_ids if user_id in users_by_id]
        return Page(items=items, next_cursor=page.next_cursor)

    @staticmethod
    def _decode_cursor(cursor: str | None) -> Cursor | None:
        if cursor is None:
            return None
        try:
            return decode_cursor(cursor)
        except InvalidCursorError as exc:
            raise InvalidPaginationCursorError() from exc
