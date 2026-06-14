**Project Technical DNA**

Complete Architecture Summary:
- Monolithic FastAPI backend orchestrates agentic RAG workflows executed via LangGraph. Agents are modular Python components that perform retrieval, tool execution, memory operations, validation and synthesis.

Component Map:
- `backend/app/main.py` — HTTP surface, middleware, orchestration entry points.
- `backend/app/agents/*` — planner, retrieval, validator, synthesizer, tool agent, memory.
- `backend/app/services/*` — DB access, document store, reranker, ingestion helpers.
- `frontend/` — Next.js UI components and pages for streaming interactions.

Request Flow:
- Incoming request -> auth & rate limiting -> planner -> langgraph executor -> agents -> synthesizer stream -> response.

Data Flow:
- Documents uploaded -> chunked -> embeddings -> stored in vector DB and DB tables -> retrieval uses both vector DB and BM25 over chunks -> rerank -> synth.

Agent Flow: See `07_AGENT_ARCHITECTURE.md` and `08_AGENT_WORKFLOWS.md`.

RAG Flow: Hybrid dense + sparse with RRF fusion and optional cross-encoder reranker. Validator enforces evidence overlap and human review gating.

Security Flow: JWT + API keys, rate-limiting, prompt-injection middleware, audit logs.

Key Design Decisions & Tradeoffs:
- Hybrid retrieval (dense + BM25) to improve recall for user-owned documents.
- Deterministic validator rather than purely learned verifier to keep predictable review gating.
- Streaming synthesizer to support low-latency progressive UX.

Limitations & Not Found items:
- No explicit CI/CD manifests in repo.
- No external secrets manager integration.
- Some ingestion internals and chunking algorithm locations are not explicitly surfaced (search for `ingest` scripts if needed).

Future Enhancements:
- Add managed vector DB support and autoscaling policies.
- Add CI/CD pipelines and IaC manifests.
- Implement configurable retention/TTL policies for traces and memories.
