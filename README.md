# IRS Tax Tables API

REST API that extracts structured tax data from PDF documents and exposes it through queryable endpoints. Supports two extraction pipelines: an AI-powered dynamic pipeline for any PDF document, and a deterministic static pipeline tuned for IRS publications. Includes a natural language agent endpoint backed by SQL queries.

See [C4 Architecture Diagram](docs/c4_diagram.md) for the full system architecture.

## Dual extraction architecture

**AI-powered dynamic pipeline**
Upload random Taxes PDF documents and extract structured records automatically — the system infers table schemas, field names, and data types without any prior knowledge of the document's structure.

**Deterministic static pipeline**
Layout-specific parsers purpose-built for IRS publications, delivering exact and fully auditable tax figures at zero inference cost per request.

## Quick overview

- 4 endpoints for AI-powered dynamic PDF extraction — upload any PDF, the system infers schemas and extracts records automatically (max 5 documents)
- 3 GET endpoints for direct IRS tax lookups: income tax brackets, Earned Income Credits, and wage withholding amounts
- 1 POST endpoint for natural language tax questions answered by an AI agent via SQL queries
- 39,422 records extracted from 5 IRS PDFs across 3 publications (p1040, p596, p15t)
- Interactive API docs available at `/docs`

## Stack

- **Python 3.12** / **FastAPI** — Async-native framework
- **SQLAlchemy 2 (async)** + **asyncpg** — Async PostgreSQL
- **pdfplumber** — PDF text and table extraction
- **OpenAI SDK** (Azure AI Foundry endpoint) — LLM extraction and agent tool calling
- **python-multipart** — Multipart file upload support
- **slowapi** — Rate limiting
- **pytest** + **pytest-asyncio** — Tests

---

## Dynamic PDF extraction (AI pipeline)

Accepts any PDF containing tabular data and extracts structured records without requiring prior knowledge of the document's schema.

### Flow

1. **Deduplication** — SHA-256 hash of the file is computed before any processing. If the same PDF was already uploaded (regardless of filename), it is rejected immediately without spending tokens. The system holds a maximum of 5 documents.

2. **Page filtering** — `pdfplumber` scans the document and selects only pages where `extract_tables()` detects structured content.

3. **Parallel per-page extraction** — Each selected page is sent independently to `gpt-4o-mini` using 5 concurrent workers (`ThreadPoolExecutor`). The LLM receives the full page text — surrounding context (titles, headings, section names) plus the raw table rows — and returns a `table_type` name inferred from that context and a list of extracted records as JSON. `temperature=0` and `response_format=json_object` are used to minimize non-determinism.

4. **Name reconciliation** — After all pages are processed, a single LLM call receives the list of all detected `table_type` names and normalizes them, merging names that refer to the same table across different pages.

5. **Storage** — Each record is persisted in PostgreSQL as JSONB with its `pdf_hash`, `filename`, `page_number`, and `table_type`. No predefined schema is required.

### Design note

The per-page approach keeps each LLM call small (max 3,000 characters) and independent. Pages are processed in parallel, reducing total extraction time to approximately the slowest single page. Name reconciliation happens once at the end, after all parallel work is done, to ensure consistent grouping without blocking the parallel phase.

Using the full page context — not just column structure — to name tables allows the LLM to distinguish tables that share the same columns but represent different entities (e.g., "Single Filers" vs "Married Filing Jointly" brackets on separate pages).

---

## Static PDF extraction (deterministic pipeline)

Extracts IRS tax data at startup using layout-specific parsers per publication. Records are stored once and served through the GET endpoints.

### Data sources

