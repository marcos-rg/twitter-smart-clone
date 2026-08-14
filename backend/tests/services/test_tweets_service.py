"""Integration tests for `TweetsService` against a real PostgreSQL session
and a real Redis pub/sub channel (spec §5.1, §5.3, §6.3 "Tweets & feed").
Mirrors `tests/services/test_follows_service.py`'s commit/rollback lifecycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest_asyncio
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.core.outbox import run_post_commit_callbacks
from app.models.pending_upload import MediaPurpose, PendingUpload, PendingUploadStatus
from app.models.tweet import Tweet
from app.models.user import User
from app.repositories.likes import LikeRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.pending_uploads import PendingUploadRepository
from app.repositories.tweet_media import TweetMediaRepository
from app.repositories.tweets import TweetRepository
from app.repositories.users import UserRepository
from app.services.notifications import NotificationsService
from app.services.tweets import (
    CannotReplyToReplyError,
    InvalidPaginationCursorError,
    MediaKeyAlreadyUsedError,
    MediaKeyForbiddenError,
    MediaKeyNotConfirmedError,
    MediaKeyNotFoundError,
    MediaKeyWrongPurposeError,
    TweetNotFoundError,
    TweetsService,
    UserNotFoundError,
)


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


async def _make_confirmed_upload(
    session: AsyncSession, *, user_id: UUID, content_type: str = "image/png"
) -> PendingUpload:
    upload = PendingUpload(
        user_id=user_id,
        purpose=MediaPurpose.TWEET_IMAGE,
        s3_key=f"tweet_image/{user_id}/{uuid4().hex}.png",
        content_type=content_type,
        size_bytes=1024,
        status=PendingUploadStatus.CONFIRMED,
        presign_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        confirmed_at=datetime.now(UTC),
    )
    session.add(upload)
    await session.flush()
    return upload


@pytest_asyncio.fixture
async def redis_client(test_settings: Settings) -> AsyncIterator[Redis]:
    client = Redis.from_url(test_settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def service(db_session: AsyncSession, redis_client: Redis) -> TweetsService:
    notifications_service = NotificationsService(
        NotificationRepository(db_session), UserRepository(db_session), db_session, redis_client
    )
    return TweetsService(
        TweetRepository(db_session),
        TweetMediaRepository(db_session),
        PendingUploadRepository(db_session),
        UserRepository(db_session),
        LikeRepository(db_session),
        notifications_service,
    )


# --- creation --------------------------------------------------------------


async def test_create_root_tweet_returns_full_view(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_alice")

    view = await service.create_tweet(
        alice, content="hello world", parent_tweet_id=None, media_keys=[]
    )
    await db_session.commit()

    assert view.content == "hello world"
    assert view.author.id == alice.id
    assert view.parent_tweet_id is None
    assert view.like_count == 0
    assert view.reply_count == 0
    assert view.liked_by_viewer is False
    assert view.media == []


async def test_create_tweet_with_confirmed_media_attaches_in_order(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_media_alice")
    upload_1 = await _make_confirmed_upload(db_session, user_id=alice.id)
    upload_2 = await _make_confirmed_upload(db_session, user_id=alice.id)

    view = await service.create_tweet(
        alice,
        content="two images",
        parent_tweet_id=None,
        media_keys=[upload_1.s3_key, upload_2.s3_key],
    )
    await db_session.commit()

    assert [m.key for m in view.media] == [upload_1.s3_key, upload_2.s3_key]
    assert [m.position for m in view.media] == [0, 1]


async def test_create_tweet_rejects_media_key_owned_by_another_user(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_forbid_alice")
    bob = await _make_user(db_session, "tweets_svc_forbid_bob")
    upload = await _make_confirmed_upload(db_session, user_id=bob.id)

    try:
        await service.create_tweet(
            alice, content="steal bob's image", parent_tweet_id=None, media_keys=[upload.s3_key]
        )
        raise AssertionError("expected MediaKeyForbiddenError")
    except MediaKeyForbiddenError:
        pass


async def test_create_tweet_rejects_unknown_media_key(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_unknown_alice")
    try:
        await service.create_tweet(
            alice, content="ghost image", parent_tweet_id=None, media_keys=["nope/does-not-exist"]
        )
        raise AssertionError("expected MediaKeyNotFoundError")
    except MediaKeyNotFoundError:
        pass


async def test_create_tweet_rejects_unconfirmed_media_key(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_unconfirmed_alice")
    upload = PendingUpload(
        user_id=alice.id,
        purpose=MediaPurpose.TWEET_IMAGE,
        s3_key=f"tweet_image/{alice.id}/{uuid4().hex}.png",
        content_type="image/png",
        size_bytes=1024,
        status=PendingUploadStatus.PENDING,
        presign_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    db_session.add(upload)
    await db_session.flush()

    try:
        await service.create_tweet(
            alice, content="not confirmed yet", parent_tweet_id=None, media_keys=[upload.s3_key]
        )
        raise AssertionError("expected MediaKeyNotConfirmedError")
    except MediaKeyNotConfirmedError:
        pass


async def test_create_tweet_rejects_avatar_purpose_key(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_wrongpurpose_alice")
    upload = await _make_confirmed_upload(db_session, user_id=alice.id)
    upload.purpose = MediaPurpose.AVATAR
    db_session.add(upload)
    await db_session.flush()

    try:
        await service.create_tweet(
            alice, content="wrong purpose", parent_tweet_id=None, media_keys=[upload.s3_key]
        )
        raise AssertionError("expected MediaKeyWrongPurposeError")
    except MediaKeyWrongPurposeError:
        pass


async def test_create_tweet_rejects_already_used_media_key(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_reused_alice")
    upload = await _make_confirmed_upload(db_session, user_id=alice.id)

    await service.create_tweet(
        alice, content="first tweet", parent_tweet_id=None, media_keys=[upload.s3_key]
    )
    await db_session.commit()

    try:
        await service.create_tweet(
            alice, content="reuse the same image", parent_tweet_id=None, media_keys=[upload.s3_key]
        )
        raise AssertionError("expected MediaKeyAlreadyUsedError")
    except MediaKeyAlreadyUsedError:
        pass


# --- flat-reply semantics ----------------------------------------------------


async def test_reply_increments_parent_and_notifies_atomically(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_reply_alice")
    bob = await _make_user(db_session, "tweets_svc_reply_bob")

    root = await service.create_tweet(
        alice, content="root tweet", parent_tweet_id=None, media_keys=[]
    )
    await db_session.commit()

    reply = await service.create_tweet(
        bob, content="nice tweet!", parent_tweet_id=root.id, media_keys=[]
    )
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    assert reply.parent_tweet_id == root.id

    refreshed_root = await service.get_tweet(root.id, alice)
    assert refreshed_root.reply_count == 1

    notifications = NotificationRepository(db_session)
    page = await notifications.list_for_recipient(alice.id, cursor=None, limit=10)
    assert len(page.items) == 1
    assert page.items[0].type == "reply"
    assert page.items[0].actor_id == bob.id
    assert page.items[0].tweet_id == root.id


async def test_replying_to_your_own_tweet_does_not_self_notify(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_selfreply_alice")
    root = await service.create_tweet(alice, content="root", parent_tweet_id=None, media_keys=[])
    await db_session.commit()

    await service.create_tweet(
        alice, content="replying to myself", parent_tweet_id=root.id, media_keys=[]
    )
    await db_session.commit()
    await run_post_commit_callbacks(db_session)

    notifications = NotificationRepository(db_session)
    page = await notifications.list_for_recipient(alice.id, cursor=None, limit=10)
    assert page.items == []


async def test_cannot_reply_to_a_reply(db_session: AsyncSession, service: TweetsService) -> None:
    alice = await _make_user(db_session, "tweets_svc_nested_alice")
    bob = await _make_user(db_session, "tweets_svc_nested_bob")

    root = await service.create_tweet(alice, content="root", parent_tweet_id=None, media_keys=[])
    await db_session.commit()
    reply = await service.create_tweet(
        bob, content="first reply", parent_tweet_id=root.id, media_keys=[]
    )
    await db_session.commit()

    try:
        await service.create_tweet(
            alice, content="nested reply", parent_tweet_id=reply.id, media_keys=[]
        )
        raise AssertionError("expected CannotReplyToReplyError")
    except CannotReplyToReplyError:
        pass


async def test_reply_to_nonexistent_tweet_raises_not_found(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_ghostparent_alice")
    try:
        await service.create_tweet(
            alice, content="reply to nothing", parent_tweet_id=uuid4(), media_keys=[]
        )
        raise AssertionError("expected TweetNotFoundError")
    except TweetNotFoundError:
        pass


# --- retrieval, viewer state, links ------------------------------------------


async def test_get_tweet_reports_viewer_like_state(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_liked_alice")
    bob = await _make_user(db_session, "tweets_svc_liked_bob")
    tweet = await service.create_tweet(
        alice, content="like me", parent_tweet_id=None, media_keys=[]
    )
    await db_session.commit()

    likes = LikeRepository(db_session)
    await likes.like(bob.id, tweet.id)
    await db_session.commit()

    view_from_bob = await service.get_tweet(tweet.id, bob)
    assert view_from_bob.liked_by_viewer is True

    view_from_alice = await service.get_tweet(tweet.id, alice)
    assert view_from_alice.liked_by_viewer is False


async def test_get_tweet_includes_safe_link_entities(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_links_alice")
    tweet = await service.create_tweet(
        alice, content="see https://example.com for more", parent_tweet_id=None, media_keys=[]
    )
    await db_session.commit()

    view = await service.get_tweet(tweet.id, alice)
    assert [link.url for link in view.links] == ["https://example.com"]


async def test_get_unknown_tweet_raises_not_found(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_notfound_alice")
    try:
        await service.get_tweet(uuid4(), alice)
        raise AssertionError("expected TweetNotFoundError")
    except TweetNotFoundError:
        pass


# --- replies + timeline pagination -------------------------------------------


async def test_list_replies_paginates_oldest_first_without_duplicates(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_repliespage_alice")
    bob = await _make_user(db_session, "tweets_svc_repliespage_bob")
    root = await service.create_tweet(alice, content="root", parent_tweet_id=None, media_keys=[])
    await db_session.commit()

    for i in range(3):
        db_session.add(Tweet(author_id=bob.id, content=f"reply-{i}", parent_tweet_id=root.id))
    await db_session.commit()

    page_1 = await service.list_replies(root.id, alice, cursor=None, limit=2)
    assert len(page_1.items) == 2
    assert page_1.next_cursor is not None

    page_2 = await service.list_replies(root.id, alice, cursor=page_1.next_cursor, limit=2)
    assert len(page_2.items) == 1
    assert page_2.next_cursor is None

    all_content = [t.content for t in page_1.items] + [t.content for t in page_2.items]
    assert all_content == ["reply-0", "reply-1", "reply-2"]  # oldest first
    assert len(set(all_content)) == 3  # no duplicates across pages


async def test_list_replies_of_a_reply_is_always_empty(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_emptyreplies_alice")
    bob = await _make_user(db_session, "tweets_svc_emptyreplies_bob")
    root = await service.create_tweet(alice, content="root", parent_tweet_id=None, media_keys=[])
    await db_session.commit()
    reply = await service.create_tweet(
        bob, content="a reply", parent_tweet_id=root.id, media_keys=[]
    )
    await db_session.commit()

    page = await service.list_replies(reply.id, alice, cursor=None, limit=10)
    assert page.items == []


async def test_list_replies_of_unknown_tweet_raises_not_found(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_repliesnotfound_alice")
    try:
        await service.list_replies(uuid4(), alice, cursor=None, limit=10)
        raise AssertionError("expected TweetNotFoundError")
    except TweetNotFoundError:
        pass


async def test_list_replies_malformed_cursor_is_rejected(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_badcursor_alice")
    root = await service.create_tweet(alice, content="root", parent_tweet_id=None, media_keys=[])
    await db_session.commit()

    try:
        await service.list_replies(root.id, alice, cursor="not-a-valid-cursor", limit=10)
        raise AssertionError("expected InvalidPaginationCursorError")
    except InvalidPaginationCursorError:
        pass


async def test_get_user_timeline_returns_authors_tweets_newest_first(
    db_session: AsyncSession, service: TweetsService
) -> None:
    alice = await _make_user(db_session, "tweets_svc_timeline_alice")
    viewer = await _make_user(db_session, "tweets_svc_timeline_viewer")
    base = datetime.now(UTC)
    for i in range(3):
        db_session.add(
            Tweet(author_id=alice.id, content=f"tl-{i}", created_at=base + timedelta(seconds=i))
        )
    await db_session.commit()

    page = await service.get_user_timeline(alice.username, viewer, cursor=None, limit=10)
    assert [t.content for t in page.items] == ["tl-2", "tl-1", "tl-0"]
    assert all(t.author.username == alice.username for t in page.items)


async def test_get_user_timeline_unknown_user_raises_not_found(
    db_session: AsyncSession, service: TweetsService
) -> None:
    viewer = await _make_user(db_session, "tweets_svc_timeline_viewer_2")
    try:
        await service.get_user_timeline("no_such_user_at_all", viewer, cursor=None, limit=10)
        raise AssertionError("expected UserNotFoundError")
    except UserNotFoundError:
        pass
