# Enterprise Agentic RAG Platform — Architecture Overview

This document captures the Phase 1 architecture decisions mapped to the PROJECT CHARTER.

Goals (top priorities): Scalability, Security, Maintainability, Observability, Performance, Extensibility, Testability.

High-level components:
- Frontend: Next.js (TypeScript), TailwindCSS, shadcn/ui — frontend serves SaaS UI, streaming chat, and dashboards.
- API Gateway / Backend: FastAPI (Python 3.12), Pydantic, dependency injection, request/response middleware for auth, ratelimiting, and tracing.
- Database: PostgreSQL (logical multi-tenancy via tenant_id + workspace_id columns; single logical DB instance).
- Cache: Redis (sessions, rate limiting, ephemeral caches).
- Vector DB: Qdrant (logical namespaces + metadata filters).
- Embeddings / Models: Primary BGE-M3 for embeddings, BGE reranker, Gemini family for LLMs (external model endpoints).
- Observability: OpenTelemetry traces, Prometheus metrics, Grafana dashboards.

Agent pipeline (conceptual):
- Query Router → Planner → Tool Selector → Retrieval (hybrid: dense + sparse + RRF) → Reranker → Memory → Validator → Critic → Citation Verifier → Response Generator → Streaming

Security safeguards:
- JWT + refresh tokens; RBAC (roles + permissions) and workspace scoping.
- Prompt-injection scanner + chunk sanitization as middleware.
- Audit logging of all agent/tool actions and user interactions.

Next artifacts to produce (Phase 1 deliverables):
1. Detailed ER schema describing tenancy boundaries.
2. API surface contract for auth, workspaces, documents, ingestion, retrieval, agents, and evaluation.
3. Deployment & infra checklist (non-Docker): Postgres, Redis, Qdrant, model endpoints, OTel Collector, Prometheus.

Reference: follow the PROJECT CHARTER strictly; subsequent phases will implement concrete code and migrations.
