import os
import asyncio
from dotenv import load_dotenv
import asyncpg
from urllib.parse import urlparse, parse_qsl, urlunparse

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'), override=True)
raw_url = os.getenv('DATABASE_URL')
if raw_url is None:
    raise SystemExit('DATABASE_URL not set')
parsed = urlparse(raw_url)
query = dict(parse_qsl(parsed.query, keep_blank_values=True))
sslmode = query.pop('sslmode', None)
parsed = parsed._replace(scheme='postgresql', query='')
async_url = urlunparse(parsed)
ssl_arg = 'require' if sslmode == 'require' else None
print('using asyncpg dsn:', async_url, 'ssl', ssl_arg)

async def main():
    conn = await asyncpg.connect(async_url, ssl=ssl_arg)
    try:
        print('current database version:')
        try:
            version = await conn.fetchval('SELECT version_num FROM alembic_version')
            print('alembic_version', version)
        except Exception as exc:
            print('alembic_version query failed:', type(exc).__name__, exc)
        rows = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
        print('tables:', [r['table_name'] for r in rows])
        for name in ['users','sessions','tenants','workspaces','api_keys','review_requests','reflection_logs']:
            res = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=$1)", name)
            print(name, res)
    finally:
        await conn.close()

asyncio.run(main())
