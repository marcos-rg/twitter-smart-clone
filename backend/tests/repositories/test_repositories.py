"""Repository behavior: pagination, idempotent like/follow, notification
unread counting, refresh-token rotation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import NotificationType
from app.models.refresh_token import RefreshToken
from app.models.tweet import Tweet
from app.models.user import User
from app.repositories.follows import FollowRepository
from app.repositories.likes import LikeRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.pagination import decode_cursor
from app.repositories.refresh_tokens import RefreshTokenRepository
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


async def test_tweet_pagination_returns_pages_newest_first(db_session: AsyncSession) -> None:
    author = await _make_user(db_session, "paginator")
    tweets_repo = TweetRepository(db_session)
    for i in range(5):
        db_session.add(
            Tweet(
                author_id=author.id,
                content=f"tweet {i}",
                created_at=datetime.now(UTC) + timedelta(seconds=i),
            )
        )
    await db_session.flush()

    page_1 = await tweets_repo.list_by_author(author.id, cursor=None, limit=2)
    assert [t.content for t in page_1.items] == ["tweet 4", "tweet 3"]
    assert page_1.next_cursor is not None

    cursor = decode_cursor(page_1.next_cursor)
    page_2 = await tweets_repo.list_by_author(author.id, cursor=cursor, limit=2)
    assert [t.content for t in page_2.items] == ["tweet 2", "tweet 1"]
    assert page_2.next_cursor is not None

    cursor = decode_cursor(page_2.next_cursor)
    page_3 = await tweets_repo.list_by_author(author.id, cursor=cursor, limit=2)
    assert [t.content for t in page_3.items] == ["tweet 0"]
    assert page_3.next_cursor is None


async def test_like_is_idempotent(db_session: AsyncSession) -> None:
    author = await _make_user(db_session, "liked_author")
    liker = await _make_user(db_session, "liker")
    tweet = Tweet(author_id=author.id, content="like me")
    db_session.add(tweet)
    await db_session.flush()

    likes_repo = LikeRepository(db_session)
    assert await likes_repo.like(liker.id, tweet.id) is True
    assert await likes_repo.like(liker.id, tweet.id) is False
    assert await likes_repo.count_for_tweet(tweet.id) == 1


async def test_follow_unfollow_is_idempotent(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, "follow_alice")
    bob = await _make_user(db_session, "follow_bob")
    follows_repo = FollowRepository(db_session)

    assert not await follows_repo.exists(alice.id, bob.id)
    await follows_repo.add(follows_repo.model(follower_id=alice.id, followee_id=bob.id))
    assert await follows_repo.exists(alice.id, bob.id)
    assert await follows_repo.count_followers(bob.id) == 1

    assert await follows_repo.unfollow(alice.id, bob.id) is True
    assert await follows_repo.unfollow(alice.id, bob.id) is False
    assert not await follows_repo.exists(alice.id, bob.id)


async def test_notification_unread_count_and_mark_all_read(db_session: AsyncSession) -> None:
    recipient = await _make_user(db_session, "notif_recipient")
    actor = await _make_user(db_session, "notif_actor")
    notifications_repo = NotificationRepository(db_session)

    for _ in range(3):
        await notifications_repo.add(
            notifications_repo.model(
                recipient_id=recipient.id, actor_id=actor.id, type=NotificationType.FOLLOW
            )
        )

    assert await notifications_repo.count_unread(recipient.id) == 3
    marked = await notifications_repo.mark_all_read(recipient.id)
    assert marked == 3
    assert await notifications_repo.count_unread(recipient.id) == 0

    # Idempotent: a second call matches nothing already-read, so it's a no-op.
    assert await notifications_repo.mark_all_read(recipient.id) == 0
    assert await notifications_repo.count_unread(recipient.id) == 0


async def test_notification_mark_selected_read_is_scoped_and_idempotent(
    db_session: AsyncSession,
) -> None:
    recipient = await _make_user(db_session, "notif_selected_recipient")
    other_recipient = await _make_user(db_session, "notif_selected_other")
    actor = await _make_user(db_session, "notif_selected_actor")
    notifications_repo = NotificationRepository(db_session)

    mine_1 = await notifications_repo.add(
        notifications_repo.model(
            recipient_id=recipient.id, actor_id=actor.id, type=NotificationType.LIKE
        )
    )
    mine_2 = await notifications_repo.add(
        notifications_repo.model(
            recipient_id=recipient.id, actor_id=actor.id, type=NotificationType.REPLY
        )
    )
    someone_elses = await notifications_repo.add(
        notifications_repo.model(
            recipient_id=other_recipient.id, actor_id=actor.id, type=NotificationType.FOLLOW
        )
    )

    # Marking a mix of "mine" + "someone else's" id only affects mine.
    marked = await notifications_repo.mark_selected_read(
        recipient.id, [mine_1.id, someone_elses.id]
    )
    assert marked == 1
    assert await notifications_repo.count_unread(recipient.id) == 1  # mine_2 still unread
    assert await notifications_repo.count_unread(other_recipient.id) == 1  # untouched

    # Idempotent: marking the same id again matches nothing new.
    assert await notifications_repo.mark_selected_read(recipient.id, [mine_1.id]) == 0

    # Empty id list is a no-op, not an error.
    assert await notifications_repo.mark_selected_read(recipient.id, []) == 0

    marked_remaining = await notifications_repo.mark_selected_read(recipient.id, [mine_2.id])
    assert marked_remaining == 1
    assert await notifications_repo.count_unread(recipient.id) == 0


async def test_refresh_token_rotation_and_revocation(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "token_user")
    repo = RefreshTokenRepository(db_session)

    token = await repo.add(
        RefreshToken(
            user_id=user.id,
            token_hash="hash-1",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    assert repo.is_active(token) is True

    await repo.revoke(token)
    assert repo.is_active(token) is False

    other = await repo.add(
        RefreshToken(
            user_id=user.id,
            token_hash="hash-2",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    await repo.revoke_all_for_user(user.id)
    refreshed = await repo.get(other.id)
    assert refreshed is not None
    assert repo.is_active(refreshed) is False


async def test_user_search_by_username_or_name(db_session: AsyncSession) -> None:
    await _make_user(db_session, "searchable_ada")
    users_repo = UserRepository(db_session)
    results = await users_repo.search_by_name_or_username("searchable")
    assert any(u.username == "searchable_ada" for u in results)
