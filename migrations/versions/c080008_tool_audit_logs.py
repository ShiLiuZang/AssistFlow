"""Persist redacted tool audit records."""

from alembic import op
import sqlalchemy as sa

revision = "c080008"
down_revision = "c070004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_key", sa.String(200), nullable=True),
        sa.Column("tool_call_id", sa.String(100), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("server", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("argument_fields", sa.JSON(), nullable=False),
        sa.Column("result_chars", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "audit_key",
            name="uq_tool_audit_logs_audit_key",
        ),
    )
    op.create_index(
        "ix_tool_audit_logs_conversation_id",
        "tool_audit_logs",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tool_audit_logs_conversation_id",
        table_name="tool_audit_logs",
    )
    op.drop_table("tool_audit_logs")