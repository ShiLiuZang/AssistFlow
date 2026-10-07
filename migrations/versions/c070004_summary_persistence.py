"""Persist summary text, cursor and optimistic version together."""
from alembic import op
import sqlalchemy as sa

revision = "c070004"
down_revision = "83ebbbced7d5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("summary_text", sa.Text(), nullable=True))
    op.add_column("conversations", sa.Column("summary_upto", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("conversations", sa.Column("summary_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("conversations", "summary_version")
    op.drop_column("conversations", "summary_upto")
    op.drop_column("conversations", "summary_text")
