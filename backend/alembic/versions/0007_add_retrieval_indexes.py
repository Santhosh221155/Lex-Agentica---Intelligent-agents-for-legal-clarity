"""add retrieval-path indexes for BM25 source query

Revision ID: 0007_add_retrieval_indexes
Revises: 0006_schema_alignment
Create Date: 2026-06-08
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0007_add_retrieval_indexes"
down_revision = "0006_schema_alignment"
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_index("ix_documents_owner_soft_deleted", "documents", ["owner_id", "soft_deleted"], unique=False)
    except Exception:
        pass
    try:
        op.create_index("ix_documents_owner_id", "documents", ["owner_id"], unique=False)
    except Exception:
        pass
    try:
        op.create_index("ix_chunks_document_id", "chunks", ["document_id"], unique=False)
    except Exception:
        pass


def downgrade():
    for index_name in ("ix_chunks_document_id", "ix_documents_owner_id", "ix_documents_owner_soft_deleted"):
        try:
            op.drop_index(index_name, table_name="documents" if "documents" in index_name else "chunks")
        except Exception:
            pass
