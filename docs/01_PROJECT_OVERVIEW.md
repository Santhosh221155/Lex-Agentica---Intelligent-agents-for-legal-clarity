**Project Overview**

- **Name**: Agentic RAG - Legal Document Intelligence Platform
- **Purpose**: Provide an agentic Retrieval-Augmented Generation (RAG) platform that answers user queries grounded in uploaded documents and indexed knowledge for legal document intelligence scenarios.
- **Problem Solved**: Enables teams to ingest domain documents, index them into vector stores, and run agentic workflows that retrieve evidence, synthesize grounded answers, and route items for human review when confidence is low.
- **Core Business Objective**: Reduce time-to-insight from enterprise documents while minimizing hallucinations and providing audit trails and human-in-the-loop review for high-risk answers.
- **Intended Users**: Data analysts, compliance teams, security reviewers, and internal knowledge workers who need precise, evidence-backed answers from internal documents.
- **Key Capabilities**:
  - Document ingestion, chunking and embedding.
  - Hybrid retrieval (dense + BM25) with reranking.
  - Agentic planner and modular agents (retrieval, tools, memory, validator, synthesizer).
  - Streaming synthesis with provenance and human review gating.
  - Multi-tenant aware DB schema and API key authentication.
  - **End-User Assistant Mode**: Clean, natural answers with no document citations, filenames, or internal metadata.
  - **Sensitive Request Blocking**: Blocks requests for passwords, secrets, tokens, API keys, and credentials.

**High-level System Summary**

- Backend: FastAPI Python service that orchestrates planning, retrieval, tools, memory, validation and synthesis. See [backend/app/main.py](backend/app/main.py#L1-L80).
- Agents: Implemented as modular Python agents under [backend/app/agents/](backend/app/agents/). Core agents include `planner`, `retrieval`, `validator`, `synthesizer`, and tool agents.
- Storage: Postgres (SQLAlchemy) used for primary metadata and traces; optional vector stores supported (Chroma, Qdrant). See [backend/app/models.py](backend/app/models.py#L1-L80) and [backend/app/services/db.py](backend/app/services/db.py#L1-L80).
- Frontend: Next.js + TypeScript single-page UI (folder `frontend/`) that streams answers and displays provenance and review workflows.

**Major Modules**

- `backend/app`: API, agents, services (ingestion, document store, reranker), clients (qdrant, redis), observability.
- `frontend`: UI pages and components for querying, review, and workspace management.
- `langgraph/`: orchestration executor used to run agent plans.

**Technology Stack Overview**

- Language: Python 3.x (backend), TypeScript (frontend)
- Web framework: FastAPI
- DB: PostgreSQL (async via asyncpg + SQLAlchemy)
- Cache: Redis (async)
- Vector DBs: Chroma (default) and optional Qdrant integration
- Embeddings / LLMs: Embedding providers via `langchain_openai` or local sentence-transformers; LLM calls use Groq/OpenAI-compatible streaming endpoints (configurable via env).
- Frontend: Next.js, React, Tailwind CSS

**Files to inspect for details**: [backend/app/main.py](backend/app/main.py#L1-L120), [backend/app/agents/planner.py](backend/app/agents/planner.py#L1-L80), [backend/app/models.py](backend/app/models.py#L1-L80)
