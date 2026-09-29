"""为每个审核项固定一个知识块，并记录发布失败原因。"""

from alembic import op
import sqlalchemy as sa


revision = "c090008"
down_revision = "c090007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_chunks",
        sa.Column("review_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_knowledge_chunks_review_id",
        "knowledge_chunks",
        "reviews",
        ["review_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_knowledge_chunks_review_id",
        "knowledge_chunks",
        ["review_id"],
    )
    op.add_column(
        "reviews",
        sa.Column("publish_error", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reviews", "publish_error")
    op.drop_constraint(
        "uq_knowledge_chunks_review_id",
        "knowledge_chunks",
        type_="unique",
    )
    op.drop_constraint(
        "fk_knowledge_chunks_review_id",
        "knowledge_chunks",
        type_="foreignkey",
    )
    op.drop_column("knowledge_chunks", "review_id")
