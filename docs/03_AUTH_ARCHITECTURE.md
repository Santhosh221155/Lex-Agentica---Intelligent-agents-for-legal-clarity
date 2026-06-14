**Authentication & Authorization**

Summary: The codebase supports session-based JWT auth and API key auth. Endpoints and auth helpers live under `backend/app/api` and middleware under `backend/app/middleware`.

Login / Registration Workflows:
- Routes implemented in [backend/app/api/auth.py](backend/app/api/auth.py#L1-L200): `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout`, `/api/auth/me`.
- Password verification and session creation are provided by `app.services.auth` (Not exhaustively traced here).

Session Management & JWT Flow:
- `create_access_token` and refresh token logic used in `login` and `refresh` flows. Tokens are validated in `get_current_user` helper in [backend/app/api/auth.py](backend/app/api/auth.py#L1-L200).

API Key Flow:
- Middleware `APIKeyAuthMiddleware` accepts `Authorization: ApiKey <key>` or `x-api-key` header and injects a synthetic `request.state.user`. See [backend/app/middleware/api_key_auth.py](backend/app/middleware/api_key_auth.py#L1-L120).
- API key verification backed by `app.api.keys` (module present) which stores API keys in DB table `api_keys` ([backend/app/models.py](backend/app/models.py#L1-L80)).

Role-Based Access Control:
- `is_admin` flag exists on `users` table. `get_admin_user` enforces admin role in routes ([backend/app/api/auth.py](backend/app/api/auth.py#L1-L200)).
- Fine-grained permission checks via `scopes` on API key records (stored JSON in `api_keys`). Specific RBAC enforcement points are present in route handlers where `get_current_user` / `get_admin_user` are used.

OAuth Flow: Not Found in Codebase

Token Refresh Flow: Implemented in `/api/auth/refresh` via session rotation in [backend/app/api/auth.py](backend/app/api/auth.py#L1-L200).

Sequence Diagrams: (Example: Login → Issue tokens → Use tokens)

```mermaid
sequenceDiagram
  participant User
  participant FE
  participant API
  User->>FE: Submit credentials
  FE->>API: POST /api/auth/login
  API->>DB: verify credentials (services.auth)
  API-->>FE: access_token + refresh_token
  Note right of API: access tokens are JWTs; refresh tokens stored in sessions table
```
