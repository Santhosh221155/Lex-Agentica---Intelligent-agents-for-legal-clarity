"""Utility to run Alembic migrations programmatically or create tables as fallback."""
import os
import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import command
from alembic.config import Config

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def _load_environment() -> None:
    if load_dotenv is None:
        return

    repo_root = Path(__file__).resolve().parents[2]
    backend_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env", override=True)
    load_dotenv(backend_root / ".env", override=True)


def run_alembic_upgrade():
    _load_environment()
    here = os.path.dirname(__file__)
    cfg = Config(os.path.join(here, '..', 'alembic.ini'))
    cfg.set_main_option('script_location', os.path.join(here, '..', 'alembic'))
    command.upgrade(cfg, 'heads')


if __name__ == '__main__':
    try:
        run_alembic_upgrade()
        print('Migrations applied (alembic).')
    except Exception as e:
        print('Alembic apply failed:', e)
        print('As fallback, creating tables via SQLAlchemy metadata...')
        try:
            import asyncio

            from app.models import metadata
            from app.services.db import engine

            async def _create_all() -> None:
                async with engine.begin() as conn:
                    await conn.run_sync(metadata.create_all)

            asyncio.run(_create_all())
            print('Tables created via metadata.create_all')
        except Exception as e2:
            print('Fallback failed:', e2)
            sys.exit(1)
