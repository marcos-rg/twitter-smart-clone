"""Idempotent demo-data seed script (spec §12.4: "Seed script (`make seed` /
CLI) populates demo users, tweets, follows, likes for dev/test").

Usage: `uv run python -m scripts.seed` (what `make seed` runs inside the
backend container). Safe to run any number of times: every entity is looked
up by a stable natural key (username; a specific follow/like edge; a
reply's `(parent_tweet_id, author_id)`; an author's top-level tweet count)
before insert, so re-running never duplicates rows and never fails on a
uniqueness/check constraint.
"""

from __future__ import annotations

import asyncio
import logging

from faker import Faker
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.models.notification import NotificationType
from app.models.tweet import Tweet
from app.models.user import User
from app.repositories.follows import FollowRepository
from app.repositories.likes import LikeRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.tweets import TweetRepository
from app.repositories.users import UserRepository
from scripts.factories import (
    build_follow,
    build_notification,
    build_tweet,
    build_user,
    make_faker,
)

logger = logging.getLogger("scripts.seed")

#: Demo accounts. All log in with `scripts.factories.DEMO_PASSWORD`.
DEMO_USERNAMES = [
    "ada",
    "grace",
    "linus",
    "margaret",
    "alan",
    "barbara",
    "dennis",
    "radia",
]

#: Each user posts this many top-level demo tweets.
TWEETS_PER_USER = 3
#: Each user follows the next `FOLLOW_FANOUT` users in the list (cyclic),
#: so the graph has mutual follows and a realistic feed/notification spread.
FOLLOW_FANOUT = 2


async def _seed_users(faker: Faker, users_repo: UserRepository) -> tuple[dict[str, User], int]:
    users: dict[str, User] = {}
    created = 0
    for username in DEMO_USERNAMES:
        existing = await users_repo.get_by_username(username)
        if existing is not None:
            users[username] = existing
            continue
        users[username] = await users_repo.add(build_user(faker, username=username))
        created += 1
    return users, created


async def _seed_follows(
    users: dict[str, User],
    follows_repo: FollowRepository,
    notifications_repo: NotificationRepository,
) -> tuple[int, int]:
    follows_created = 0
    notifications_created = 0
    n = len(DEMO_USERNAMES)
    for i, username in enumerate(DEMO_USERNAMES):
        follower = users[username]
        for offset in range(1, FOLLOW_FANOUT + 1):
            followee = users[DEMO_USERNAMES[(i + offset) % n]]
            if await follows_repo.exists(follower.id, followee.id):
                continue
            await follows_repo.add(build_follow(follower.id, followee.id))
            follows_created += 1
            if not await notifications_repo.exists(
                recipient_id=followee.id,
                actor_id=follower.id,
                type=NotificationType.FOLLOW,
                tweet_id=None,
            ):
                await notifications_repo.add(
                    build_notification(
                        recipient_id=followee.id,
                        actor_id=follower.id,
                        type=NotificationType.FOLLOW,
                    )
                )
                notifications_created += 1
    return follows_created, notifications_created


async def _seed_tweets_replies_and_likes(
    faker: Faker,
    users: dict[str, User],
    tweets_repo: TweetRepository,
    likes_repo: LikeRepository,
    notifications_repo: NotificationRepository,
) -> dict[str, int]:
    counts = {
        "tweets_created": 0,
        "replies_created": 0,
        "likes_created": 0,
        "notifications_created": 0,
    }
    n = len(DEMO_USERNAMES)

    top_level_by_author: dict[str, list[Tweet]] = {}
    for username in DEMO_USERNAMES:
        author = users[username]
        existing_count = await tweets_repo.count_top_level_by_author(author.id)
        tweets_for_author: list[Tweet] = []
        for _ in range(existing_count, TWEETS_PER_USER):
            tweet = await tweets_repo.add(build_tweet(faker, author_id=author.id))
            tweets_for_author.append(tweet)
            counts["tweets_created"] += 1
        top_level_by_author[username] = tweets_for_author

    # One reply per newly created top-level tweet, from the next user in the
    # cycle, plus a like from the user after that.
    for i, username in enumerate(DEMO_USERNAMES):
        replier = users[DEMO_USERNAMES[(i + 1) % n]]
        liker = users[DEMO_USERNAMES[(i + 2) % n]]
        for tweet in top_level_by_author[username]:
            existing_reply = await tweets_repo.get_reply_by_author(tweet.id, replier.id)
            if existing_reply is None:
                await tweets_repo.add(
                    build_tweet(faker, author_id=replier.id, parent_tweet_id=tweet.id)
                )
                await tweets_repo.increment_reply_count(tweet.id)
                counts["replies_created"] += 1
                if not await notifications_repo.exists(
                    recipient_id=tweet.author_id,
                    actor_id=replier.id,
                    type=NotificationType.REPLY,
                    tweet_id=tweet.id,
                ):
                    await notifications_repo.add(
                        build_notification(
                            recipient_id=tweet.author_id,
                            actor_id=replier.id,
                            type=NotificationType.REPLY,
                            tweet_id=tweet.id,
                        )
                    )
                    counts["notifications_created"] += 1

            if not await likes_repo.exists(liker.id, tweet.id):
                inserted = await likes_repo.like(liker.id, tweet.id)
                if inserted:
                    await tweets_repo.increment_like_count(tweet.id)
                    counts["likes_created"] += 1
                    if not await notifications_repo.exists(
                        recipient_id=tweet.author_id,
                        actor_id=liker.id,
                        type=NotificationType.LIKE,
                        tweet_id=tweet.id,
                    ):
                        await notifications_repo.add(
                            build_notification(
                                recipient_id=tweet.author_id,
                                actor_id=liker.id,
                                type=NotificationType.LIKE,
                                tweet_id=tweet.id,
                            )
                        )
                        counts["notifications_created"] += 1

    return counts


async def seed(session: AsyncSession) -> dict[str, int]:
    """Populate demo data against `session`, returning per-entity counts of
    rows actually created (0 on a fully-idempotent re-run).
    """
    faker = make_faker()
    users_repo = UserRepository(session)
    follows_repo = FollowRepository(session)
    likes_repo = LikeRepository(session)
    notifications_repo = NotificationRepository(session)
    tweets_repo = TweetRepository(session)

    users, users_created = await _seed_users(faker, users_repo)
    follows_created, follow_notifications = await _seed_follows(
        users, follows_repo, notifications_repo
    )
    tweet_counts = await _seed_tweets_replies_and_likes(
        faker, users, tweets_repo, likes_repo, notifications_repo
    )

    await session.commit()

    return {
        "users_created": users_created,
        "follows_created": follows_created,
        "tweets_created": tweet_counts["tweets_created"],
        "replies_created": tweet_counts["replies_created"],
        "likes_created": tweet_counts["likes_created"],
        "notifications_created": follow_notifications + tweet_counts["notifications_created"],
    }


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        counts = await seed(session)
    await engine.dispose()
    logger.info("Seed complete: %s", counts)


if __name__ == "__main__":
    asyncio.run(main())
