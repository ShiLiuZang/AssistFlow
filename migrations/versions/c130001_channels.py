"""External channels (Pinduoduo): channel_sessions, channel_messages, channel_orders."""

from alembic import op
import sqlalchemy as sa


revision = "c130001"
down_revision = "c120001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("shop_id", sa.String(64), nullable=False),
        sa.Column("buyer_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("last_inbound_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("channel", "shop_id", "buyer_id", name="uq_channel_buyer"),
        sa.UniqueConstraint("user_id", name="uq_channel_sessions_user_id"),
    )
    op.create_index("ix_channel_sessions_conversation_id", "channel_sessions", ["conversation_id"])

    op.create_table(
        "channel_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("channel_sessions.id"), nullable=False),
        sa.Column("direction", sa.String(4), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(255), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("channel", "direction", "external_id", name="uq_channel_message"),
    )
    op.create_index("ix_channel_messages_session_id", "channel_messages", ["session_id"])
    op.create_index("ix_channel_messages_status", "channel_messages", ["status"])

    op.create_table(
        "channel_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("goods_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("channel", "order_id", name="uq_channel_order"),
    )
    op.create_index("ix_channel_orders_user_id", "channel_orders", ["user_id"])


def downgrade() -> None:
    # 删表会一并删除表上的索引；外键列上的索引不能单独删除
    op.drop_table("channel_orders")
    op.drop_table("channel_messages")
    op.drop_table("channel_sessions")
