"""The seed script is idempotent (spec: "Seed runs twice without
duplication or failure and creates useful demo relationships").
"""

from __future__ import annotations

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.follow import Follow
from app.models.notification import Notification
from app.models.tweet import Tweet
from app.models.user import User
from scripts.seed import DEMO_USERNAMES, TWEETS_PER_USER, seed


async def _count(session: AsyncSession, model: type) -> int:
    result = await session.exec(select(func.count()).select_from(model))
    return int(result.one())


async def test_seed_is_idempotent_and_creates_demo_relationships(
    db_session: AsyncSession,
) -> None:
    first_run_counts = await seed(db_session)

    assert first_run_counts["users_created"] == len(DEMO_USERNAMES)
    assert first_run_counts["follows_created"] > 0
    assert first_run_counts["tweets_created"] == len(DEMO_USERNAMES) * TWEETS_PER_USER
    assert first_run_counts["likes_created"] > 0
    assert first_run_counts["notifications_created"] > 0

    users_after_first_run = await _count(db_session, User)
    tweets_after_first_run = await _count(db_session, Tweet)
    follows_after_first_run = await _count(db_session, Follow)
    notifications_after_first_run = await _count(db_session, Notification)

    second_run_counts = await seed(db_session)
    assert second_run_counts == {
        "users_created": 0,
        "follows_created": 0,
        "tweets_created": 0,
        "replies_created": 0,
        "likes_created": 0,
        "notifications_created": 0,
    }

    assert await _count(db_session, User) == users_after_first_run
    assert await _count(db_session, Tweet) == tweets_after_first_run
    assert await _count(db_session, Follow) == follows_after_first_run
    assert await _count(db_session, Notification) == notifications_after_first_run
