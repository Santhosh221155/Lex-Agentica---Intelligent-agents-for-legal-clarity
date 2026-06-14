# Architecture Review

## Updated Architecture Diagram

```mermaid
flowchart LR
    U[User] --> F[FastAPI]
    F --> P[Planner Agent]
    P --> R[Retrieval Agent]
    P --> T[Tool Agent]
    P --> M[Memory Agent]
    R --> V[Validator Agent]
    T --> V
    M --> V
    V --> S[Synthesizer Agent]
    S --> X[Reflection Agent]
    V -->|confidence < threshold| H[Human Review API]
    H -->|approve / reject| F
    X --> F
    R --> D[(Document Store / Chroma / Postgres)]
    M --> D
    T --> D
    F --> O[Observability / Metrics]
    F --> E[Evaluation API]
```

## Sequence Diagram

```mermaid
sequenceDiagram
    participant User
    participant API as FastAPI
    participant Planner
    participant Retrieval
    participant Validator
    participant Synthesizer
    participant Reflection
    participant Review

    User->>API: Query
    API->>Planner: Build plan + filters
    API->>Retrieval: Top 20 candidates
    Retrieval-->>API: Reranked top 5 + explanations
    API->>Validator: Score evidence
    Validator-->>API: Confidence + review flag
    API->>Synthesizer: Stream answer
    Synthesizer-->>API: Tokens
    Synthesizer->>Reflection: Critique answer
    Reflection-->>API: Critique + revised draft
    API->>Review: If confidence low, create review request
    API-->>User: Streamed response + review metadata
```

## Data Flow Diagram

```mermaid
flowchart TD
    A[Query] --> B[Planner]
    B --> C[Metadata Filters]
    C --> D[Dense Retrieval]
    C --> E[BM25 Retrieval]
    D --> F[RRF Fusion]
    E --> F
    F --> G[Cross-Encoder Reranker]
    G --> H[Validator]
    H --> I[Synthesizer]
    I --> J[Reflection Agent]
    J --> K[Human Review if needed]
    J --> L[Trace / Audit Storage]
    H --> L
    G --> L
```

## Database ER Diagram

```mermaid
erDiagram
    USERS ||--o{ DOCUMENTS : owns
    USERS ||--o{ SESSIONS : opens
    DOCUMENTS ||--o{ CHUNKS : contains
    DOCUMENTS ||--o{ DOCUMENT_AUDITS : audited_by
    CHUNKS ||--o{ EMBEDDINGS : embeds
    SESSIONS ||--o{ TRACES : records
    SESSIONS ||--o{ TOOLS_HISTORY : logs
    SESSIONS ||--o{ REVIEW_REQUESTS : reviews
    SESSIONS ||--o{ REFLECTION_LOGS : reflections
    USERS ||--o{ REVIEW_REQUESTS : decides
    USERS ||--o{ EVALUATION_RUNS : creates
    EVALUATION_RUNS ||--o{ EVALUATION_RECORDS : contains
```

## Agent Communication Diagram

```mermaid
flowchart LR
    Planner --> Retrieval
    Planner --> ToolAgent
    Planner --> MemoryAgent
    Retrieval --> Validator
    ToolAgent --> Validator
    MemoryAgent --> Validator
    Validator --> Synthesizer
    Synthesizer --> Reflection
    Validator --> ReviewAPI
    ReviewAPI --> Synthesizer
```

## Notes

The upgraded design keeps the original agent workflow intact while adding:

1. Metadata filtering before reranking.
2. Cross-encoder reranking with latency and explanation outputs.
3. Human-in-the-loop review when validator confidence is low.
4. Memory scoring for short-term and semantic recall.
5. Evaluation persistence for RAGAS-style and DeepEval-style metrics.
6. Reflection logging for post-synthesis quality control.
7. Tool registry governance and tool audit trails.
