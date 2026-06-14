**Deployment & DevOps**

Build process & environment:
- Backend: Python package with dependencies listed in `requirements.txt`.
- Frontend: Next.js build via `frontend/package.json` scripts.

CI/CD: Not Found in Codebase: explicit CI/CD manifests (GitHub Actions, GitLab CI) are not present.

Release & Rollback:
- Releases expected to be containerized or deployed to Python hosting; rollback strategy not codified in repo (Not Found in Codebase).

Environments:
- Configuration via environment variables and `.env` loaded early in `backend/app/main.py`.
