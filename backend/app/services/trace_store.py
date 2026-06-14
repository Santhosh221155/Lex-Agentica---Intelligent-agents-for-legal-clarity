from typing import Optional

from app.services.db import get_session_factory
from app.models import traces


async def save_trace(session_id: Optional[int], trace: dict, tenant_id: Optional[int] = None, workspace_id: Optional[int] = None):
    try:
        SessionLocal = get_session_factory()
        async with SessionLocal() as session:
            values = {"session_id": session_id, "trace": trace}
            if tenant_id is not None:
                values["tenant_id"] = tenant_id
            if workspace_id is not None:
                values["workspace_id"] = workspace_id
            stmt = traces.insert().values(**values)
            await session.execute(stmt)
            await session.commit()
    except Exception:
        return
