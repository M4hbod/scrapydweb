"""project registry (fold deploy_repo)

Creates the `project` table, migrates existing `deploy_repo` rows into it
(webhook-source projects) plus a 'manual' project for every project name seen
in deploy_record, then drops `deploy_repo`.

Hand-written: autogenerate can't emit the data copy, and env.py's include_object
deliberately never drops reflected tables.

Revision ID: b3f228171b78
Revises: bcc935582a1a
Create Date: 2026-06-10 02:54:07.908816
"""
from alembic import op
import sqlalchemy as sa


revision = 'b3f228171b78'
down_revision = 'bcc935582a1a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'project',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('deploy_source', sa.String(length=16), nullable=False, server_default='manual'),
        sa.Column('default_nodes_json', sa.Text(), nullable=False, server_default='[1]'),
        sa.Column('repo_url', sa.String(length=512), nullable=True),
        sa.Column('ref', sa.String(length=255), nullable=True, server_default='main'),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('webhook_secret', sa.String(length=64), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index('ix_project_name', 'project', ['name'], unique=False)

    # fold each registered repo into a webhook-source project (repo.name -> description)
    op.execute("""
        INSERT INTO project
            (name, description, deploy_source, default_nodes_json, repo_url, ref,
             access_token, webhook_secret, enabled, created_at, updated_at)
        SELECT project, name, 'webhook', nodes_json, repo_url, ref,
               access_token, webhook_secret, enabled, created_at, updated_at
        FROM deploy_repo
        ON CONFLICT (name) DO NOTHING
    """)
    # register every project name seen in the deploy history as a manual project
    op.execute("""
        INSERT INTO project (name, deploy_source, default_nodes_json, ref, enabled)
        SELECT DISTINCT project, 'manual', '[1]', 'main', true
        FROM deploy_record
        WHERE project IS NOT NULL AND project <> ''
        ON CONFLICT (name) DO NOTHING
    """)

    op.drop_table('deploy_repo')


def downgrade():
    op.create_table(
        'deploy_repo',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('repo_url', sa.String(length=512), nullable=False),
        sa.Column('ref', sa.String(length=255), nullable=False, server_default='main'),
        sa.Column('project', sa.String(length=255), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('webhook_secret', sa.String(length=64), nullable=False),
        sa.Column('nodes_json', sa.Text(), nullable=False, server_default='[1]'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.execute("""
        INSERT INTO deploy_repo
            (name, repo_url, ref, project, access_token, webhook_secret,
             nodes_json, enabled, created_at, updated_at)
        SELECT COALESCE(description, name), repo_url, ref, name, access_token,
               COALESCE(webhook_secret, ''), default_nodes_json, enabled, created_at, updated_at
        FROM project
        WHERE deploy_source = 'webhook' AND repo_url IS NOT NULL
    """)
    op.drop_index('ix_project_name', table_name='project')
    op.drop_table('project')
