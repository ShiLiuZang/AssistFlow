"""冻结人工审核时采用的可信材料版本。"""

from alembic import op
import sqlalchemy as sa


revision = "c090007"
down_revision = "c090006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("source_digest", sa.String(64), nullable=True))
    op.add_column("reviews", sa.Column("reviewed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("reviews", "reviewed_at")
    op.drop_column("reviews", "source_digest")
