"""add password_hash to users
Revision ID: 0002_add_password_hash
Revises: 0001_create_tables
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_password_hash'
down_revision = '0001_create_tables'
branch_labels = None
depends_on = None


def upgrade():
    # No-op: password_hash column removed as authentication is disabled
    pass


def downgrade():
    # No-op
    pass
