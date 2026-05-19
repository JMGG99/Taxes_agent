# C4 Architecture Diagram

## Level 1 — System Context

```mermaid
C4Context
    title System Context — IRS Tax Tables API

    Person(client, "API Client", "Application or developer consuming tax data or uploading PDFs")

    System(api, "IRS Tax Tables API", "Dual-pipeline REST API: AI-powered dynamic PDF extraction for any document, and a deterministic static pipeline for IRS publications")

    System_Ext(azure_ai, "Azure AI Foundry", "Provides LLM inference for dynamic PDF extraction and the natural language agent")

    Rel(client, api, "HTTP requests")
    Rel(api, azure_ai, "Chat completions — extraction + agent tool calling", "HTTPS")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Level 2 — Containers

```mermaid
C4Container
    title Container Diagram — IRS Tax Tables API

    Person(client, "API Client", "Application or developer consuming tax data or uploading PDFs")

    Container(app, "FastAPI Application", "Python / FastAPI", "Handles HTTP requests, dynamic PDF extraction, static pipeline ingestion, and agent queries")
    ContainerDb(db, "PostgreSQL", "Azure DB for PostgreSQL", "Stores tax_records, withholding_brackets (39,422 rows) and dynamic_pdf_records (JSONB, up to 5 documents)")
    System_Ext(azure_ai, "Azure AI Foundry", "LLM endpoint — gpt-4o-mini for per-page extraction, reconciliation, and agent tool calling")

    Rel(client, app, "GET / POST / DELETE", "HTTPS")
    Rel(app, db, "Async SQL queries — readonly + write sessions", "asyncpg")
    Rel(app, azure_ai, "Chat completions + tool calling", "HTTPS / OpenAI SDK")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Level 3 — Components

```mermaid
C4Component
    title Component Diagram — FastAPI Application

    Person(client, "API Client")
    ContainerDb(db, "PostgreSQL", "asyncpg", "tax_records · withholding_brackets · dynamic_pdf_records")
    System_Ext(azure_ai, "Azure AI Foundry", "gpt-4o-mini endpoint")

    Container_Boundary(app, "FastAPI Application") {
        Component(main, "main.py", "FastAPI lifespan", "App startup: schema creation, static pipeline execution, loop setup")
        Component(limiter, "limiter.py", "slowapi", "Per-IP rate limiting across all endpoints")

        Component(dynamic_routes, "dynamic_pdf_routes.py", "FastAPI Router", "POST /upload-pdfs · GET /dynamic-pdfs · GET /dynamic-pdfs/{hash}/records · DELETE /dynamic-pdfs/{hash}")
        Component(extractor, "dynamic_pdf_extractor.py", "pdfplumber + ThreadPoolExecutor", "SHA-256 dedup · per-page parallel LLM extraction (5 workers) · name reconciliation")

        Component(routes, "routes.py", "FastAPI Router", "GET /tax-records · /eic-credits · /withholding-brackets")
        Component(agent_routes, "agent_routes.py", "FastAPI Router", "POST /agent")
        Component(agent, "agent.py", "OpenAI SDK", "Tool calling loop with system prompt and schema context")
        Component(agent_tools, "agent_tools.py", "SQLAlchemy + asyncio", "run_sql_query: SELECT guard + async bridge via run_coroutine_threadsafe")

        Component(pipeline, "data_pipeline.py", "pdfplumber + ThreadPoolExecutor", "Parallel deterministic extraction of p1040 · p596 · p15t")
        Component(database, "database.py", "SQLAlchemy async", "Admin engine (write) · readonly engine (read) · get_write_db")
    }

    Rel(client, dynamic_routes, "POST / GET / DELETE", "HTTPS")
    Rel(client, routes, "GET requests", "HTTPS")
    Rel(client, agent_routes, "POST /agent", "HTTPS")

    Rel(dynamic_routes, limiter, "Rate check")
    Rel(dynamic_routes, extractor, "extract_and_save(filename, bytes)")
    Rel(extractor, azure_ai, "Per-page extraction + reconciliation", "HTTPS")
    Rel(extractor, database, "WriteSession — INSERT dynamic_pdf_records")
    Rel(dynamic_routes, database, "WriteSession — SELECT / DELETE dynamic_pdf_records")

    Rel(routes, limiter, "Rate check")
    Rel(routes, database, "ReadonlySession")
    Rel(agent_routes, limiter, "Rate check")
    Rel(agent_routes, agent, "run_agent(question)")
    Rel(agent, azure_ai, "Chat completions + tool calling", "HTTPS")
    Rel(agent, agent_tools, "run_sql_query(query)")
    Rel(agent_tools, database, "ReadonlySession via coroutine_threadsafe")

    Rel(database, db, "asyncpg pool")
    Rel(main, pipeline, "On startup (idempotent)")
    Rel(pipeline, database, "AdminSession (write)")
```
