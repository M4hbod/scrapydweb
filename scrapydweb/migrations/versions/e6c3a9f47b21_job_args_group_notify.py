"""job args + group link on job_version; notify config on job_group

Revision ID: e6c3a9f47b21
Revises: d5b2f8a31c92
Create Date: 2026-06-19

"""
import sqlalchemy as sa
from alembic import op

revision = 'e6c3a9f47b21'
down_revision = 'd5b2f8a31c92'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('job_version', sa.Column('args_json', sa.Text(), nullable=False, server_default='{}'))
    op.add_column('job_version', sa.Column('group_id', sa.BigInteger(), nullable=True))
    op.add_column('job_group', sa.Column('notify_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('job_group', sa.Column('notify_channels_json', sa.Text(), nullable=False, server_default='[]'))
    op.add_column('task', sa.Column('group_id', sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column('task', 'group_id')
    op.drop_column('job_group', 'notify_channels_json')
    op.drop_column('job_group', 'notify_enabled')
    op.drop_column('job_version', 'group_id')
    op.drop_column('job_version', 'args_json')
