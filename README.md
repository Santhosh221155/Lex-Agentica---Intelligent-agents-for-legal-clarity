# Agentic RAG — Legal Document Intelligence Platform (Local Prototype)

This repository is a local, production-oriented prototype of an Agentic Retrieval-Augmented-Generation (RAG) platform specialized for Legal Document Intelligence (example domain). It demonstrates an architecture where multiple autonomous agents plan, retrieve, tool, validate, and synthesize answers with observability and production practices.

## ✨ Key Enhancements (End-User Assistant Mode)
The system has been updated from a "document analyst" debugging tool to a clean, natural end-user assistant:
- **No more document/excerpt/citation references**: LLM responses are human-readable and direct
- **Sensitive request blocking**: Passwords, secrets, tokens, API keys, and credentials are blocked upfront
- **Enhanced prompt injection defense**: Multi-layer pattern matching with Unicode normalization and homoglyph handling
- **Improved response sanitization**: Removes filenames, page numbers, chunk references, and retrieval metadata automatically
- **Natural, concise answers**: No more "According to the document..." or "The excerpt mentions..." phrasing

## 🏛️ Architecture Highlights
- **Multi-agent workflow**: Planner, Retrieval, Memory, Tool, Validator, Synthesizer (fully implemented!)
- **Post-synthesis reflection and human review gating**: Low-confidence runs trigger human review
- **Metadata-aware retrieval filters**: Document-based filtering with cross-encoder reranking
- **Evaluation persistence**: RAGAS-style and DeepEval-style metrics tracking
- **LangGraph orchestration**: Full implementation with conditional routing and parallel execution
- **Data storage**: ChromaDB for embeddings, Redis for caching, PostgreSQL for persistent relational data
- **Backend**: FastAPI with streaming synthesizer endpoint
- **Frontend**: Next.js AI Ops Console with trace panel and streaming responses
- **Observability**: Prometheus metrics, request trace IDs, structured logging, and health dashboards

## 🚀 Local Setup

Use [SETUP.md](SETUP.md) for the full local setup guide, including environment variables, database configuration, backend startup, and frontend startup.

For a quick start on Windows, you can use the scripts in `scripts/`:
```powershell
.\scripts\start_backend.ps1
```

```powershell
.\scripts\start_frontend.ps1
```

```powershell
.\scripts\start_all.ps1
```

### Manual Backend Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd backend
alembic upgrade head
cd ..
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## 📋 Environment Variables
Copy `.env.example` to `.env` and configure the following key variables:
- `ENABLE_SENTENCE_TRANSFORMERS=1`: Enables local sentence-transformers embeddings (no OpenAI key required)
- `GROQ_API_KEY`: Your Groq API key for LLM calls
- `DATABASE_URL`: PostgreSQL connection string (or use local SQLite for development)
- `REDIS_URL`: Redis connection string for caching
- `SECRET_KEY`: Secure secret for JWT signing
- `DISABLE_AUTH=1`: Skips authentication for local development

## 🛠️ Key Features Implemented
1. **Agents**: Planner, Retrieval, Tool, Memory, Validator, Synthesizer
2. **Orchestration**: LangGraph-based workflow with conditional routing
3. **Security**:
   - Multi-layer prompt injection detection
   - Sensitive request blocking (passwords, secrets, API keys)
   - Query/response sanitization
   - Rate limiting
4. **Observability**:
   - Prometheus metrics endpoint (`/metrics`)
   - `X-Trace-Id` response headers
   - Structured JSON logging
   - Dashboards for pipeline health and evaluations
5. **Ingestion**: Document upload and processing pipeline
6. **Frontend**: Next.js AI Ops Console with streaming UI and trace views

## 📚 Documentation
- [SETUP.md](SETUP.md): Detailed local setup guide
- [ARCHITECTURE.md](ARCHITECTURE.md): System architecture overview
- [docs/](docs/): In-depth technical documentation covering:
  - Project overview
  - System architecture
  - Agent architecture
  - RAG pipeline
  - Ingestion pipeline
  - Database schema
  - Authentication
  - Security architecture
  - Observability
  - [Answer Generation Quality Standards](docs/21_ANSWER_GENERATION_QUALITY.md): Guidelines for response style, content restrictions, and prompt injection handling
  - And more!

## 🧪 Testing
Run backend tests from the `backend/` directory:
```powershell
cd backend
python -m unittest discover -s tests -v
```

## 📈 Project Status
✅ Production-ready core features implemented
✅ End-user assistant mode active
✅ Observability and security features in place
✅ Local development setup complete
