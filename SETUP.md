# Local Setup Guide

This project is designed to run locally on Windows with PowerShell.

## Prerequisites
- Python 3.11 or newer
- Node.js 18 or newer
- Postgres (optional, for persistent data)
- Redis (optional, for caching)
- A virtual environment at the repo root: `.venv`

## Environment Variables
Copy `.env.example` to `.env` and configure the values you need:

### Required
- `GROQ_API_KEY`: Your Groq API key for LLM calls
- `SECRET_KEY`: Secure secret for JWT signing

### Optional but Recommended
- `ENABLE_SENTENCE_TRANSFORMERS=1`: Enables local sentence-transformers embeddings (no OpenAI key required)
- `DATABASE_URL`: PostgreSQL connection string (or use local SQLite: `sqlite+aiosqlite:///backend/tmp/agentic_rag_dev.db`)
- `REDIS_URL`: Redis connection string for caching
- `EMBEDDING_MODEL`: Sentence-transformers model to use (default: all-MiniLM-L6-v2)
- `HF_TOKEN`: Hugging Face token for model downloads (if needed)

### Local Development
- `DISABLE_AUTH=1`: Skips JWT authentication for local development
- `NEXT_PUBLIC_DISABLE_AUTH=1`: Skips frontend login gate
- `NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000`: Frontend backend URL

Example:
```powershell
# Copy env file
Copy-Item .env.example .env

# Edit .env with your API keys
# Then set (optional) environment variables in your shell
$env:GROQ_API_KEY="your_groq_key_here"
$env:ENABLE_SENTENCE_TRANSFORMERS="1"
```

## Backend Setup
From the repo root:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd backend
alembic upgrade head
```

Start the backend:
```powershell
cd ..
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend Setup
In a second terminal:
```powershell
cd frontend
npm install
npm run dev
```

The console runs on `http://localhost:3000` and talks to the backend at `NEXT_PUBLIC_BACKEND_URL`.

## Health Checks
Once the backend is up, verify it with:
```powershell
python scripts/check_backend_core.py
```

For a query smoke test:
```powershell
python scripts/smoke_test_backend.py
```

## Notes
- The backend includes safe fallbacks when Redis, Qdrant, Postgres, or Prometheus are unavailable.
- `alembic upgrade head` should be run from the `backend` directory.
- If you want live embeddings, set `ENABLE_SENTENCE_TRANSFORMERS=1`.
