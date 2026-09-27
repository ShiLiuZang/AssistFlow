"""新增执行观测记录表。"""

from alembic import op
import sqlalchemy as sa


revision = "c090001"
down_revision = "c080008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trace_spans",
        sa.Column("span_id", sa.String(32), primary_key=True),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("parent_id", sa.String(32), nullable=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("duration_ms", sa.Float(precision=53), nullable=False),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_trace_spans_trace_id", "trace_spans", ["trace_id"],
    )
    op.create_index(
        "ix_trace_spans_created_at", "trace_spans", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_trace_spans_created_at", table_name="trace_spans")
    op.drop_index("ix_trace_spans_trace_id", table_name="trace_spans")
    op.drop_table("trace_spans")
