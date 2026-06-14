import asyncio
import os
import time

from app.services.document_store import list_user_chunks


async def main() -> None:
    os.environ["RETRIEVAL_BM25_EXPLAIN"] = "1"
    owner_id = 1
    t0 = time.time()
    rows = await list_user_chunks(owner_id)
    elapsed_ms = round((time.time() - t0) * 1000, 2)
    print(f"owner_id={owner_id} rows={len(rows)} elapsed_ms={elapsed_ms}")


if __name__ == "__main__":
    asyncio.run(main())
