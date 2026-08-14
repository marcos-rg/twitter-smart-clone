"""Business rules for profiles, profile editing, timeline, and user search."""

from __future__ import annotations

from app.core.errors import AppError
from app.models.base import utcnow
from app.models.tweet import Tweet
from app.models.user import User
from app.repositories.pagination import Cursor, InvalidCursorError, Page, decode_cursor
from app.repositories.tweets import TweetRepository
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


class UsersService:
    def __init__(self, users: UserRepository, tweets: TweetRepository) -> None:
        self.users = users
        self.tweets = tweets

    async def get_public_profile(self, username: str) -> User:
        user = await self.users.get_by_username(username)
        if user is None:
            raise UserNotFoundError()
        return user

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

    async def get_timeline(
        self, *, username: str, cursor: str | None, limit: int | None
    ) -> Page[Tweet]:
        user = await self.get_public_profile(username)
        decoded_cursor = self._decode_timeline_cursor(cursor)
        return await self.tweets.list_by_author(user.id, cursor=decoded_cursor, limit=limit)

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
    def _decode_timeline_cursor(cursor: str | None) -> Cursor | None:
        if cursor is None:
            return None
        try:
            return decode_cursor(cursor)
        except InvalidCursorError as exc:
            raise InvalidPaginationCursorError() from exc

    @staticmethod
    def _decode_search_cursor(cursor: str | None) -> UserSearchCursor | None:
        if cursor is None:
            return None
        try:
            return decode_user_search_cursor(cursor)
        except InvalidUserSearchCursorError as exc:
            raise InvalidPaginationCursorError() from exc
