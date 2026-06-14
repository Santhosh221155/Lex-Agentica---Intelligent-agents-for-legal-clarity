"""merge_governance_and_retrieval_branches

Revision ID: 0008_merge
Revises: 0005_ai_ops_governance, 0007_add_retrieval_indexes
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_merge"
down_revision = ("0005_ai_ops_governance", "0007_add_retrieval_indexes")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
