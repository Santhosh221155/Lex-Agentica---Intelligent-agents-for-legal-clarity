# Backend — Migrations & Setup

## Applying migrations (Alembic)

Ensure `alembic` is installed in your environment (pip install alembic).

Set `DATABASE_URL` in your environment (see `.env.example`). Then run:

```powershell
cd backend
python scripts/apply_migrations.py
```

This will attempt to run alembic programmatically. If alembic fails, the script falls back to `metadata.create_all`.
