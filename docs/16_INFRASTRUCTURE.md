**Infrastructure Architecture**

Note: User requested to ignore Docker specifics; this document focuses on runtime architecture and optional infra components.

Runtime components:
- FastAPI backend (single service) — hosts HTTP endpoints, SSE streams, and orchestrates agents.
- Postgres: primary metadata and audit store.
- Redis: caching and rate-limit counters.
- Vector DB: Chroma (local) or Qdrant (managed) for vector search.
- External LLM provider: Groq/OpenAI-compatible streaming endpoints (configurable via env vars GROQ_API_URL / GROQ_API_KEY).

Networking & Secrets:
- Services communicate over internal network; connection strings provided via environment variables and `.env`.

Storage & Persistence:
- Postgres for relational data; vector DB stores persistent vectors; Chroma persist directory default under backend/chroma_db.

Queues & Background:
- Ingestion and long-running tasks are implemented as background jobs and async tasks; ingestion jobs persisted in `ingestion_jobs` table.
