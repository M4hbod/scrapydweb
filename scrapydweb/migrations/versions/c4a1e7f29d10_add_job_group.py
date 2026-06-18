"""add job_group

Revision ID: c4a1e7f29d10
Revises: b3f228171b78
Create Date: 2026-06-12

"""
import sqlalchemy as sa
from alembic import op

revision = 'c4a1e7f29d10'
down_revision = 'b3f228171b78'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'job_group',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('project', sa.String(length=255), nullable=False),
        sa.Column('version', sa.String(length=255), nullable=True),
        sa.Column('spiders_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('nodes_json', sa.Text(), nullable=False, server_default='[1]'),
        sa.Column('settings_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('args_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_job_group_name', 'job_group', ['name'], unique=True)


def downgrade():
    op.drop_index('ix_job_group_name', table_name='job_group')
    op.drop_table('job_group')
