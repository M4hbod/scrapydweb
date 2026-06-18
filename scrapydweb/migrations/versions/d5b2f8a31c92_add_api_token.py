"""add api_token

Revision ID: d5b2f8a31c92
Revises: c4a1e7f29d10
Create Date: 2026-06-12

"""
import sqlalchemy as sa
from alembic import op

revision = 'd5b2f8a31c92'
down_revision = 'c4a1e7f29d10'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'api_token',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('prefix', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_api_token_token_hash', 'api_token', ['token_hash'], unique=True)


def downgrade():
    op.drop_index('ix_api_token_token_hash', table_name='api_token')
    op.drop_table('api_token')
