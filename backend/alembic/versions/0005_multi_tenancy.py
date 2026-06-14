"""multi-tenant schema additions

Revision ID: 0005_multi_tenancy
Revises: 0004_document_management
Create Date: 2026-05-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '0005_multi_tenancy'
down_revision = '0004_document_management'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    return inspect(bind).has_table(table_name)


def _column_exists(table_name, column_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    # Create tenants, workspaces, roles, api_keys, audit_logs
    if not _table_exists('tenants'):
        op.create_table(
            'tenants',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('name', sa.String(255), nullable=False, unique=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        )

    if not _table_exists('workspaces'):
        op.create_table(
            'workspaces',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('settings', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        )

    if not _table_exists('roles'):
        op.create_table(
            'roles',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=False),
            sa.Column('name', sa.String(128), nullable=False),
            sa.Column('permissions', sa.JSON(), nullable=True),
        )

    if not _table_exists('user_roles'):
        op.create_table(
            'user_roles',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
            sa.Column('role_id', sa.Integer, sa.ForeignKey('roles.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        )

    if not _table_exists('api_keys'):
        op.create_table(
            'api_keys',
            sa.Column('id', sa.BigInteger, primary_key=True),
            sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=False),
            sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True),
            sa.Column('key_hash', sa.String(255), nullable=False),
            sa.Column('scopes', sa.JSON(), nullable=True),
            sa.Column('created_by', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        )

    if not _table_exists('audit_logs'):
        op.create_table(
            'audit_logs',
            sa.Column('id', sa.BigInteger, primary_key=True),
            sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=False),
            sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
            sa.Column('action', sa.String(128), nullable=False),
            sa.Column('resource_type', sa.String(128), nullable=True),
            sa.Column('resource_id', sa.String(255), nullable=True),
            sa.Column('details', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        )

    # Add tenant_id / workspace_id to existing core tables
    cols = [
        ('users', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('users', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('documents', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('documents', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('ingestion_jobs', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=False)),
        ('ingestion_jobs', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('chunks', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('chunks', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('embeddings', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('embeddings', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('conversations', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('conversations', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('traces', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('traces', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('retrieval_logs', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('retrieval_logs', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('memories', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('memories', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('tools_history', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('tools_history', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('review_requests', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('review_requests', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('reflection_logs', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('reflection_logs', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
        ('evaluation_runs', sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=True)),
        ('evaluation_runs', sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id'), nullable=True)),
    ]

    for table_name, column in cols:
        if _table_exists(table_name) and not _column_exists(table_name, column.name):
            op.add_column(table_name, column)


def downgrade():
    # Remove added columns (best-effort)
    col_names = [
        ('users', 'tenant_id'), ('users', 'workspace_id'),
        ('documents', 'tenant_id'), ('documents', 'workspace_id'),
        ('ingestion_jobs', 'tenant_id'), ('ingestion_jobs', 'workspace_id'),
        ('chunks', 'tenant_id'), ('chunks', 'workspace_id'),
        ('embeddings', 'tenant_id'), ('embeddings', 'workspace_id'),
        ('conversations', 'tenant_id'), ('conversations', 'workspace_id'),
        ('traces', 'tenant_id'), ('traces', 'workspace_id'),
        ('retrieval_logs', 'tenant_id'), ('retrieval_logs', 'workspace_id'),
        ('memories', 'tenant_id'), ('memories', 'workspace_id'),
        ('tools_history', 'tenant_id'), ('tools_history', 'workspace_id'),
        ('review_requests', 'tenant_id'), ('review_requests', 'workspace_id'),
        ('reflection_logs', 'tenant_id'), ('reflection_logs', 'workspace_id'),
        ('evaluation_runs', 'tenant_id'), ('evaluation_runs', 'workspace_id'),
    ]
    for table_name, col in col_names:
        try:
            op.drop_column(table_name, col)
        except Exception:
            pass

    # Drop new tables
    try:
        op.drop_table('audit_logs')
    except Exception:
        pass
    try:
        op.drop_table('api_keys')
    except Exception:
        pass
    try:
        op.drop_table('roles')
    except Exception:
        pass
    try:
        op.drop_table('workspaces')
    except Exception:
        pass
    try:
        op.drop_table('tenants')
    except Exception:
        pass
