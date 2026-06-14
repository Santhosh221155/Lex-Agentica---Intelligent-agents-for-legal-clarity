"""ai ops governance tables
Revision ID: 0005_ai_ops_governance
Revises: 0004_document_management
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_ai_ops_governance"
down_revision = "0004_document_management"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer_draft", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.String(length=16), nullable=True),
        sa.Column("threshold", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reviewer_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("audit_log", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "reflection_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer_draft", sa.Text(), nullable=True),
        sa.Column("critique", sa.JSON(), nullable=True),
        sa.Column("revised_answer", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dataset_name", sa.String(length=255), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "evaluation_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("evaluation_runs.id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("retrieved_context", sa.JSON(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("latencies", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("evaluation_records")
    op.drop_table("evaluation_runs")
    op.drop_table("reflection_logs")
    op.drop_table("review_requests")
