**Memory Architecture**

Memory types in the codebase:
- Short-Term / Conversation Memory: stored as `traces` and `conversations` rows to capture session context.
- Long-Term Memory: `memories` table stores payloads with importance/recency scores.
- Agent Memory: `tools_history`, `reflection_logs`, and `review_requests` capture agent interactions over time.

Storage locations:
- All memories persist in Postgres tables under `backend/app/models.py` (tables `memories`, `traces`, `conversations`).

Retention & Lifecycle:
- No explicit retention policy in code — retention is expected to be implemented via operational processes or migrations. (Not Found in Codebase: automated retention/TTL logic.)

Retrieval memory:
- `memory` agent step is expected to query `memories` and return context relevant to the plan. See references to `save_memory` in `backend/app/main.py`.
