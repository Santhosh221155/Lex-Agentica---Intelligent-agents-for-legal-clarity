from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
from typing import Callable


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        # Accept `Authorization: ApiKey <key>` or `x-api-key` header
        try:
            auth = request.headers.get("authorization", "")
            api_key = None
            if auth and auth.lower().startswith("apikey "):
                api_key = auth.split(" ", 1)[1].strip()
            elif "x-api-key" in request.headers:
                api_key = request.headers.get("x-api-key").strip()

            if api_key:
                # import lazily to avoid import cycles at startup
                try:
                    from app.api.keys import verify_api_key
                except Exception:
                    verify_api_key = None
                if verify_api_key:
                    try:
                        record = verify_api_key(api_key)
                        if record:
                            # attach API key record and tenancy to request.state
                            request.state.api_key = record
                            request.state.tenant_id = record.get("tenant_id")
                            request.state.workspace_id = record.get("workspace_id")
                            # synthetic identity for permission checks
                            request.state.authenticated_via = "api_key"
                            # normalized user shape expected by application code
                            api_key_id = record.get("id")
                            try:
                                api_key_id_int = int(api_key_id)
                            except Exception:
                                api_key_id_int = None
                            request.state.user = {
                                "id": 0,
                                "api_key_id": api_key_id_int,
                                "tenant_id": record.get("tenant_id"),
                                "workspace_id": record.get("workspace_id"),
                                "scopes": record.get("scopes"),
                                "is_admin": False,
                                "identity_type": "api_key",
                            }
                            request.state.auth_identity = request.state.user
                    except Exception:
                        # verification failed; proceed as unauthenticated
                        pass
        except Exception:
            # non-fatal middleware error should not block requests
            pass

        response: Response = await call_next(request)
        return response
