"""document management tables
Revision ID: 0004_document_management
Revises: 0003_add_auth_tables
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0004_document_management"
down_revision = "0003_add_auth_tables"
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    return inspect(bind).has_table(table_name)


def upgrade():
    if not _table_exists("documents"):
        op.create_table(
            "documents",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("source", sa.String(length=255), nullable=True),
            sa.Column("upload_time", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )

    if not _table_exists("ingestion_jobs"):
        op.create_table(
            "ingestion_jobs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id"), nullable=True),
            sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )

    if not _table_exists("chunks"):
        op.create_table(
            "chunks",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("chunk_index", sa.Integer, nullable=False),
            sa.Column("page_number", sa.Integer, nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )

    if not _table_exists("embeddings"):
        op.create_table(
            "embeddings",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("chunk_id", sa.String(length=64), sa.ForeignKey("chunks.id"), nullable=False),
            sa.Column("vector_reference", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )

    if not _table_exists("document_audits"):
        op.create_table(
            "document_audits",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("before", sa.JSON(), nullable=True),
            sa.Column("after", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade():
    op.drop_table("document_audits")
    op.drop_table("embeddings")
    op.drop_table("chunks")
    op.drop_table("ingestion_jobs")
    op.drop_table("documents")