| File | Content | Years | Source |
|------|---------|-------|--------|
| `p1040_2025.pdf` | Federal income tax brackets | 2025 | [IRS Publication 1040 Tax Tables](https://www.irs.gov/pub/irs-pdf/i1040tt.pdf) |
| `p596_2024.pdf` | Earned Income Credit tables | 2024 | [IRS Publication 596 (2024)](https://www.irs.gov/pub/irs-prior/p596--2024.pdf) |
| `p596_2025.pdf` | Earned Income Credit tables | 2025 | [IRS Publication 596](https://www.irs.gov/pub/irs-pdf/p596.pdf) |
| `p15t_2025.pdf` | Wage withholding brackets | 2025 | [IRS Publication 15-T (2025)](https://www.irs.gov/pub/irs-prior/p15t--2025.pdf) |
| `p15t_2026.pdf` | Wage withholding brackets | 2026 | [IRS Publication 15-T](https://www.irs.gov/pub/irs-pdf/p15t.pdf) |

### Extraction strategy

**p1040** — The tax table is rendered as plain text across 12 pages in a three-column layout. Each line contains up to three income bands packed together (e.g., `3,000 3,050 303 303 303 303  6,000 6,050 603 ...`). The extractor uses regex to find numeric sequences and a sliding window to identify valid income bands by checking that the bracket width is in `{5, 10, 25, 50}` and that bounds are multiples of 5. A `seen_bands` set prevents duplicates from the overlapping multi-column layout.

**p596** — The EIC table has a proper table structure that pdfplumber's `extract_tables()` can parse directly. Each row contains an income range in column 0, single/MFS/HH credit amounts for 0–3 children in column 2, and MFJ credits in column 3. Some cells pack multiple rows with newlines, which are split and processed individually.

**p15t** — The wage bracket tables are plain text pages identified by the header `Wage Bracket Method Tables` + `2020 or Later`. Each data line has exactly 8 space-separated tokens mapping to a fixed column order defined in `S2_COLUMNS`.

All five PDFs are parsed in parallel using `ThreadPoolExecutor(max_workers=5)`. The pipeline is idempotent: on startup it checks for existing records before running.

### Design note

Tax amounts must be exact — a parsing error of $1 produces a wrong tax figure. The IRS PDFs contain embedded text (not scanned images), making the layout fully machine-readable. Deterministic parsing is testable, auditable, and adds no latency or cost per request. LLM-based extraction was used during development to identify table patterns and accelerate extraction logic design; the final implementation is fully rule-based.

---

## Database schema

### `dynamic_pdf_records`
Stores records extracted from dynamically uploaded PDFs. Schema is flexible — `record` holds arbitrary JSONB per document type.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER` | Primary key |
| `pdf_hash` | `VARCHAR(64)` | SHA-256 of the file — indexed, used for deduplication and lookup |
| `filename` | `VARCHAR(255)` | Original filename |
| `document_type` | `VARCHAR(255)` | Filename without extension |
| `page_number` | `INTEGER` | Source page in the PDF |
| `table_type` | `VARCHAR(100)` | LLM-inferred table name (e.g. `federal_income_tax_brackets_single_filers_2026`) |
| `record` | `JSONB` | Extracted row — field names and types inferred per document |
| `uploaded_at` | `TIMESTAMPTZ` | Upload timestamp |

### `tax_records`
Stores both tax table (p1040) and EIC credit tables (p596) rows, differentiated by `table_type`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER` | Primary key |
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
| `id` | `INTEGER` | Primary key |
| `year` | `SMALLINT` | Tax year |
| `filing_status` | `VARCHAR(50)` | W-4 filing status |
| `pay_period` | `VARCHAR(20)` | `WEEKLY`, `BIWEEKLY`, `SEMIMONTHLY`, `MONTHLY`, `DAILY` |
| `income_from` | `NUMERIC(10,2)` | Inclusive lower bound |
| `income_to` | `NUMERIC(10,2)` | Exclusive upper bound |
| `withholding_amount` | `NUMERIC(10,2)` | Amount to withhold |
| `withholding_type` | `VARCHAR(10)` | `standard` or `checkbox` |

**Static record counts (production DB):**

| Source | Rows |
|--------|------|
| tax_table 2025 | 8,248 |
| eic 2024 | 10,696 |
| eic 2025 | 10,992 |
| withholding 2025 | 4,692 |
| withholding 2026 | 4,794 |
| **Total** | **39,422** |

---

## Architecture notes

**Two database sessions**

The static GET endpoints and the agent use `DATABASE_URL_READONLY` (a PostgreSQL user with `SELECT`-only privileges). The dynamic PDF endpoints use `get_write_db`, which connects via the admin `DATABASE_URL` since they need to `INSERT` and `DELETE`. The admin connection is also used at startup for schema creation and pipeline ingestion.

**Async event loop and the agent thread**

FastAPI runs on a single asyncio event loop. The agent's tool calling loop (`_run_sync`) runs in a worker thread via `asyncio.to_thread`. The SQL queries in `agent_tools.py` are async. To bridge this, `setup_loop()` captures the main event loop at startup, and `run_sql_query` uses `asyncio.run_coroutine_threadsafe` to submit the async query back onto the main loop from the worker thread and block until it resolves.

**Rate limiting**

`slowapi` applies per-IP rate limits: 100 req/min on the static GET endpoints, 20 req/min on the agent, 5 req/min on `POST /upload-pdfs`, 30 req/min on dynamic GET endpoints, 10 req/min on `DELETE`.

---

## API reference

Interactive docs available at `/docs` on the running service.

---

### `POST /upload-pdfs`
Uploads a PDF and runs the AI extraction pipeline. Returns the `pdf_hash` (first 12 chars), detected tables, and record counts.

- Max file size: 10 MB
- Max documents: 5 (use `DELETE` to free a slot)
- Duplicate PDFs are rejected by content hash regardless of filename

**Response:**
```json
{
  "pdf_hash": "895ca7f65d41",
  "filename": "tablas_impuestos_federales_2026.pdf",
  "pages_with_tables": [2, 3, 4, 5, 6, 7],
  "tables": [
    {"table_type": "federal_income_tax_brackets_single_filers_2026", "page": 2, "records_stored": 7, "sample": {...}}
  ],
  "total_records": 48
}
```

---

### `GET /dynamic-pdfs`
Lists all uploaded PDFs with slot usage, record counts, and hashes.

**Response:**
```json
{
  "slots_used": "1/5",
  "pdfs": [
    {
      "pdf_hash": "895ca7f65d41",
      "filename": "tablas_impuestos_federales_2026.pdf",
      "document_type": "tablas_impuestos_federales_2026",
      "uploaded_at": "2026-05-19T17:35:59Z",
      "record_count": 48
    }
  ]
}
```

---

### `GET /dynamic-pdfs/{pdf_hash}/records`
Returns all extracted records for a PDF, grouped by `table_type` and ordered by page number. Use the first 12 characters of the hash returned by `POST /upload-pdfs`.

**Response:**
```json
{
  "pdf_hash": "895ca7f65d41",
  "filename": "tablas_impuestos_federales_2026.pdf",
  "document_type": "tablas_impuestos_federales_2026",
  "tables": {
    "federal_income_tax_brackets_single_filers_2026": [
      {"lower_limit": 0, "upper_limit": 11925, "marginal_rate": 10, "base_calculation": "10% del ingreso gravable"},
      ...
    ]
  }
}
```

---

### `DELETE /dynamic-pdfs/{pdf_hash}`
Deletes a PDF and all its records, freeing a slot.

**Query params:**

| Param | Type | Notes |
|-------|------|-------|
| `key` | `string` | Authorization key — required |
| `pdf_hash` | `string` | First 12 chars of the hash |

Returns `401` if the key is wrong, `404` if the hash is not found.

---

### `GET /tax-records`
Returns the federal income tax bracket for a given income and filing status (p1040, 2025).

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

| Param | Type | Values |
|-------|------|--------|
| `income` | `float` | ≥ 0 |
| `filing_status` | `string` | `Married Filing Jointly`, `Head of Household`, `Single or Married Filing Separately` |
| `pay_period` | `string` | `WEEKLY`, `BIWEEKLY`, `SEMIMONTHLY`, `MONTHLY`, `DAILY` |
| `withholding_type` | `string` | `standard`, `checkbox` |
| `year` | `string` | `2025`, `2026` |

Returns `[]` when income exceeds the table maximum — use the IRS percentage method (Pub. 15-T) in that case.

---

### `POST /agent`
Accepts a natural language tax question and returns an answer backed by SQL queries against the static database.

**Request body:**
```json
{"question": "How much federal income tax does a single filer owe on $45,000 in 2025?"}
```

**Response:**
```json
{"answer": "A single filer owes **$5,165.00** in federal income tax on **$45,000** of income for **2025**."}
```

The agent uses the OpenAI tool calling API (Azure AI Foundry). It has one tool: `run_sql_query`, which executes read-only SELECT statements. A `SELECT`-only guard is enforced in code before any query reaches the database.

---

### `GET /stats`
Returns total record counts and per-year breakdown for each static table.

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

Run the API (the static pipeline runs automatically on first startup):
```bash
uvicorn app.main:app --reload
```

Run tests:
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
