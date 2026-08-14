"""add pending_uploads

`pending_uploads` (TSC-MEDIA-001): tracks every presigned upload URL from
issue to confirmation (or abandonment), scoped to the requesting user.
See `app.models.pending_upload` for why this table exists and how it's used.

Revision ID: 0002_add_pending_uploads
Revises: 0001_initial_schema
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_pending_uploads"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

media_purpose = postgresql.ENUM("avatar", "tweet_image", name="media_purpose", create_type=False)
pending_upload_status = postgresql.ENUM(
    "pending", "confirmed", name="pending_upload_status", create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    media_purpose.create(op.get_bind(), checkfirst=True)
    pending_upload_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "pending_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", media_purpose, nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "status", pending_upload_status, nullable=False, server_default="pending"
        ),
        sa.Column("presign_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_pending_uploads_user_id_users"
        ),
        sa.UniqueConstraint("s3_key", name="uq_pending_uploads_s3_key"),
    )
    op.create_index("ix_pending_uploads_user_id", "pending_uploads", ["user_id"])
    op.create_index("ix_pending_uploads_s3_key", "pending_uploads", ["s3_key"])
    # Cleanup task sweep: pending rows ordered by age.
    op.execute(
        "CREATE INDEX ix_pending_uploads_status_created_at ON pending_uploads "
        "(created_at) WHERE status = 'pending'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_pending_uploads_status_created_at", table_name="pending_uploads")
    op.drop_index("ix_pending_uploads_s3_key", table_name="pending_uploads")
    op.drop_index("ix_pending_uploads_user_id", table_name="pending_uploads")
    op.drop_table("pending_uploads")
    pending_upload_status.drop(op.get_bind(), checkfirst=True)
    media_purpose.drop(op.get_bind(), checkfirst=True)
