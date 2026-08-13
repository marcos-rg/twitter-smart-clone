"""Additional repository coverage: reply/feed pagination, tweet media,
delete/count, `get_by_token_hash`, and follower/following counts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.refresh_token import RefreshToken
from app.models.tweet import Tweet
from app.models.tweet_media import TweetMedia
from app.models.user import User
from app.repositories.follows import FollowRepository
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.tweet_media import TweetMediaRepository
from app.repositories.tweets import TweetRepository
from app.repositories.users import UserRepository


async def _make_user(session: AsyncSession, username: str) -> User:
    user = User(
        name=username.title(),
        username=username,
        email=f"{username}@example.com",
        password_hash="hash",
    )
    session.add(user)
    await session.flush()
    return user


async def test_list_replies_oldest_first(db_session: AsyncSession) -> None:
    author = await _make_user(db_session, "reply_author")
    replier = await _make_user(db_session, "reply_replier")
    tweets_repo = TweetRepository(db_session)

    parent = Tweet(author_id=author.id, content="parent tweet")
    db_session.add(parent)
    await db_session.flush()

    for i in range(2):
        db_session.add(Tweet(author_id=replier.id, content=f"reply {i}", parent_tweet_id=parent.id))
    await db_session.flush()

    page = await tweets_repo.list_replies(parent.id, cursor=None, limit=10)
    assert [t.content for t in page.items] == ["reply 0", "reply 1"]
    assert page.next_cursor is None


async def test_list_feed_across_multiple_authors(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, "feed_alice")
    bob = await _make_user(db_session, "feed_bob")
    tweets_repo = TweetRepository(db_session)

    db_session.add(Tweet(author_id=alice.id, content="alice tweet"))
    db_session.add(Tweet(author_id=bob.id, content="bob tweet"))
    await db_session.flush()

    page = await tweets_repo.list_feed([alice.id, bob.id], cursor=None, limit=10)
    assert len(page.items) == 2


async def test_tweet_media_listed_in_position_order(db_session: AsyncSession) -> None:
    author = await _make_user(db_session, "media_author")
    tweet = Tweet(author_id=author.id, content="tweet with media")
    db_session.add(tweet)
    await db_session.flush()

    media_repo = TweetMediaRepository(db_session)
    db_session.add(
        TweetMedia(tweet_id=tweet.id, s3_key="b.png", content_type="image/png", position=1)
    )
    db_session.add(
        TweetMedia(tweet_id=tweet.id, s3_key="a.png", content_type="image/png", position=0)
    )
    await db_session.flush()

    media = await media_repo.list_for_tweet(tweet.id)
    assert [m.s3_key for m in media] == ["a.png", "b.png"]


async def test_base_repository_delete_and_count(db_session: AsyncSession) -> None:
    users_repo = UserRepository(db_session)
    user = await users_repo.add(
        User(name="Del", username="deletable", email="deletable@example.com", password_hash="h")
    )
    count_before = await users_repo.count()
    await users_repo.delete(user)
    count_after = await users_repo.count()
    assert count_after == count_before - 1
    assert await users_repo.get(user.id) is None


async def test_refresh_token_get_by_token_hash(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "hash_lookup_user")
    repo = RefreshTokenRepository(db_session)
    await repo.add(
        RefreshToken(
            user_id=user.id,
            token_hash="findable-hash",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    found = await repo.get_by_token_hash("findable-hash")
    assert found is not None
    assert await repo.get_by_token_hash("missing-hash") is None


async def test_follow_counts_followers_and_following(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, "count_alice")
    bob = await _make_user(db_session, "count_bob")
    carol = await _make_user(db_session, "count_carol")
    follows_repo = FollowRepository(db_session)

    await follows_repo.add(follows_repo.model(follower_id=alice.id, followee_id=bob.id))
    await follows_repo.add(follows_repo.model(follower_id=carol.id, followee_id=bob.id))

    assert await follows_repo.count_followers(bob.id) == 2
    assert await follows_repo.count_following(alice.id) == 1
