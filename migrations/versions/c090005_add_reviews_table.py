"""新增待审核队列表，关联问题池。"""

from alembic import op
import sqlalchemy as sa


revision = "c090005"
down_revision = "c090004"
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewer", sa.String(64), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.String(255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.func.now(),
        ),
        comment="Review queue for normalized questions",
    )


    op.add_column(
        "low_confidence_questions",
        sa.Column("review_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_low_confidence_questions_review_id",
        "low_confidence_questions",
        "reviews",
        ["review_id"],
        ["id"],
    )


def downgrade() -> None:

    op.drop_constraint(
        "fk_low_confidence_questions_review_id",
        "low_confidence_questions",
        type_="foreignkey",
    )


    op.drop_column("low_confidence_questions", "review_id")


    op.drop_table("reviews")
