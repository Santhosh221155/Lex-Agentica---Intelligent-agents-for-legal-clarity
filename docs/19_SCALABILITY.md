**Scalability Analysis**

Potential bottlenecks identified in code:
- Vector search latency: dense retrieval relies on Chroma or Qdrant; scale requires sharding or managed Qdrant clusters.
- Database: Postgres is central for metadata and traces; consider read replicas and partitioning for high ingestion.
- Agents: Retrieval and reranker can be parallelized (retrieval.batch_retrieve supports concurrency). See [backend/app/agents/retrieval.py](backend/app/agents/retrieval.py#L1-L40).
- LLM throughput: external provider streaming limits capacity; batching or model selection can control cost/latency.

Scaling strategies:
- Cache retrieval results in Redis to reduce repeated vector queries.
- Scale vector DB independently (Qdrant managed clusters) and use replicas for search.
- Use worker queues (e.g., Celery or managed queues) for ingestion and long-running tasks.
