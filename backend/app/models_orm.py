from sqlalchemy.orm import registry
from typing import Any

from app import models as core_models

# Reuse the existing metadata from `app.models` and map simple ORM classes
mapper_registry = registry(metadata=core_models.metadata)


class Tenant:
    pass


class Workspace:
    pass


class User:
    pass


class Document:
    pass


class IngestionJob:
    pass


class Chunk:
    pass


class Embedding:
    pass


class Memory:
    pass


class Trace:
    pass


# Map ORM classes to existing tables defined in `app.models`
mapper_registry.map_imperatively(Tenant, core_models.tenants)
mapper_registry.map_imperatively(Workspace, core_models.workspaces)
mapper_registry.map_imperatively(User, core_models.users)
mapper_registry.map_imperatively(Document, core_models.documents)
mapper_registry.map_imperatively(IngestionJob, core_models.ingestion_jobs)
mapper_registry.map_imperatively(Chunk, core_models.chunks)
mapper_registry.map_imperatively(Embedding, core_models.embeddings)
mapper_registry.map_imperatively(Memory, core_models.memories)
mapper_registry.map_imperatively(Trace, core_models.traces)

__all__ = [
    "Tenant",
    "Workspace",
    "User",
    "Document",
    "IngestionJob",
    "Chunk",
    "Embedding",
    "Memory",
    "Trace",
]
