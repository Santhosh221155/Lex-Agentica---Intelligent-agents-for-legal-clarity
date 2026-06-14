**Documentation README**

Table of Contents:
- 01_PROJECT_OVERVIEW.md
- 02_SYSTEM_ARCHITECTURE.md
- 03_AUTH_ARCHITECTURE.md
- 04_DATABASE_ARCHITECTURE.md
- 05_INGESTION_PIPELINE.md
- 06_RAG_PIPELINE.md
- 07_AGENT_ARCHITECTURE.md
- 08_AGENT_WORKFLOWS.md
- 09_TOOL_CALLING.md
- 10_MEMORY_ARCHITECTURE.md
- 11_SECURITY_ARCHITECTURE.md
- 12_GOVERNANCE.md
- 13_API_ARCHITECTURE.md
- 14_FRONTEND_ARCHITECTURE.md
- 15_EVENT_FLOW.md
- 16_INFRASTRUCTURE.md
- 17_DEPLOYMENT.md
- 18_OBSERVABILITY.md
- 19_SCALABILITY.md
- 20_PROJECT_TECHNICAL_DNA.md
- 21_ANSWER_GENERATION_QUALITY.md
- 22_llm_prompts.md

Documentation Structure & Reading Order:
1. Start with `01_PROJECT_OVERVIEW.md` for goals and high-level summary.
2. Read `02_SYSTEM_ARCHITECTURE.md` and `20_PROJECT_TECHNICAL_DNA.md` for architecture and decision context.
3. Read `03_AUTH_ARCHITECTURE.md`, `11_SECURITY_ARCHITECTURE.md`, and `04_DATABASE_ARCHITECTURE.md` for security & data model.
4. Read pipelines and agents: `05_INGESTION_PIPELINE.md`, `06_RAG_PIPELINE.md`, `07_AGENT_ARCHITECTURE.md`, `08_AGENT_WORKFLOWS.md`.
5. Operational docs: `16_INFRASTRUCTURE.md`, `17_DEPLOYMENT.md`, `18_OBSERVABILITY.md`, `19_SCALABILITY.md`.

Quick Start For New Developers:

- Setup virtualenv and install requirements: see `requirements.txt`.
- Populate `.env` with database and API keys; `backend/app/main.py` loads `.env` at startup.
- Start backend dev server (example):

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

- Start frontend dev server inside `frontend/` using `npm run dev` or `pnpm` depending on package manager.

Notes & Next Steps:
- This documentation was produced by static analysis of repository files. Where implementation evidence was not found, the documents explicitly note "Not Found in Codebase".
