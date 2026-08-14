"""Business rules for profiles, profile editing, timeline, and user search."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import AppError
from app.models.base import utcnow
from app.models.user import User
from app.repositories.follows import FollowRepository
from app.repositories.pagination import Page
from app.repositories.users import (
    InvalidUserSearchCursorError,
    UserRepository,
    UserSearchCursor,
    decode_user_search_cursor,
)
from app.schemas.users import SearchMode, UserProfileUpdateRequest


class UserNotFoundError(AppError):
    status_code = 404
    code = "not_found"

    def __init__(self, message: str = "User not found.") -> None:
        super().__init__(message)


class UserConflictError(AppError):
    status_code = 409
    code = "conflict"


class InvalidPaginationCursorError(AppError):
    status_code = 400
    code = "validation_error"

    def __init__(self) -> None:
        super().__init__("Invalid pagination cursor.")


@dataclass(frozen=True)
class ProfileView:
    """A profile plus the follow-graph fields (spec §5.1, TSC-SOC-001) the
    `GET /users/{username}` response renders alongside it: `user` itself
    carries none of these (they're not columns on `User`), so the router
    builds `UserPublicProfile` from this rather than `model_validate(user)`.
    """

    user: User
    followers_count: int
    following_count: int
    is_following: bool


class UsersService:
    def __init__(self, users: UserRepository, follows: FollowRepository) -> None:
        self.users = users
        self.follows = follows

    async def get_public_profile(self, username: str) -> User:
        user = await self.users.get_by_username(username)
        if user is None:
            raise UserNotFoundError()
        return user

    async def get_profile_view(self, username: str, viewer: User) -> ProfileView:
        """`get_public_profile` plus follower/following counts and whether
        `viewer` follows this profile. `is_following` is always `False` on
        one's own profile — self-follow is impossible, not merely unusual.
        """
        user = await self.get_public_profile(username)
        followers_count = await self.follows.count_followers(user.id)
        following_count = await self.follows.count_following(user.id)
        is_following = (
            False if viewer.id == user.id else await self.follows.exists(viewer.id, user.id)
        )
        return ProfileView(
            user=user,
            followers_count=followers_count,
            following_count=following_count,
            is_following=is_following,
        )

    async def update_current_user(self, current_user: User, body: UserProfileUpdateRequest) -> User:
        updates = body.model_dump(exclude_unset=True)

        if "username" in updates:
            existing_username_owner = await self.users.get_by_username(updates["username"])
            if (
                existing_username_owner is not None
                and existing_username_owner.id != current_user.id
            ):
                raise UserConflictError("Username is already taken.")

        if "email" in updates:
            existing_email_owner = await self.users.get_by_email(updates["email"])
            if existing_email_owner is not None and existing_email_owner.id != current_user.id:
                raise UserConflictError("Email is already registered.")

        for key, value in updates.items():
            setattr(current_user, key, value)

        current_user.updated_at = utcnow()
        self.users.session.add(current_user)
        await self.users.session.flush()
        return current_user

    async def search_users(
        self, *, query: str, mode: SearchMode, cursor: str | None, limit: int | None
    ) -> Page[User]:
        decoded_cursor = self._decode_search_cursor(cursor)
        if decoded_cursor is not None and decoded_cursor.mode != mode.value:
            raise InvalidPaginationCursorError()

        if mode == SearchMode.exact:
            return await self.users.search_exact(query, cursor=decoded_cursor, limit=limit)
        if mode == SearchMode.prefix:
            return await self.users.search_prefix(query, cursor=decoded_cursor, limit=limit)
        return await self.users.search_fuzzy(query, cursor=decoded_cursor, limit=limit)

    @staticmethod
    def _decode_search_cursor(cursor: str | None) -> UserSearchCursor | None:
        if cursor is None:
            return None
        try:
            return decode_user_search_cursor(cursor)
        except InvalidUserSearchCursorError as exc:
            raise InvalidPaginationCursorError() from exc
