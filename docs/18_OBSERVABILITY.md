**Observability**

Logging & Metrics:
- Observability helpers under `backend/app/observability.py` (used to record events, token usage, agent latencies).
- Prometheus metrics optionally exposed at `/metrics` when `prometheus_client` installed (mounted in `backend/app/main.py`).

Tracing:
- `ObservabilityMiddleware` injects `X-Trace-Id` and logs request lifecycle events. OpenTelemetry initialization attempted on startup if available.

Alerting: Not Found in Codebase: alerting rules or external integrations.

Traces & Token Accounting:
- `synthesizer` records token counts via `record_token_usage` and traces persisted to `traces` table for later inspection.
