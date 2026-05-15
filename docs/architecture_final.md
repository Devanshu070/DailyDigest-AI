# DailyDigest-AI — Architecture Diagrams

---

# 1. High-Level System Architecture

<div align="center">

```mermaid
flowchart TD

    A[YouTube RSS]
    B[Blog RSS]
    C[Newsletters]
    D[HTML Sources]

    A --> INGEST
    B --> INGEST
    C --> INGEST
    D --> INGEST

    subgraph INGESTION_LAYER [Ingestion Layer]
        INGEST[app/ingestion]
    end

    INGEST --> DB[(PostgreSQL)]

    DB --> CLEANER

    subgraph PROCESSING_LAYER [Processing Layer]
        CLEANER[cleaner.py]
    end

    CLEANER --> ROUTER

    subgraph SUMMARIZATION_LAYER [Summarization Layer]

        ROUTER{token_count > threshold?}

        STANDARD[Standard Summarization]

        CONTEXT[Context-Preserving Hierarchical Summarization]

        ROUTER -->|No| STANDARD
        ROUTER -->|Yes| CONTEXT
    end

    STANDARD --> SUMMARY

    CONTEXT --> CHUNK1[Chunk 1 → Summary 1]
    CHUNK1 --> CHUNK2[Chunk 2 + Summary 1 → Summary 2]
    CHUNK2 --> CHUNK3[Chunk 3 + Previous Context → Summary 3]
    CHUNK3 --> SYNTHESIS[Final Synthesis]

    SYNTHESIS --> SUMMARY

    SUMMARY[Final Article Summary]

    SUMMARY --> DIGEST

    subgraph DIGEST_LAYER [Digest Assembly]

        DIGEST[Digest Generator]
        INTERESTS[user_interests.md]

        INTERESTS --> DIGEST
    end

    DIGEST --> HTML

    HTML[Markdown → HTML]

    HTML --> EMAIL

    subgraph DELIVERY_LAYER [Delivery]
        EMAIL[Resend Email Delivery]
    end

    EMAIL --> USER[Inbox]
```

</div>

---

# 2. Runtime Pipeline Flowchart

<div align="center">

```mermaid
flowchart TD

    START([Pipeline Start])

    START --> LOAD_SOURCES

    LOAD_SOURCES[Load active sources from DB]

    LOAD_SOURCES --> INGEST

    INGEST[Fetch RSS / HTML content]

    INGEST --> DEDUP

    DEDUP{Already exists?}

    DEDUP -->|Yes| SKIP

    DEDUP -->|No| STORE_RAW

    STORE_RAW[Store raw_content]

    STORE_RAW --> CLEAN

    CLEAN[Normalize + clean content]

    CLEAN --> TOKENIZE

    TOKENIZE[Estimate token_count]

    TOKENIZE --> ROUTE

    ROUTE{Large transcript?}

    ROUTE -->|No| STANDARD

    ROUTE -->|Yes| CONTEXT

    STANDARD[Single-pass summarization]

    CONTEXT[Context-Preserving Hierarchical Summarization]

    STANDARD --> SAVE_SUMMARY
    CONTEXT --> SAVE_SUMMARY

    SAVE_SUMMARY[Store summary]

    SAVE_SUMMARY --> COLLECT

    COLLECT[Collect summarized articles]

    COLLECT --> DIGEST

    DIGEST[Generate personalized digest]

    DIGEST --> CONVERT

    CONVERT[Convert Markdown to HTML]

    CONVERT --> SEND

    SEND[Send email via Resend]

    SEND --> LOGS

    LOGS[Emit structured logs]

    LOGS --> END([Pipeline Complete])

    SKIP --> END
```

</div>

---

# 3. Sequence Diagram — End-to-End Pipeline

<div align="center">

```mermaid
sequenceDiagram
    autonumber

    participant Runner
    participant Sources
    participant Ingestion
    participant Cleaner
    participant LLM
    participant Digest
    participant Email
    participant DB

    Runner->>DB: Load active sources

    loop Per Source
        Runner->>Ingestion: Fetch source content
        Ingestion->>Sources: RSS / HTML request
        Sources-->>Ingestion: Articles

        Ingestion->>DB: Store raw_content
    end

    Runner->>DB: Fetch articles(status=fetched)

    loop Per Article
        Runner->>Cleaner: Clean content
        Cleaner->>DB: Update cleaned_content + token_count

        alt Small Article
            Runner->>LLM: Standard summary request
        else Large Transcript
            Runner->>LLM: Context-Preserving Hierarchical Summarization
        end

        LLM-->>Runner: Summary
        Runner->>DB: Store summary
    end

    Runner->>DB: Fetch summarized articles

    Runner->>Digest: Generate digest from summarized articles

    Digest->>LLM: Personalized digest prompt
    LLM-->>Digest: Markdown digest

    Digest->>DB: Store markdown_content + html_content

    Runner->>Email: Send digest email

    Email->>DB: Update sent_at
```

