"""Initial schema"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("turn_seq", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "room_members",
        sa.Column(
            "room_id",
            sa.String(length=36),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.String(length=36), primary_key=True),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "objects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "room_id",
            sa.String(length=36),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=False),
        sa.Column("anchor_ring", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "strokes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "room_id",
            sa.String(length=36),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_id", sa.String(length=36), nullable=False),
        sa.Column("color", sa.String(length=50), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("path", sa.JSON(), nullable=False),
        sa.Column(
            "object_id",
            sa.String(length=36),
            sa.ForeignKey("objects.id", ondelete="SET NULL"),
        ),
    )

    op.create_table(
        "turns",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "room_id",
            sa.String(length=36),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_actor", sa.String(length=30), nullable=False),
        sa.Column(
            "source_object_id",
            sa.String(length=36),
            sa.ForeignKey("objects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ai_patch_uri", sa.String(length=500)),
        sa.Column("safety_status", sa.String(length=50)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "room_id",
            sa.String(length=36),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=36)),
        sa.Column(
            "turn_id",
            sa.String(length=36),
            sa.ForeignKey("turns.id", ondelete="SET NULL"),
        ),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index(
        "ix_turns_room_sequence", "turns", ["room_id", "sequence"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_turns_room_sequence", table_name="turns")
    op.drop_table("audit_logs")
    op.drop_table("turns")
    op.drop_table("strokes")
    op.drop_table("objects")
    op.drop_table("room_members")
    op.drop_table("rooms")
