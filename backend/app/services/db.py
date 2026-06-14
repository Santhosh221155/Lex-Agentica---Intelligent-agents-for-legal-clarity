
import os
import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.models import metadata
from .database_utils import resolve_database_urls

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(override=True)


# --- Lazy-loaded variables ---
_initialized = False
DATABASE_URL = None
DATABASE_CONFIG = None
DATABASE_CONNECT_ARGS = None
DATABASE_BACKEND = None
DATABASE_AVAILABLE = None
DATABASE_FALLBACK_TO_SQLITE = None
REQUIRED_TABLES = ("tenants", "workspaces", "users", "sessions")
engine = None
AsyncSessionLocal = None


def _make_dummy_session_factory():
    class _DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *args, **kwargs):
            raise RuntimeError("database_unavailable")

        async def commit(self):
            raise RuntimeError("database_unavailable")

    def _factory():
        return _DummySession()

    return _factory


def _initialize_db(force: bool = False):
    global _initialized, DATABASE_URL, DATABASE_CONFIG, DATABASE_CONNECT_ARGS, DATABASE_BACKEND, DATABASE_AVAILABLE, DATABASE_FALLBACK_TO_SQLITE, engine, AsyncSessionLocal

    if _initialized and not force:
        return

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/agentic_rag")
    DATABASE_CONFIG = resolve_database_urls(DATABASE_URL, check_reachable=False)
    DATABASE_URL = str(DATABASE_CONFIG["async_url"])
    DATABASE_CONNECT_ARGS = dict(DATABASE_CONFIG["connect_args"])
    DATABASE_BACKEND = str(DATABASE_CONFIG["backend"])
    DATABASE_AVAILABLE = True
    DATABASE_FALLBACK_TO_SQLITE = bool(DATABASE_CONFIG.get("fallback", False))

    # Enforce SSL for asyncpg + Supabase (SNI requires SSL + full hostname)
    # Skip SSL for local connections (localhost/127.0.0.1)
    _is_local_host = any(h in DATABASE_URL for h in ("localhost", "127.0.0.1", "0.0.0.0"))
    if DATABASE_BACKEND == "postgres":
        if DATABASE_URL.startswith("postgresql+asyncpg"):
            if "ssl" not in DATABASE_CONNECT_ARGS:
                if _is_local_host:
                    DATABASE_CONNECT_ARGS["ssl"] = False
                    logger.info("Database SSL disabled (local connection)")
                else:
                    DATABASE_CONNECT_ARGS["ssl"] = "require"
                    logger.info("Database SSL enforcement enabled")

    try:
        logger.info("Initializing database engine (%s)", DATABASE_BACKEND)
        # Optimize connection pool for local dev
        engine_kwargs = {
            "future": True,
            "connect_args": DATABASE_CONNECT_ARGS,
            "pool_size": 10,  # Increased pool size
            "max_overflow": 20,  # Max additional connections
            "pool_timeout": 30,  # Wait up to 30s for connection
            "pool_recycle": 1800,  # Recycle connections after 30 mins
            "echo": False  # Disable SQL echoing
        }
        engine = create_async_engine(DATABASE_URL, **engine_kwargs)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        logger.info("Database engine ready")
    except ModuleNotFoundError as exc:
        # Missing async driver (e.g., aiosqlite, asyncpg)
        logger.error("Missing database driver: %s", exc.name)
        DATABASE_AVAILABLE = False
        AsyncSessionLocal = _make_dummy_session_factory()
    except Exception as exc:
        # Fall back to a dummy async session factory
        logger.error("Failed to create database engine: %s: %s", type(exc).__name__, exc)
        DATABASE_AVAILABLE = False
        AsyncSessionLocal = _make_dummy_session_factory()

    _initialized = True


def get_database_url() -> str:
    _initialize_db()
    return DATABASE_URL


def get_engine():
    _initialize_db()
    return engine


def get_session_factory():
    """Get the current database session factory.
    Ensures DB is initialized first.
    """
    _initialize_db()
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "Database not initialized. Ensure _initialize_db() was called during startup."
        )
    return AsyncSessionLocal


async def ensure_schema():
    _initialize_db()
    if DATABASE_BACKEND != "sqlite":
        return
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
    except Exception:
        return


async def database_status() -> str:
    """Return a coarse-grained Postgres availability signal."""
    _initialize_db()
    if not DATABASE_AVAILABLE:
        logger.info("Database unavailable")
        return "unavailable"
    if DATABASE_BACKEND == "sqlite":
        if DATABASE_FALLBACK_TO_SQLITE:
            logger.info("SQLite fallback active")
            return "fallback"
        logger.info("SQLite backend available")
        return "available"
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            if result is not None:
                missing = await _missing_required_tables()
                if missing:
                    logger.warning("Database schema incomplete: missing tables %s", ", ".join(missing))
                    return "schema_missing"
                logger.info("Database connection and schema verified")
                return "available"
    except Exception as exc:
        logger.warning("Database connection test failed: %s: %s", type(exc).__name__, exc)
        return "unavailable"
    return "unavailable"


async def get_session() -> AsyncSession:
    _initialize_db()
    async with AsyncSessionLocal() as session:
        yield session


async def _missing_required_tables() -> list[str]:
    _initialize_db()
    missing = []
    async with AsyncSessionLocal() as session:
        for table_name in REQUIRED_TABLES:
            result = await session.execute(
                text(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :table_name"
                ),
                {"table_name": table_name},
            )
            if result.scalar() is None:
                missing.append(table_name)
    return missing


async def verify_database_schema() -> bool:
    _initialize_db()
    if DATABASE_BACKEND != "postgres":
        logger.info("SQLite schema check skipped")
        return True

    if not DATABASE_AVAILABLE:
        logger.error("Database unavailable; cannot verify schema")
        return False

    try:
        missing = await _missing_required_tables()
        if missing:
            logger.error("Required database tables missing: %s", ", ".join(missing))
            return False
        logger.info("Required database tables are present")
        return True
    except Exception as exc:
        logger.error("Schema verification failed: %s", exc)
        return False


async def verify_database_connection() -> bool:
    """
    Test database connectivity at startup.
    For Postgres + Supabase, this verifies SNI is working correctly.
    Raises SystemExit if connection fails with actionable error message.
    """
    _initialize_db()
    if not DATABASE_AVAILABLE:
        logger.error("Database engine not available")
        return False
    
    if DATABASE_BACKEND == "sqlite":
        if DATABASE_FALLBACK_TO_SQLITE:
            logger.warning("Running with SQLite fallback")
            return
        logger.info("Using SQLite backend")
        return True

    try:
        logger.info("Verifying Postgres connection at startup")
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        if not await verify_database_schema():
            logger.error("Database is reachable but required schema is missing")
            raise RuntimeError("required database tables missing")
        logger.info("Database connection verified successfully")
        return True
    except Exception as exc:
        error_name = type(exc).__name__
        error_msg = str(exc)
        logger.error("Database connection failed: %s: %s", error_name, error_msg)
        raise RuntimeError(f"database connection verification failed: {error_name}: {error_msg}") from exc

