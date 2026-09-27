"""为执行观测记录增加模型用量字段。"""

from alembic import op
import sqlalchemy as sa


revision = "c090002"
down_revision = "c090001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trace_spans",
        sa.Column("kind", sa.String(16), nullable=False,
                  server_default="span"),
    )
    op.add_column(
        "trace_spans",
        sa.Column("intent", sa.String(64), nullable=True),
    )
    op.add_column(
        "trace_spans",
        sa.Column("model", sa.String(255), nullable=True),
    )
    op.add_column(
        "trace_spans",
        sa.Column("input_tokens", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "trace_spans",
        sa.Column("output_tokens", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "trace_spans",
        sa.Column("total_tokens", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trace_spans", "total_tokens")
    op.drop_column("trace_spans", "output_tokens")
    op.drop_column("trace_spans", "input_tokens")
    op.drop_column("trace_spans", "model")
    op.drop_column("trace_spans", "intent")
    op.drop_column("trace_spans", "kind")
