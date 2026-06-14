import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.db import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT id, status, error, owner_id, tenant_id, workspace_id FROM ingestion_jobs ORDER BY id DESC LIMIT 1")
        )
        row = result.mappings().first()
        print(dict(row) if row else {})


asyncio.run(main())
