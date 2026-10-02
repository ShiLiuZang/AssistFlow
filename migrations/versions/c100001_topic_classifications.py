"""Add 微调 topic classification results for the AssistFlow classifier pipeline."""

from alembic import op
import sqlalchemy as sa


revision = "c100001"
down_revision = "c090010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic_classifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("classified_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["question_id"], ["low_confidence_questions.id"]),
        sa.UniqueConstraint("question_id", name="uq_topic_classifications_question_id"),
    )


def downgrade() -> None:
    op.drop_table("topic_classifications")
