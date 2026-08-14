"""Deterministic `Faker`-backed factories for demo/test data.

Shared by `scripts/seed.py` (demo data for dev/test) and the backend
integration test suite (`tests/repositories/`), so both exercise the exact
same entity-construction logic instead of two subtly different copies.
"""

from __future__ import annotations

from uuid import UUID

from faker import Faker

from app.core.security import hash_password
from app.models.follow import Follow
from app.models.like import Like
from app.models.notification import Notification, NotificationType
from app.models.tweet import Tweet
from app.models.tweet_media import TweetMedia
from app.models.user import User

#: Login password for every demo user the seed script creates (dev/test
#: only — never used outside local, non-production data).
DEMO_PASSWORD = "Password123!"  # noqa: S105 - literal demo credential, not a real secret

BIO_MAX_LENGTH = 160
CONTENT_MAX_LENGTH = 280


def make_faker(seed: int = 20240101) -> Faker:
    """A `Faker` instance seeded for byte-for-byte reproducible demo data:
    running the seed script twice generates the exact same names/bios/tweet
    text both times (the *idempotency* still comes from each entity being
    looked up by a natural key before insert — this just makes the
    generated *content* deterministic too, so diffs/reviews are stable).
    """
    Faker.seed(seed)
    faker = Faker()
    faker.seed_instance(seed)
    return faker


def build_user(
    faker: Faker,
    *,
    username: str,
    name: str | None = None,
    email: str | None = None,
    bio: str | None = None,
) -> User:
    """A `User` with a real, verifiable Argon2id password hash for
    `DEMO_PASSWORD` (spec §5.1: `password_hash` is an Argon2id hash).
    """
    return User(
        name=(name or faker.name())[:50],
        username=username,
        email=email or f"{username}@example.com",
        password_hash=hash_password(DEMO_PASSWORD),
        bio=(bio if bio is not None else faker.sentence(nb_words=8))[:BIO_MAX_LENGTH],
    )


def build_tweet(
    faker: Faker,
    *,
    author_id: UUID,
    parent_tweet_id: UUID | None = None,
    content: str | None = None,
) -> Tweet:
    """A `Tweet`, or (with `parent_tweet_id`) a flat reply to one."""
    return Tweet(
        author_id=author_id,
        content=(content or faker.sentence(nb_words=12))[:CONTENT_MAX_LENGTH],
        parent_tweet_id=parent_tweet_id,
    )


def build_tweet_media(
    *, tweet_id: UUID, position: int, content_type: str = "image/png"
) -> TweetMedia:
    return TweetMedia(
        tweet_id=tweet_id,
        s3_key=f"demo/{tweet_id}/{position}.png",
        content_type=content_type,
        position=position,
    )


def build_follow(follower_id: UUID, followee_id: UUID) -> Follow:
    return Follow(follower_id=follower_id, followee_id=followee_id)


def build_like(user_id: UUID, tweet_id: UUID) -> Like:
    return Like(user_id=user_id, tweet_id=tweet_id)


def build_notification(
    *,
    recipient_id: UUID,
    actor_id: UUID,
    type: NotificationType,
    tweet_id: UUID | None = None,
) -> Notification:
    return Notification(recipient_id=recipient_id, actor_id=actor_id, type=type, tweet_id=tweet_id)
