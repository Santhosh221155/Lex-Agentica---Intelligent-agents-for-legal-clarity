
"""fix documents schema: make old columns nullable and set defaults

Revision ID: 0009_fix_documents_schema
Revises: 0008_merge
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0009_fix_documents_schema"
down_revision = "0008_merge"
branch_labels = None
depends_on = None


def _column_exists(table_name, column_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    # First, make filename/source columns nullable if they exist
    if _column_exists('documents', 'filename'):
        try:
            op.alter_column('documents', 'filename', existing_type=sa.String(255), nullable=True)
        except Exception:
            pass
    if _column_exists('documents', 'source'):
        try:
            op.alter_column('documents', 'source', existing_type=sa.String(255), nullable=True)
        except Exception:
            pass
    if _column_exists('documents', 'upload_time'):
        try:
            op.alter_column('documents', 'upload_time', existing_type=sa.DateTime(), nullable=True)
        except Exception:
            pass
    if _column_exists('documents', 'deleted_at'):
        try:
            op.alter_column('documents', 'deleted_at', existing_type=sa.DateTime(), nullable=True)
        except Exception:
            pass

    # Now, ensure tenant_id/workspace_id are NOT NULL (models require them)
    # First, set default values if needed
    try:
        # Check if tenants/workspaces exist, create defaults if not
        conn = op.get_bind()
        
        # Check if default tenant exists
        result = conn.execute(sa.text("SELECT id FROM tenants WHERE name = 'default' LIMIT 1"))
        tenant_id = result.scalar()
        if not tenant_id:
            conn.execute(sa.text("INSERT INTO tenants (name) VALUES ('default') ON CONFLICT DO NOTHING"))
            result = conn.execute(sa.text("SELECT id FROM tenants WHERE name = 'default' LIMIT 1"))
            tenant_id = result.scalar()
        
        # Check if default workspace exists
        result = conn.execute(sa.text("SELECT id FROM workspaces WHERE tenant_id = :tenant_id AND name = 'default' LIMIT 1"), {'tenant_id': tenant_id})
        workspace_id = result.scalar()
        if not workspace_id:
            conn.execute(sa.text("INSERT INTO workspaces (tenant_id, name) VALUES (:tenant_id, 'default') ON CONFLICT DO NOTHING"), {'tenant_id': tenant_id})
            result = conn.execute(sa.text("SELECT id FROM workspaces WHERE tenant_id = :tenant_id AND name = 'default' LIMIT 1"), {'tenant_id': tenant_id})
            workspace_id = result.scalar()
        
        # Update any documents with null tenant_id/workspace_id
        if tenant_id and workspace_id:
            conn.execute(sa.text("UPDATE documents SET tenant_id = :tenant_id WHERE tenant_id IS NULL"), {'tenant_id': tenant_id})
            conn.execute(sa.text("UPDATE documents SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {'workspace_id': workspace_id})
        
        # Now alter columns to be NOT NULL
        try:
            op.alter_column('documents', 'tenant_id', existing_type=sa.Integer(), nullable=False)
        except Exception:
            pass
        try:
            op.alter_column('documents', 'workspace_id', existing_type=sa.Integer(), nullable=False)
        except Exception:
            pass
            
    except Exception as e:
        print(f"Warning: Could not set tenant/workspace defaults: {e}")
        pass


def downgrade():
    # Best-effort downgrade
    try:
        op.alter_column('documents', 'tenant_id', existing_type=sa.Integer(), nullable=True)
    except Exception:
        pass
    try:
        op.alter_column('documents', 'workspace_id', existing_type=sa.Integer(), nullable=True)
    except Exception:
        pass
    # Make filename/source NOT NULL again (if they exist)
    if _column_exists('documents', 'filename'):
        try:
            op.alter_column('documents', 'filename', existing_type=sa.String(255), nullable=False)
        except Exception:
            pass
