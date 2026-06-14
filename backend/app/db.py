
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine
from typing import Iterator
from .config import settings
from .services.database_utils import resolve_database_urls

# --- Lazy-loaded variables ---
_initialized = False
DATABASE_CONFIG = None
engine: Engine = None
SessionLocal = None


def _initialize_db(force: bool = False):
    global _initialized, DATABASE_CONFIG, engine, SessionLocal
    if _initialized and not force:
        return
    DATABASE_CONFIG = resolve_database_urls(settings.DATABASE_URL, check_reachable=False)
    engine = create_engine(str(DATABASE_CONFIG["sync_url"]), future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    _initialized = True


def get_db() -> Iterator:
    _initialize_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

