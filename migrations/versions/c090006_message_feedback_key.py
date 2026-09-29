"""为消息保存轮次反馈标识。"""

from alembic import op
import sqlalchemy as sa


revision = "c090006"
down_revision = "c090005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("turn_message_id", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_messages_turn_message_id",
        "messages",
        ["turn_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_messages_turn_message_id",
        "messages",
        type_="unique",
    )
    op.drop_column("messages", "turn_message_id")
