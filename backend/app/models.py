from sqlalchemy import Table, Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, BigInteger
from sqlalchemy.orm import registry
from sqlalchemy.sql import func

mapper_registry = registry()
metadata = mapper_registry.metadata

# Tenancy core
tenants = Table(
    "tenants",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(255), nullable=False, unique=True),
    Column("created_at", DateTime, server_default=func.now()),
)

workspaces = Table(
    "workspaces",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("name", String(255), nullable=False),
    Column("settings", JSON, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)

roles = Table(
    "roles",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("name", String(128), nullable=False),
    Column("permissions", JSON, nullable=True),
)

user_roles = Table(
    "user_roles",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("role_id", Integer, ForeignKey("roles.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
)

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=True),
    Column("username", String(64), nullable=False),
    Column("email", String(255), nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("is_admin", Boolean, server_default="0"),
    Column("created_at", DateTime, server_default=func.now()),
    Column("last_login", DateTime, nullable=True),
)

api_keys = Table(
    "api_keys",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=True),
    Column("key_hash", String(255), nullable=False),
    Column("scopes", JSON, nullable=True),
    Column("created_by", Integer, ForeignKey("users.id"), nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=True),
    Column("state", JSON, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Column("refresh_token_hash", String(255), nullable=True),
    Column("expires_at", DateTime, nullable=True),
    Column("revoked_at", DateTime, nullable=True),
)

documents = Table(
    "documents",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=False),
    Column("owner_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("title", String(255), nullable=False),
    Column("source_uri", String(1024), nullable=True),
    Column("version", String(64), nullable=True),
    Column("status", String(32), nullable=False, server_default="active"),
    Column("metadata", JSON, nullable=True),
    Column("soft_deleted", Boolean, server_default="0"),
    Column("uploaded_by", Integer, ForeignKey("users.id"), nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)

ingestion_jobs = Table(
    "ingestion_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("document_id", Integer, ForeignKey("documents.id"), nullable=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=True),
    Column("owner_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("status", String(32), nullable=False, server_default="queued"),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Column("completed_at", DateTime, nullable=True),
)

chunks = Table(
    "chunks",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("document_id", Integer, ForeignKey("documents.id"), nullable=False),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=False),
    Column("chunk_index", Integer, nullable=False),
    Column("page_number", Integer, nullable=True),
    Column("content", Text, nullable=False),
    Column("token_count", Integer, nullable=True),
    Column("metadata", JSON, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)

embeddings = Table(
    "embeddings",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("chunk_id", String(64), ForeignKey("chunks.id"), nullable=False),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=False),
    Column("vector_id", String(255), nullable=False),
    Column("model_name", String(255), nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)

document_audits = Table(
    "document_audits",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("document_id", Integer, ForeignKey("documents.id"), nullable=False),
    Column("actor_id", Integer, ForeignKey("users.id"), nullable=True),
    Column("action", String(64), nullable=False),
    Column("before", JSON, nullable=True),
    Column("after", JSON, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)

conversations = Table(
    "conversations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=False),
    Column("session_id", Integer, ForeignKey("sessions.id")),
    Column("user_message", Text),
    Column("assistant_response", Text),
    Column("created_at", DateTime, server_default=func.now()),
)

traces = Table(
    "traces",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=True),
    Column("session_id", Integer, ForeignKey("sessions.id")),
    Column("trace", JSON),
    Column("created_at", DateTime, server_default=func.now()),
)

retrieval_logs = Table(
    "retrieval_logs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=True),
    Column("session_id", Integer, ForeignKey("sessions.id")),
    Column("query", Text),
    Column("results", JSON),
    Column("latency_ms", Integer),
    Column("created_at", DateTime, server_default=func.now()),
)

memories = Table(
    "memories",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=True),
    Column("user_id", Integer, nullable=True),
    Column("kind", String(50)),
    Column("payload", JSON),
    Column("importance_score", Integer, nullable=True),
    Column("recency_score", Integer, nullable=True),
    Column("retrieval_score", Integer, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)

tools_history = Table(
    "tools_history",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=True),
    Column("session_id", Integer, ForeignKey("sessions.id")),
    Column("tool_name", String(128)),
    Column("input", JSON),
    Column("output", JSON),
    Column("success", Boolean),
    Column("created_at", DateTime, server_default=func.now()),
)

review_requests = Table(
    "review_requests",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=True),
    Column("trace_id", String(64), nullable=True),
    Column("session_id", Integer, ForeignKey("sessions.id"), nullable=True),
    Column("query", Text, nullable=False),
    Column("answer_draft", Text, nullable=True),
    Column("confidence_score", String(16), nullable=True),
    Column("threshold", String(16), nullable=True),
    Column("status", String(32), nullable=False, server_default="pending"),
    Column("reviewer_id", Integer, ForeignKey("users.id"), nullable=True),
    Column("reviewer_notes", Text, nullable=True),
    Column("audit_log", JSON, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Column("decided_at", DateTime, nullable=True),
)

reflection_logs = Table(
    "reflection_logs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=True),
    Column("trace_id", String(64), nullable=True),
    Column("session_id", Integer, ForeignKey("sessions.id"), nullable=True),
    Column("query", Text, nullable=False),
    Column("answer_draft", Text, nullable=True),
    Column("critique", JSON, nullable=True),
    Column("revised_answer", Text, nullable=True),
    Column("confidence_score", String(16), nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)

evaluation_runs = Table(
    "evaluation_runs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=True),
    Column("name", String(255), nullable=False),
    Column("dataset_name", String(255), nullable=True),
    Column("config", JSON, nullable=True),
    Column("summary", JSON, nullable=True),
    Column("created_by", Integer, ForeignKey("users.id"), nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)

evaluation_records = Table(
    "evaluation_records",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", Integer, ForeignKey("evaluation_runs.id"), nullable=False),
    Column("question", Text, nullable=False),
    Column("retrieved_context", JSON, nullable=True),
    Column("answer", Text, nullable=True),
    Column("metrics", JSON, nullable=True),
    Column("latencies", JSON, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)

audit_logs = Table(
    "audit_logs",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Integer, ForeignKey("workspaces.id"), nullable=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=True),
    Column("action", String(128), nullable=False),
    Column("resource_type", String(128), nullable=True),
    Column("resource_id", String(255), nullable=True),
    Column("details", JSON, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)
