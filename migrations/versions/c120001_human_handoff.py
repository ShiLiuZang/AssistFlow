"""Human handoff: handoffs, ticket_events, ticket workflow columns, message author."""

from alembic import op
import sqlalchemy as sa


revision = "c120001"
down_revision = "c110001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "handoffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("card", sa.JSON(), nullable=True),
        sa.Column("assignee", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("closed_by", sa.String(64), nullable=True),
        sa.Column("harvested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_handoffs_conversation_id", "handoffs", ["conversation_id"])
    op.create_index("ix_handoffs_user_id", "handoffs", ["user_id"])
    op.create_index("ix_handoffs_status", "handoffs", ["status"])
    op.create_index("ix_handoffs_assignee", "handoffs", ["assignee"])

    op.add_column("messages", sa.Column("author", sa.String(64), nullable=True))

    op.add_column("tickets", sa.Column("user_id", sa.String(64), nullable=True))
    op.add_column("tickets", sa.Column("title", sa.String(120), nullable=True))
    # 不用中文作服务端默认值：DDL 的连接字符集可能不是 utf8mb4，旧工单的空值按「普通」显示
    op.add_column("tickets", sa.Column("priority", sa.String(8), nullable=True))
    op.add_column("tickets", sa.Column("assignee", sa.String(64), nullable=True))
    op.add_column("tickets", sa.Column("source", sa.String(16), nullable=False, server_default="customer"))
    op.add_column("tickets", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.create_index("ix_tickets_user_id", "tickets", ["user_id"])

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ticket_events_ticket_id", "ticket_events", ["ticket_id"])


def downgrade() -> None:
    # 删表会一并删除表上的索引；外键列上的索引不能单独删除
    op.drop_table("ticket_events")
    op.drop_index("ix_tickets_user_id", table_name="tickets")
    for column in ("updated_at", "source", "assignee", "priority", "title", "user_id"):
        op.drop_column("tickets", column)
    op.drop_column("messages", "author")
    op.drop_table("handoffs")
