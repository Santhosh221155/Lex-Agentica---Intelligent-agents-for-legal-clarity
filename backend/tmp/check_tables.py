import os
import asyncio
from dotenv import load_dotenv
import asyncpg

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'), override=True)
url = os.getenv('DATABASE_URL')
print('DATABASE_URL', url)

async def main():
    conn = await asyncpg.connect(url)
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