</div>

---

# 4. Context-Preserving Hierarchical Summarization Flow

<div align="center">

```mermaid
flowchart TD

    A[Large Transcript]

    A --> C1[Chunk 1]

    C1 --> S1[Summary 1]

    A --> C2[Chunk 2 + Summary 1]

    C2 --> S2[Summary 2]

    A --> C3[Chunk 3 + Previous Context]

    C3 --> S3[Summary 3]

    S1 --> FINAL
    S2 --> FINAL
    S3 --> FINAL

    FINAL[Final Synthesis]

    FINAL --> OUT[Final Article Summary]
```

</div>

---

# 5. Database ER Diagram

<div align="center">

```mermaid
erDiagram

    SOURCES {
        UUID id PK
        STRING name
        ENUM type
        STRING url
        BOOLEAN is_active
        DATETIME last_fetched_at
        INTEGER fetch_interval_minutes
        INTEGER failure_count
        TEXT last_error
        DATETIME created_at
        DATETIME updated_at
    }

    ARTICLES {
        UUID id PK
        UUID source_id FK
        STRING title
        STRING url
        STRING content_hash
        TEXT raw_content
        TEXT cleaned_content
        TEXT summary
        STRING summary_model
        INTEGER token_count
        ENUM processing_status
        TEXT processing_error
        INTEGER retry_count
        DATETIME last_retry_at
        DATETIME published_at
        DATETIME scraped_at
        DATETIME created_at
        DATETIME updated_at
    }

    DAILY_DIGESTS {
        UUID id PK
        DATE digest_date
        TEXT markdown_content
        TEXT html_content
        STRING prompt_version
        STRING model_used
        INTEGER article_count
        DATETIME sent_at
        DATETIME created_at
        DATETIME updated_at
    }

    SOURCES ||--o{ ARTICLES : produces
```

</div>

---

# 6. Class Diagram

<div align="center">

```mermaid
classDiagram

    class BaseLLMProvider {
        <<abstract>>
        +complete(system_prompt, user_prompt)
    }

    class AnthropicProvider {
        +complete(system_prompt, user_prompt)
    }

    class OpenAIProvider {
        +complete(system_prompt, user_prompt)
    }

    BaseLLMProvider <|-- AnthropicProvider
    BaseLLMProvider <|-- OpenAIProvider

    class BaseIngester {
        <<abstract>>
        +fetch()
        +parse()
    }

    class YouTubeIngester {
        +fetch()
        +parse()
    }

    class BlogIngester {
        +fetch()
        +parse()
    }

    BaseIngester <|-- YouTubeIngester
    BaseIngester <|-- BlogIngester

    class Cleaner {
        +clean()
        +normalize()
        +estimate_tokens()
    }

    class DigestGenerator {
        +summarize_article()
        +generate_digest()
    }

    class EmailSender {
        +send_digest()
    }

    class Runner {
        +run()
    }

    Runner --> BaseIngester
    Runner --> Cleaner
    Runner --> DigestGenerator
    Runner --> EmailSender

    DigestGenerator --> BaseLLMProvider
```

</div>

---

# 7. Processing State Machine

<div align="center">

```mermaid
stateDiagram-v2

    [*] --> fetched

    fetched --> cleaned

    cleaned --> summarized

    summarized --> included_in_digest

    fetched --> failed
    cleaned --> failed
    summarized --> failed

    failed --> cleaned : retry
```

</div>

---

# 8. Future Extensibility Architecture

<div align="center">

```mermaid
flowchart LR

    SUMMARIES[Summarized Articles]

    SUMMARIES --> RANKING[Relevance Ranking]

    RANKING --> FILTER[LLM-Driven Article Selection]

    FILTER --> DIGEST[Digest Assembly]

    SUMMARIES --> EMBEDDINGS[Embeddings]

    EMBEDDINGS --> SEARCH[Semantic Search]

    EMBEDDINGS --> CLUSTERING[Topic Clustering]

    CLUSTERING --> DIGEST
```

</div>
