import os
import asyncio
from urllib.parse import urlparse, parse_qsl, urlunparse
from dotenv import load_dotenv
import asyncpg

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'), override=True)
raw_url = os.getenv('DATABASE_URL')
print('raw DATABASE_URL', raw_url)
parsed = urlparse(raw_url)
query = dict(parse_qsl(parsed.query, keep_blank_values=True))
sslmode = query.pop('sslmode', None)
parsed = parsed._replace(scheme='postgresql', query='')
async_url = urlunparse(parsed)
print('asyncpg DSN', async_url, 'sslmode', sslmode)

async def main():
    conn = await asyncpg.connect(async_url, ssl='require' if sslmode == 'require' else None)
    try:
        print('connected')
        names = ['users', 'sessions', 'tenants', 'workspaces']
        for name in names:
            res = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=$1)",
                name,
            )
            print(name, res)
        tbls = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        print('tables', [r['table_name'] for r in tbls])
    finally:
        await conn.close()

asyncio.run(main())
