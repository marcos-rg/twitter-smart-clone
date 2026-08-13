"""Database-level invariants (spec's AI-verifiable acceptance criteria):
duplicate usernames/emails, self-follows, duplicate follows/likes, and
other constraints assigned to the database are rejected by PostgreSQL
itself, not merely by application code.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.follow import Follow
from app.models.like import Like
from app.models.tweet import Tweet
from app.models.user import User
from app.repositories.users import UserRepository


async def _make_user(session: AsyncSession, *, username: str, email: str) -> User:
    user = User(
        name="Test User",
        username=username,
        email=email,
        password_hash="not-a-real-hash",
    )
    session.add(user)
    await session.flush()
    return user


async def test_duplicate_username_different_case_is_rejected(db_session: AsyncSession) -> None:
    await _make_user(db_session, username="alice", email="alice@example.com")
    with pytest.raises(IntegrityError):
        await _make_user(db_session, username="ALICE", email="alice2@example.com")


async def test_duplicate_email_different_case_is_rejected(db_session: AsyncSession) -> None:
    await _make_user(db_session, username="bob", email="bob@example.com")
    with pytest.raises(IntegrityError):
        await _make_user(db_session, username="bob2", email="BOB@EXAMPLE.COM")


async def test_username_lookup_is_case_insensitive(db_session: AsyncSession) -> None:
    await _make_user(db_session, username="carol", email="carol@example.com")
    await db_session.commit()
    repo = UserRepository(db_session)
    assert await repo.get_by_username("CAROL") is not None
    assert await repo.get_by_email("CAROL@EXAMPLE.COM") is not None


async def test_self_follow_is_rejected(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, username="dave", email="dave@example.com")
    await db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.add(Follow(follower_id=user.id, followee_id=user.id))
        await db_session.flush()


async def test_duplicate_follow_is_rejected(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, username="erin", email="erin@example.com")
    bob = await _make_user(db_session, username="frank", email="frank@example.com")
    await db_session.flush()
    db_session.add(Follow(follower_id=alice.id, followee_id=bob.id))
    await db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.add(Follow(follower_id=alice.id, followee_id=bob.id))
        await db_session.flush()


async def test_duplicate_like_is_rejected(db_session: AsyncSession) -> None:
    author = await _make_user(db_session, username="grace", email="grace@example.com")
    liker = await _make_user(db_session, username="henry", email="henry@example.com")
    await db_session.flush()
    tweet = Tweet(author_id=author.id, content="hello world")
    db_session.add(tweet)
    await db_session.flush()
    db_session.add(Like(user_id=liker.id, tweet_id=tweet.id))
    await db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.add(Like(user_id=liker.id, tweet_id=tweet.id))
        await db_session.flush()


async def test_tweet_requires_existing_author(db_session: AsyncSession) -> None:
    db_session.add(Tweet(author_id=uuid4(), content="orphan tweet"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
