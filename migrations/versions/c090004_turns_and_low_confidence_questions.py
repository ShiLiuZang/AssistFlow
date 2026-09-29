"""新增回答快照表和低置信度问题池表。"""

from alembic import op
import sqlalchemy as sa


revision = "c090004"
down_revision = "c090002"
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table(
        "turns",
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("conversation", sa.String(64), nullable=False),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("turn_id", sa.String(64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("owner", "conversation", "message_id"),
        comment="Conversation turn snapshots for historical reference",
    )


    op.create_table(
        "low_confidence_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("conversation", sa.String(64), nullable=False),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.func.now(),
        ),
        comment="Low confidence questions pool for review",
    )


    op.create_index(
        "ix_low_confidence_questions_owner",
        "low_confidence_questions",
        ["owner"],
    )
    op.create_index(
        "ix_low_confidence_questions_conversation",
        "low_confidence_questions",
        ["conversation"],
    )
    op.create_index(
        "ix_low_confidence_questions_created_at",
        "low_confidence_questions",
        ["created_at"],
    )


    op.create_unique_constraint(
        "uq_pool_message_source",
        "low_confidence_questions",
        ["owner", "conversation", "message_id", "source"],
    )


def downgrade() -> None:

    op.drop_constraint(
        "uq_pool_message_source",
        "low_confidence_questions",
        type_="unique",
    )


    op.drop_index(
        "ix_low_confidence_questions_created_at",
        table_name="low_confidence_questions",
    )
    op.drop_index(
        "ix_low_confidence_questions_conversation",
        table_name="low_confidence_questions",
    )
    op.drop_index(
        "ix_low_confidence_questions_owner",
        table_name="low_confidence_questions",
    )


    op.drop_table("low_confidence_questions")
    op.drop_table("turns")
