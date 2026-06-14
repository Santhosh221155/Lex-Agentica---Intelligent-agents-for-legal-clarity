import os
import sys
from pathlib import Path
import asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.models import metadata
from app.services.database_utils import resolve_database_urls


def _load_env():
    repo_root = Path(__file__).resolve().parents[2]
    backend_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env", override=True)
    load_dotenv(backend_root / ".env", override=True)


async def main():
    _load_env()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set in .env")

    db_config = resolve_database_urls(database_url)
    async_url = db_config["async_url"]
    connect_args = db_config["connect_args"]

    print(f"Connecting to database with backend={db_config['backend']}...")
    engine = create_async_engine(async_url, future=True, connect_args=connect_args)

    async with engine.begin() as conn:
        print("Creating missing tables from metadata...")
        await conn.run_sync(metadata.create_all)
        print("Metadata create_all executed.")

    print("Schema ensure complete.")


if __name__ == "__main__":
    asyncio.run(main())
