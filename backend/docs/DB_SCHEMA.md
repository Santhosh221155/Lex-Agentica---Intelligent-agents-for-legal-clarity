# Database Schema Draft — Multi-tenant ER Overview

This draft lists core tables required by the PROJECT CHARTER. Every table includes `tenant_id` and where relevant `workspace_id`.

Core tables (brief):

- tenants
  - id (PK)
  - name
  - admin_user_id
  - created_at

- users
  - id (PK)
  - tenant_id (FK tenants.id)
  - email
  - password_hash
  - is_active
  - roles (relation to roles table)
  - created_at

- roles
  - id
  - tenant_id
  - name
  - permissions (jsonb)

- workspaces
  - id
  - tenant_id
  - name
  - settings (jsonb)

- api_keys
  - id
  - tenant_id
  - workspace_id
  - key_hash
  - scopes
  - created_by (user_id)

- documents
  - id
  - tenant_id
  - workspace_id
  - title
  - source_uri
  - metadata (jsonb)
  - version
  - soft_deleted (bool)
  - uploaded_by
  - created_at

- chunks
  - id
  - document_id (FK documents.id)
  - tenant_id
  - workspace_id
  - content
  - chunk_index
  - token_count
  - metadata (jsonb)

- embeddings
  - id
  - chunk_id (FK chunks.id)
  - tenant_id
  - workspace_id
  - vector_id (qdrant payload id)
  - model_name
  - created_at

- conversations
  - id
  - tenant_id
  - workspace_id
  - user_id
  - metadata

- messages
  - id
  - conversation_id
  - sender_type (user/system/agent)
  - content
  - created_at

- memories
  - id
  - tenant_id
  - workspace_id
  - kind (semantic/fact/short-term)
  - payload (jsonb)
  - importance_score
  - recency_score
  - retrieval_score

- agent_logs
  - id
  - tenant_id
  - workspace_id
  - trace_id
  - agent_name
  - step
  - input
  - output
  - latency_ms
  - created_at

- evaluations
  - id
  - tenant_id
  - workspace_id
  - metric_results (jsonb)
  - run_id
  - created_by

- audit_logs
  - id
  - tenant_id
  - workspace_id
  - user_id
  - action
  - resource_type
  - resource_id
  - details (jsonb)
  - created_at

Notes & constraints:
- All FK relationships should include tenant_id/workspace_id checks in application layer and DB constraints where practical.
- Use partial indexes on frequently queried metadata keys and on (tenant_id, workspace_id) for performance.
- Use JSONB for flexible metadata and to support multimodal representations (image descriptions, table extracts).

Next: generate complete SQLAlchemy models and Alembic migration scripts based on this draft.
