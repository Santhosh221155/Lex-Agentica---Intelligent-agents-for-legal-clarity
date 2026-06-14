import os
import socket
import ssl
import logging
from pathlib import Path
from typing import Dict, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from functools import lru_cache

logger = logging.getLogger(__name__)


def _mask_database_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.password or parsed.username:
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        if parsed.username:
            netloc = f"{parsed.username}:***@{netloc}"
        return urlunparse(parsed._replace(netloc=netloc))
    return raw_url


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _sqlite_db_path() -> Path:
    db_dir = _repo_root() / "backend" / "tmp"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "agentic_rag_dev.db"


def _normalize_postgres_async_url(raw_url: str) -> Tuple[str, dict]:
    parsed = urlparse(raw_url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    sslmode = query_items.pop("sslmode", None)
    normalized_url = urlunparse(parsed._replace(query=urlencode(query_items)))

    connect_args = {}
    if sslmode == "require":
        # For Supabase + SNI to work correctly with asyncpg, use ssl="require"
        # This string value is simpler and more reliable than custom SSL contexts
        connect_args["ssl"] = "require"
        logger.debug("SSL mode 'require' extracted from URL and set in connect_args")

    # Supabase pooler/pgbouncer does not support asyncpg prepared statements reliably.
    # Disabling the statement cache avoids DuplicatePreparedStatementError at startup.
    connect_args["statement_cache_size"] = 0

    return normalized_url, connect_args


def _normalize_postgres_sync_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    scheme = parsed.scheme
    if scheme.startswith("postgresql+asyncpg"):
        scheme = "postgresql+psycopg2"
    elif scheme == "postgresql":
        scheme = "postgresql+psycopg2"
    return urlunparse(parsed._replace(scheme=scheme))


@lru_cache(maxsize=1)
def _postgres_reachable(parsed) -> bool:
    """Try to reach Postgres via direct connection, then pooler connection."""
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    
    # List of connection attempts: (test_host, test_port, description)
    attempts = [(host, port, f"direct connection")]
    
    # If using Supabase pooler, also try the direct connection as fallback
    if "pooler.supabase.com" in host:
        # Add the direct connection as secondary attempt
        project_ref = host.split(".")[0]  # e.g., "aws-1-ap-southeast-2" -> extract project
        direct_host = f"db.{project_ref}.supabase.co" if not host.startswith("db.") else host
        if direct_host != host:
            attempts.append((direct_host, 5432, "Supabase direct connection fallback"))
    
    last_error = None
    for attempt_host, attempt_port, attempt_desc in attempts:
        logger.debug(f"Testing {attempt_desc}: {attempt_host}:{attempt_port}")
        try:
            addrinfos = socket.getaddrinfo(attempt_host, attempt_port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            logger.debug(f"  ✗ DNS lookup failed for {attempt_host}:{attempt_port} — {type(e).__name__}: {e}")
            last_error = e
            continue
        except Exception as e:
            logger.debug(f"  ✗ Unexpected error during getaddrinfo: {type(e).__name__}: {e}")
            last_error = e
            continue

        for family, socktype, proto, _, sockaddr in addrinfos:
            try:
                with socket.socket(family, socktype, proto) as sock:
                    sock.settimeout(3)  # Short timeout for connectivity test
                    sock.connect(sockaddr)
                    logger.info(f" Postgres reachable at {attempt_host}:{attempt_port} ({attempt_desc})")
                    return True
            except socket.timeout:
                logger.debug(f"  ✗ Connection timeout for {sockaddr} (timeout=3s)")
                last_error = socket.timeout("connection timed out")
            except ConnectionRefusedError as e:
                logger.debug(f"  ✗ Connection refused for {sockaddr}")
                last_error = e
            except OSError as e:
                logger.debug(f"  ✗ OS error for {sockaddr} — {type(e).__name__}: {e}")
                last_error = e

    logger.warning(f"✗ Postgres unreachable at {host}:{port}")
    if last_error is not None:
        logger.debug(f"Last connection error: {type(last_error).__name__}: {last_error}")
    return False


def resolve_database_urls(raw_url: str, check_reachable: bool = False) -> Dict[str, object]:
    parsed = urlparse(raw_url)

    if parsed.scheme.startswith("sqlite"):
        logger.info(f"Using SQLite backend")
        sync_url = raw_url.replace("sqlite+aiosqlite", "sqlite")
        return {"backend": "sqlite", "async_url": raw_url, "sync_url": sync_url, "connect_args": {}}

    if parsed.scheme.startswith("postgresql"):
        if check_reachable and not _postgres_reachable(parsed):
            logger.warning(
                f"Postgres unreachable at {parsed.hostname}:{parsed.port or 5432}. "
                f"DATABASE_URL={_mask_database_url(raw_url)}. "
                "Possible causes: (1) Supabase project is paused, (2) Network blocks port 5432/6543, "
                "(3) Incorrect .env DATABASE_URL. Falling back to SQLite."
            )
            sqlite_path = _sqlite_db_path().as_posix()
            async_url = f"sqlite+aiosqlite:///{sqlite_path}"
            sync_url = f"sqlite:///{sqlite_path}"
            return {
                "backend": "sqlite",
                "async_url": async_url,
                "sync_url": sync_url,
                "connect_args": {},
                "fallback": True,
            }

    async_url, connect_args = _normalize_postgres_async_url(raw_url)
    sync_url = _normalize_postgres_sync_url(raw_url)
    logger.info(f"Using Postgres backend at {parsed.hostname}:{parsed.port or 5432} with sslmode={'require' if 'sslmode=require' in raw_url else 'default'}")
    return {
        "backend": "postgres",
        "async_url": async_url,
        "sync_url": sync_url,
        "connect_args": connect_args,
        "fallback": False,
    }
