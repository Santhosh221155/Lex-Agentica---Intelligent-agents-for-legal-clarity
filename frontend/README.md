# Frontend (AI Ops Console) — Local Scaffold

This is the Next.js AI Ops Console for the Agentic RAG platform. It provides a dashboard-style interface for streaming answers, health checks, planning traces, retrieval evidence, validation output, and prompt presets.

```bash
cd frontend
npm install
npm run dev
```

By default the backend streaming endpoint is expected at `http://localhost:8000/api/stream-query`.
Set `NEXT_PUBLIC_BACKEND_URL` to override the backend host if needed.

The console polls `GET /healthz` and streams queries from `GET /api/stream-query`.
