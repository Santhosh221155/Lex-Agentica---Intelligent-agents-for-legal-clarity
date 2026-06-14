"""create core tables
Revision ID: 0001_create_tables
Revises: 
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_create_tables'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # users table intentionally omitted in this deployment

    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, nullable=True),
        sa.Column('state', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('session_id', sa.Integer, sa.ForeignKey('sessions.id')),
        sa.Column('user_message', sa.Text()),
        sa.Column('assistant_response', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'traces',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('session_id', sa.Integer, sa.ForeignKey('sessions.id')),
        sa.Column('trace', sa.JSON()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'retrieval_logs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('session_id', sa.Integer, sa.ForeignKey('sessions.id')),
        sa.Column('query', sa.Text()),
        sa.Column('results', sa.JSON()),
        sa.Column('latency_ms', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'memories',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, nullable=True),
        sa.Column('type', sa.String(length=50)),
        sa.Column('content', sa.JSON()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'tools_history',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('session_id', sa.Integer, sa.ForeignKey('sessions.id')),
        sa.Column('tool_name', sa.String(length=128)),
        sa.Column('input', sa.JSON()),
        sa.Column('output', sa.JSON()),
        sa.Column('success', sa.Boolean()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('tools_history')
    op.drop_table('memories')
    op.drop_table('retrieval_logs')
    op.drop_table('traces')
    op.drop_table('conversations')
    op.drop_table('sessions')
