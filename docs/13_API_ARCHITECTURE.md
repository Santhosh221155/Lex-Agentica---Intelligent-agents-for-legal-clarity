**API Architecture**

Primary HTTP endpoints (overview):
- `GET /` : root health/info endpoint ([backend/app/main.py](backend/app/main.py#L1-L40)).
- `GET /healthz`, `GET /readyz` : readiness and health checks.
- `POST /api/query` : main query endpoint; requires authentication (`get_current_user`) and rate limiting.
- `GET /api/stream-query` : SSE streaming query endpoint.
- Authentication routes: `/api/auth/*` implemented in [backend/app/api/auth.py](backend/app/api/auth.py#L1-L200).
- Ingest endpoints: mounted under `/api/ingest` when present (see `backend/app/api/ingest.py` if available).

For each API route: consult file in `backend/app/api/` for request and response models. The main query endpoint uses `QueryRequest` and `QueryResponse` (see [backend/app/main.py](backend/app/main.py#L1-L120)).

Validation rules:
- `QueryRequest.query` length 1–4000 enforced by Pydantic.
- Auth enforced by `get_current_user` helper.
