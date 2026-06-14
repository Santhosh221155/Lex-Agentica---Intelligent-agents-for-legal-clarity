from typing import Optional

from app.services.db import get_session_factory
from app.models import tools_history


async def log_tool_execution(session_id: Optional[int], tool_name: str, input_payload: dict, output: dict, success: bool):
    try:
        SessionLocal = get_session_factory()
        async with SessionLocal() as session:
            stmt = tools_history.insert().values(
                session_id=session_id,
                tool_name=tool_name,
                input=input_payload,
                output=output,
                success=success,
            )
            await session.execute(stmt)
            await session.commit()
    except Exception:
        return
