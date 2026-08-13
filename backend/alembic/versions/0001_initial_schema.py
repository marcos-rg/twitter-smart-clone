"""initial schema

Creates every table from spec §5.1 (`users`, `tweets`, `tweet_media`,
`follows`, `likes`, `notifications`, `refresh_tokens`), the `citext` and
`pg_trgm` extensions, and every constraint/index the spec calls out
explicitly:

- Unique `users.username`/`users.email` (via the `citext` column type
  itself: PostgreSQL's plain `UNIQUE` on a `citext` column is already
  case-insensitive).
- GIN trigram indexes on `users.username`/`users.name` for fuzzy search.
- `(author_id, created_at desc)`, `(parent_tweet_id, created_at asc)`,
  `(created_at desc)` on `tweets`.
- Composite PK `(follower_id, followee_id)` on `follows` + a
  `follower_id <> followee_id` check constraint (rejects self-follows).
- Composite PK `(user_id, tweet_id)` on `likes` (idempotent like) +
  index on `tweet_id`.
- `(recipient_id, created_at desc)` and a partial index on
  `(recipient_id) WHERE is_read = false` on `notifications`.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

notification_type = postgresql.ENUM(
    "follow", "like", "reply", name="notification_type", create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('CREATE EXTENSION IF NOT EXISTS "citext"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    notification_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("username", postgresql.CITEXT(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("bio", sa.String(length=160), nullable=True),
        sa.Column("avatar_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])
    op.execute("CREATE INDEX ix_users_username_trgm ON users USING gin (username gin_trgm_ops)")
    op.execute("CREATE INDEX ix_users_name_trgm ON users USING gin (name gin_trgm_ops)")

    op.create_table(
        "tweets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.String(length=280), nullable=False),
        sa.Column("parent_tweet_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reply_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_tweets_author_id_users"),
        sa.ForeignKeyConstraint(
            ["parent_tweet_id"], ["tweets.id"], name="fk_tweets_parent_tweet_id_tweets"
        ),
    )
    op.create_index("ix_tweets_author_id", "tweets", ["author_id"])
    op.create_index("ix_tweets_parent_tweet_id", "tweets", ["parent_tweet_id"])
    op.create_index(
        "ix_tweets_author_id_created_at", "tweets", ["author_id", sa.text("created_at DESC")]
    )
    op.create_index(
        "ix_tweets_parent_tweet_id_created_at",
        "tweets",
        ["parent_tweet_id", sa.text("created_at ASC")],
    )
    op.create_index("ix_tweets_created_at", "tweets", [sa.text("created_at DESC")])

    op.create_table(
        "tweet_media",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tweet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tweet_id"], ["tweets.id"], name="fk_tweet_media_tweet_id_tweets"),
        sa.CheckConstraint("position >= 0 AND position <= 3", name="ck_tweet_media_position"),
    )
    op.create_index("ix_tweet_media_tweet_id", "tweet_media", ["tweet_id"])

    op.create_table(
        "follows",
        sa.Column("follower_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("followee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"], name="fk_follows_follower_id_users"),
        sa.ForeignKeyConstraint(["followee_id"], ["users.id"], name="fk_follows_followee_id_users"),
        sa.PrimaryKeyConstraint("follower_id", "followee_id", name="pk_follows"),
        sa.CheckConstraint("follower_id <> followee_id", name="ck_follows_no_self_follow"),
    )
    op.create_index("ix_follows_follower_id", "follows", ["follower_id"])
    op.create_index("ix_follows_followee_id", "follows", ["followee_id"])

    op.create_table(
        "likes",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tweet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_likes_user_id_users"),
        sa.ForeignKeyConstraint(["tweet_id"], ["tweets.id"], name="fk_likes_tweet_id_tweets"),
        sa.PrimaryKeyConstraint("user_id", "tweet_id", name="pk_likes"),
    )
    op.create_index("ix_likes_tweet_id", "likes", ["tweet_id"])

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", notification_type, nullable=False),
        sa.Column("tweet_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recipient_id"], ["users.id"], name="fk_notifications_recipient_id_users"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_notifications_actor_id_users"),
        sa.ForeignKeyConstraint(
            ["tweet_id"], ["tweets.id"], name="fk_notifications_tweet_id_tweets"
        ),
    )
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])
    op.create_index(
        "ix_notifications_recipient_id_created_at",
        "notifications",
        ["recipient_id", sa.text("created_at DESC")],
    )
    op.execute(
        "CREATE INDEX ix_notifications_recipient_id_unread ON notifications (recipient_id) "
        "WHERE is_read = false"
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("refresh_tokens")
    op.drop_index("ix_notifications_recipient_id_unread", table_name="notifications")
    op.drop_index("ix_notifications_recipient_id_created_at", table_name="notifications")
    op.drop_index("ix_notifications_recipient_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("likes")
    op.drop_table("follows")
    op.drop_table("tweet_media")
    op.drop_index("ix_tweets_created_at", table_name="tweets")
    op.drop_index("ix_tweets_parent_tweet_id_created_at", table_name="tweets")
    op.drop_index("ix_tweets_author_id_created_at", table_name="tweets")
    op.drop_table("tweets")
    op.drop_index("ix_users_name_trgm", table_name="users")
    op.drop_index("ix_users_username_trgm", table_name="users")
    op.drop_table("users")
    notification_type.drop(op.get_bind(), checkfirst=True)
