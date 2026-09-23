# 作者：zcy
"""add doc_chunks for multimodal document knowledge base

Revision ID: 7f9a2d1c3b4e
Revises: 6c352c941647
Create Date: 2026-09-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy  # noqa: F401  (VECTOR 类型引用)


# revision identifiers, used by Alembic.
revision: str = '7f9a2d1c3b4e'
down_revision: Union[str, Sequence[str], None] = '6c352c941647'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('doc_chunks',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('doc_id', sa.String(), nullable=False),
    sa.Column('source_name', sa.String(length=200), nullable=False),
    sa.Column('page', sa.Integer(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
    sa.Column('meta', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_doc_chunks_hnsw', 'doc_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index(op.f('ix_doc_chunks_doc_id'), 'doc_chunks', ['doc_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_doc_chunks_doc_id'), table_name='doc_chunks')
    op.drop_index('idx_doc_chunks_hnsw', table_name='doc_chunks', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('doc_chunks')
