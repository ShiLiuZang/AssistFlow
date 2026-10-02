"""Add staff_users for back-office login and role-based access."""

from alembic import op
import sqlalchemy as sa


revision = "c110001"
down_revision = "c100001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("username", name="uq_staff_users_username"),
    )


def downgrade() -> None:
    op.drop_table("staff_users")
