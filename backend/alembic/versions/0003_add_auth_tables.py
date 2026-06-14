"""add auth users and session fields
Revision ID: 0003_add_auth_tables
Revises: 0002_add_password_hash
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_add_auth_tables"
down_revision = "0002_add_password_hash"
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


def _fk_exists(table_name, fk_name=None, referred_table=None):
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(table_name):
        return False
    for fk in inspector.get_foreign_keys(table_name):
        if fk_name and fk.get("name") == fk_name:
            return True
        if referred_table and fk.get("referred_table") == referred_table:
            return True
    return False


def upgrade():
    if not _table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("username", sa.String(length=64), nullable=False, unique=True),
            sa.Column("email", sa.String(length=255), nullable=False, unique=True),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("is_admin", sa.Boolean(), server_default="0"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("last_login", sa.DateTime(), nullable=True),
        )

    if not _column_exists("sessions", "refresh_token_hash"):
        op.add_column("sessions", sa.Column("refresh_token_hash", sa.String(length=255), nullable=True))
    if not _column_exists("sessions", "expires_at"):
        op.add_column("sessions", sa.Column("expires_at", sa.DateTime(), nullable=True))
    if not _column_exists("sessions", "revoked_at"):
        op.add_column("sessions", sa.Column("revoked_at", sa.DateTime(), nullable=True))
    if not _fk_exists("sessions", fk_name="fk_sessions_user_id", referred_table="users"):
        op.create_foreign_key("fk_sessions_user_id", "sessions", "users", ["user_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_sessions_user_id", "sessions", type_="foreignkey")
    op.drop_column("sessions", "revoked_at")
    op.drop_column("sessions", "expires_at")
    op.drop_column("sessions", "refresh_token_hash")
    op.drop_table("users")
