"""align DB schema with models: add title/source_uri and rename embedding refs

Revision ID: 0006_schema_alignment
Revises: 0005_multi_tenancy
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006_schema_alignment"
down_revision = "0005_multi_tenancy"
branch_labels = None
depends_on = None


def upgrade():
    # documents: add title, source_uri, version, uploaded_by, created_at, soft_deleted
    try:
        op.add_column('documents', sa.Column('title', sa.String(length=255), nullable=True))
    except Exception:
        pass
    try:
        op.add_column('documents', sa.Column('source_uri', sa.String(length=1024), nullable=True))
    except Exception:
        pass
    try:
        op.add_column('documents', sa.Column('version', sa.String(length=64), nullable=True))
    except Exception:
        pass
    try:
        op.add_column('documents', sa.Column('uploaded_by', sa.Integer, nullable=True))
    except Exception:
        pass
    try:
        op.add_column('documents', sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True))
    except Exception:
        pass
    try:
        op.add_column('documents', sa.Column('soft_deleted', sa.Boolean(), server_default="0", nullable=True))
    except Exception:
        pass

    # copy existing data where possible
    try:
        op.execute("UPDATE documents SET title = filename WHERE title IS NULL")
        op.execute("UPDATE documents SET source_uri = source WHERE source_uri IS NULL")
        op.execute("UPDATE documents SET created_at = upload_time WHERE created_at IS NULL")
    except Exception:
        pass

    # embeddings: add vector_id and model_name, migrate vector_reference
    try:
        op.add_column('embeddings', sa.Column('vector_id', sa.String(length=255), nullable=True))
    except Exception:
        pass
    try:
        op.add_column('embeddings', sa.Column('model_name', sa.String(length=255), nullable=True))
    except Exception:
        pass
    try:
        op.execute("UPDATE embeddings SET vector_id = vector_reference WHERE vector_id IS NULL")
    except Exception:
        pass
    try:
        op.drop_column('embeddings', 'vector_reference')
    except Exception:
        pass


def downgrade():
    # Best-effort downgrade: restore previous names where practical
    try:
        op.add_column('embeddings', sa.Column('vector_reference', sa.String(length=255), nullable=True))
    except Exception:
        pass
    try:
        op.execute("UPDATE embeddings SET vector_reference = vector_id WHERE vector_reference IS NULL")
    except Exception:
        pass
    try:
        op.drop_column('embeddings', 'vector_id')
    except Exception:
        pass
    try:
        op.drop_column('embeddings', 'model_name')
    except Exception:
        pass

    # documents
    for col in ('title', 'source_uri', 'version', 'uploaded_by', 'created_at', 'soft_deleted'):
        try:
            op.drop_column('documents', col)
        except Exception:
            pass
