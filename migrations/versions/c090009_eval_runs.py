"""保存 Ch09 固定集评测运行结果。"""

from alembic import op
import sqlalchemy as sa


revision = "c090009"
down_revision = "c090008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_version", sa.String(128), nullable=False),
        sa.Column("case_ids", sa.JSON(), nullable=False),
        sa.Column("config_version", sa.String(128), nullable=False),
        sa.Column("kb_revision", sa.String(128), nullable=False),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("triggered_by", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_eval_runs_created_at", "eval_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_eval_runs_created_at", table_name="eval_runs")
    op.drop_table("eval_runs")
