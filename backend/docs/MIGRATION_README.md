Migration instructions — multi-tenant migration

Prerequisites
- A running PostgreSQL instance and a valid `DATABASE_URL` environment variable used by your `backend` app and Alembic config.
- Your virtualenv with project dependencies activated.

Steps

1) From the repository `backend` directory, run:

```bash
cd "d:\My projects\Self Healing RAG\backend"
.\.venv\Scripts\Activate.ps1   # or activate your venv
export DATABASE_URL=postgresql://user:pass@host:5432/dbname  # or set in PowerShell
venv\Scripts\python -m alembic upgrade head
```

2) Verify new tables exist (`tenants`, `workspaces`, `api_keys`, `audit_logs`) and that `documents`, `chunks`, and `embeddings` include `tenant_id` and `workspace_id` columns.

Notes
- The provided migration `0005_multi_tenancy.py` is best-effort: if your DB already differs, the migration will skip failing column adds to avoid blocking. Review the migration before running in production.
- Run migrations on a staging DB first.
