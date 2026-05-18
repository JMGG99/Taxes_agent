# IRS Tax Tables API

REST API that extracts structured tax data from IRS (Internal Revenue Service) PDF publications and exposes it through queryable endpoints. Includes a natural language agent endpoint that translates questions into SQL queries against the same data.

## Quick overview

- 3 GET endpoints for direct tax lookups: income tax brackets, Earned Income Credits, and wage withholding amounts
- 1 POST endpoint for natural language tax questions answered by an AI agent via SQL queries
- 39,422 records extracted from 5 IRS PDFs across 3 publications (p1040, p596, p15t)
- Interactive API docs available at `/docs`

## Stack

- **Python 3.12** / **FastAPI** — Async-native framework.
- **SQLAlchemy 2 (async)** + **asyncpg** — Async PostgreSQL
- **pdfplumber** — PDF text and table extraction
- **OpenAI SDK** (Azure AI Foundry endpoint) — Agent tool calling
- **slowapi** — Rate limiting for API
- **pytest** + **pytest-asyncio** — Tests

## Data sources

| File | Content | Years | Source |
|------|---------|-------|--------|
| `p1040_2025.pdf` | Federal income tax brackets | 2025 | [IRS Publication 1040 Tax Tables](https://www.irs.gov/pub/irs-pdf/i1040tt.pdf) |
| `p596_2024.pdf` | Earned Income Credit tables | 2024 | [IRS Publication 596 (2024)](https://www.irs.gov/pub/irs-prior/p596--2024.pdf) |
| `p596_2025.pdf` | Earned Income Credit tables | 2025 | [IRS Publication 596](https://www.irs.gov/pub/irs-pdf/p596.pdf) |
| `p15t_2025.pdf` | Wage withholding brackets | 2025 | [IRS Publication 15-T (2025)](https://www.irs.gov/pub/irs-prior/p15t--2025.pdf) |
| `p15t_2026.pdf` | Wage withholding brackets | 2026 | [IRS Publication 15-T](https://www.irs.gov/pub/irs-pdf/p15t.pdf) |

## Database schema

### `tax_records`
Stores both tax table (p1040) and EIC credit tables (p596) rows under a single table, differentiated by `table_type`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER` | Primary Key |
| `year` | `SMALLINT` | Tax year |
| `table_type` | `VARCHAR(20)` | `tax_table` or `eic` |
| `filing_status` | `VARCHAR(50)` | Taxpayer's filing status |
| `income_from` | `INTEGER` | Inclusive lower bound |
| `income_to` | `INTEGER` | Exclusive upper bound |
| `amount` | `INTEGER` | Negative for tax owed, positive for EIC credit |
| `qualifying_children` | `SMALLINT` | 0–3, only for `eic` rows |

### `withholding_brackets`
Stores p15t wage bracket rows.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER` | Primary Key |
| `year` | `SMALLINT` | Tax year |
| `filing_status` | `VARCHAR(50)` | W-4 filing status |
| `pay_period` | `VARCHAR(20)` | `WEEKLY`, `BIWEEKLY`, `SEMIMONTHLY`, `MONTHLY`, `DAILY` |
| `income_from` | `NUMERIC(10,2)` | Inclusive lower bound |
| `income_to` | `NUMERIC(10,2)` | Exclusive upper bound |
| `withholding_amount` | `NUMERIC(10,2)` | Amount to withhold |
| `withholding_type` | `VARCHAR(10)` | `standard` or `checkbox` |

**Record counts (production DB):**

| Source | Rows |
|--------|------|
| tax_table 2025 | 8,248 (2,062 × 4 filing statuses) |
| eic 2024 | 10,696 (5,348 × 2 filing statuses) |
| eic 2025 | 10,992 (5,496 × 2 filing statuses) |
| withholding 2025 | 4,692 (3 filing statuses × 5 pay periods × 2 withholding types) |
| withholding 2026 | 4,794 |
| **Total** | **39,422** |

## PDF extraction

The three IRS publications have different layouts, so each uses a different extraction strategy.

**p1040** — The tax table is rendered as plain text across 12 pages in a three-column layout. Each line contains up to three income bands packed together (e.g., `3,000 3,050 303 303 303 303  6,000 6,050 603 ...`). The extractor uses regex to find numeric sequences and a sliding window to identify valid income bands by checking that the bracket width is in `{5, 10, 25, 50}` and that bounds are multiples of 5. A `seen_bands` set prevents duplicates from the overlapping multi-column layout.

**p596** — The EIC table has a proper table structure that pdfplumber's `extract_tables()` can parse directly. Each row contains an income range in column 0, single/MFS/HH credit amounts for 0–3 children in column 2, and MFJ credits in column 3. Some cells pack multiple rows with newlines (e.g., `200 250\n250 300\n...`), which are split and processed individually.

**p15t** — The wage bracket tables are plain text pages identified by the header `Wage Bracket Method Tables` + `2020 or Later`. Each data line has exactly 8 space-separated tokens: `$from $to amount×6` (one per filing status × withholding type combination). The six amounts map to a fixed column order defined in `S2_COLUMNS`.

All five PDFs are parsed in parallel using `ThreadPoolExecutor(max_workers=5)` — one thread per file — coordinated via `asyncio.run_in_executor`. The pipeline is idempotent: on startup it checks for existing records before running.

## Design decisions

**pdfplumber for PDF extraction**

All five PDFs contain embedded text (not scanned images), which makes pdfplumber's extraction reliable. It handles both cases present in these documents: `extract_tables()` for p596 (proper table structure) and `extract_text()` for p1040 and p15t (plain text columns).

**Deterministic parsing over LLM extraction**

Tax amounts must be exact. A parsing error of $1 produces a wrong tax figure. The PDFs contain embedded text (not scanned images), so the layout is machine-readable and the extraction can be fully deterministic, tested, and audited. LLM-based extraction adds latency, cost, and non-determinism to a problem that doesn't require semantic understanding — just pattern matching on well-structured numeric data. IRS table patterns were identified in collaboration with an LLM tool, which accelerated extraction logic design while keeping the final implementation fully deterministic.

**Parallel processing and bottleneck reduction**

Async patterns are used throughout the stack to avoid blocking the event loop at every I/O boundary: FastAPI async handlers, SQLAlchemy async + asyncpg for non-blocking DB queries, and `asyncio.to_thread` for the agent's synchronous tool calling loop. For the PDF pipeline, pdfplumber is synchronous and CPU/IO-bound — parsing five files sequentially would make startup time additive. `ThreadPoolExecutor(max_workers=5)` dispatches one thread per file and `asyncio.gather` collects all results concurrently, reducing total parse time to approximately the slowest single file.

**Two tables instead of one**

`tax_records` merges p1040 and p596 rows because both share the same dimensional shape: year, filing status, income range, and a dollar amount. The `table_type` column (`tax_table` / `eic`) and `qualifying_children` distinguish them. Splitting them into separate tables would duplicate the schema with no query benefit.

`withholding_brackets` is a separate table because it has attributes that don't exist in the income tax domain (`pay_period`, `withholding_type`) and its income bounds are decimal rather than integer. Forcing it into `tax_records` would require nullable columns with no semantic meaning for the other rows.

## Architecture notes

**Async event loop and the agent thread**

FastAPI runs on a single asyncio event loop. The agent's tool calling loop (`_run_sync`) runs in a worker thread via `asyncio.to_thread`, which means it cannot directly `await` coroutines. The SQL queries in `agent_tools.py` are async (SQLAlchemy async). To bridge this, `setup_loop()` captures the main event loop at startup, and `run_sql_query` uses `asyncio.run_coroutine_threadsafe` to submit the async query back onto the main loop from the worker thread and block until it resolves.

**Readonly database user**

The GET endpoints and the agent both use `DATABASE_URL_READONLY` (a PostgreSQL user with `SELECT`-only privileges). The admin connection (`DATABASE_URL`) is only used at startup for schema creation and pipeline ingestion. An additional `SELECT`-only guard is enforced in code in `agent_tools.py` before any query reaches the database.

**Rate limiting**

`slowapi` applies per-IP rate limits: 100 req/min on the three GET endpoints, 20 req/min on the agent endpoint.

## API reference

Interactive docs available at `/docs` on the running service.

---

### `GET /tax-records`
Returns the federal income tax bracket for a given income and filing status (p1040, 2025).

**Query params:**

| Param | Type | Values |
|-------|------|--------|
| `income` | `int` | 0 – 99,999 |
| `filing_status` | `string` | `single`, `married_filing_jointly`, `married_filing_separately`, `head_of_household` |

**Example:**
```
GET /tax-records?income=50000&filing_status=single
```
```json
[{"filing_status": "single", "income_from": 50000, "income_to": 50050, "amount": -5920}]
```
`amount` is negative — represents tax owed.

---

### `GET /eic-credits`
Returns the Earned Income Credit for a given income, filing status, and number of qualifying children (p596, 2024–2025).

**Query params:**

| Param | Type | Values |
|-------|------|--------|
| `income` | `int` | ≥ 1 |
| `filing_status` | `string` | `single_mfs_hh`, `married_filing_jointly` |
| `qualifying_children` | `string` | `0`, `1`, `2`, `3` |
| `year` | `string` | `2024`, `2025` |

**Example:**
```
GET /eic-credits?income=20000&filing_status=single_mfs_hh&qualifying_children=2&year=2025
```
```json
[{"year": 2025, "filing_status": "single_mfs_hh", "income_from": 20000, "income_to": 20050, "amount": 7152, "qualifying_children": 2}]
```

---

### `GET /withholding-brackets`
Returns the wage withholding amount for a given pay period income (p15t, 2025–2026).

**Query params:**

| Param | Type | Values |
|-------|------|--------|
| `income` | `float` | ≥ 0 |
| `filing_status` | `string` | `Married Filing Jointly`, `Head of Household`, `Single or Married Filing Separately` |
| `pay_period` | `string` | `WEEKLY`, `BIWEEKLY`, `SEMIMONTHLY`, `MONTHLY`, `DAILY` |
| `withholding_type` | `string` | `standard`, `checkbox` |
| `year` | `string` | `2025`, `2026` |

Returns `[]` when income exceeds the table maximum — use the IRS percentage method (Pub. 15-T) in that case.

**Example:**
```
GET /withholding-brackets?income=1000&filing_status=Single+or+Married+Filing+Separately&pay_period=WEEKLY&withholding_type=standard&year=2025
```
```json
[{"year": 2025, "filing_status": "Single or Married Filing Separately", "pay_period": "WEEKLY", "income_from": 995.0, "income_to": 1005.0, "withholding_amount": 81.0, "withholding_type": "standard"}]
```

---

### `POST /agent`
Accepts a natural language tax question and returns an answer backed by SQL queries against the database.

**Request body:**
```json
{"question": "How much federal income tax does a single filer owe on $45,000 in 2025?"}
```

**Response:**
```json
{"answer": "A single filer owes **$5,165.00** in federal income tax on **$45,000** of income for **2025**."}
```

The agent uses the OpenAI tool calling API (Azure AI Foundry, deployment configured via `AZURE_MODEL_DEPLOYMENT`). It has one tool: `run_sql_query`, which executes read-only SELECT statements. The system prompt includes the full database schema, column semantics, and example queries so the model generates correct SQL without hallucinating table or column names.

---

### `GET /stats`
Returns total record counts and per-year breakdown for each table.

### `GET /health`
Returns `{"status": "ok"}`.

---

## Local setup

**Prerequisites:** Python 3.12, PostgreSQL running locally.

```bash
git clone <repo>
cd Taxes_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your values:
```
DATABASE_URL=<admin_user_db_url>
DATABASE_URL_READONLY=<read_only_user_db_url>
AZURE_AI_ENDPOINT=<azure_openai_endpoint_url>
AZURE_MODEL_DEPLOYMENT=<azure_model_deployment_name>
AZURE_AI_API_KEY=<azure_api_key>
```

Run the API (the pipeline runs automatically on first startup):
```bash
uvicorn app.main:app --reload
```

Run tests (requires a fully configured environment with database connection, loaded data, and PDF source files in place):
```bash
pytest
```

## Deployment

The service runs on Azure Container Apps. The image is built from `Dockerfile` and stored in Azure Container Registry. Environment variables are set as secrets in the Container App. The database runs on Azure Database for PostgreSQL Flexible Server.

```bash
docker login <registry>.azurecr.io
docker build -t <registry>.azurecr.io/<image>:<tag> .
docker push <registry>.azurecr.io/<image>:<tag>
```
