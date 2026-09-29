"""create ch03 knowledge chunks

Revision ID: 83ebbbced7d5
Revises: e85ec34e7af6
Create Date: 2026-09-18 16:21:29.210321

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



revision: str = '83ebbbced7d5'
down_revision: Union[str, Sequence[str], None] = 'e85ec34e7af6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table('knowledge_chunks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(length=255), nullable=False),
    sa.Column('questions', sa.Text(), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('section_path', sa.String(length=512), nullable=True),
    sa.Column('content_type', sa.String(length=32), nullable=True),
    sa.Column('is_key_clause', sa.Integer(), nullable=False),
    sa.Column('prev_chunk_id', sa.Integer(), nullable=True),
    sa.Column('next_chunk_id', sa.Integer(), nullable=True),
    sa.Column('vector_id', sa.String(length=100), nullable=True),
    sa.Column('vectorize_status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_chunks_vectorize_status'), 'knowledge_chunks', ['vectorize_status'], unique=False)



def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f('ix_knowledge_chunks_vectorize_status'), table_name='knowledge_chunks')
    op.drop_table('knowledge_chunks')
