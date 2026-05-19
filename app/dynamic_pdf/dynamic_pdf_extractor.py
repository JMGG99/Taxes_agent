import asyncio
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pdfplumber
from openai import OpenAI

from app.config import settings

MAX_PAGE_CHARS = 3_000
MAX_WORKERS = 5

_PAGE_SYSTEM = """You are a data extraction specialist. Given the full text of a single PDF page, determine if it contains a structured data table with multiple rows of data.

The page text includes BOTH the surrounding context (titles, headings, section names) AND the raw table data. Use ALL of this information — not just the column structure — to understand and name each table.

Return ONLY valid JSON in this exact format:
{
  "table_type": "<snake_case name describing this specific table based on its context and content, or null if no data table found>",
  "records": [ { ...one object per row, field names as keys, numeric values as numbers... } ]
}

Rules:
- Name the table using the page context (titles, headings, labels) — two tables with identical columns but different context must have different names
- Numbers must be numeric (e.g. 1500 not "1,500")
- Field names must be consistent in language and format (use English snake_case)
- Only extract rows explicitly present — never invent data
- If the page has no structured data table, return {"table_type": null, "records": []}"""

_RECONCILE_SYSTEM = """You are a data analyst. Given a list of table_type names detected from different pages of the same PDF, identify which names refer to the same table and normalize them.

Return ONLY valid JSON:
{
  "mapping": {
    "<original_name>": "<normalized_name>"
  }
}

Rules:
- If names refer to the same table (same structure and content type), map them all to the most descriptive common name
- If a name is already unique and descriptive, map it to itself
- Use snake_case for all normalized names"""


def _get_client() -> OpenAI:
    return OpenAI(
        base_url=settings.azure_ai_endpoint,
        api_key=settings.azure_ai_api_key,
    )


def _extract_page_text(page) -> str:
    text = page.extract_text() or ""
    chunk = text
    for j, table in enumerate(page.extract_tables()):
        if table:
            chunk += f"\n\nTABLE {j + 1}:\n"
            for row in table:
                if row:
                    chunk += " | ".join(str(c or "") for c in row) + "\n"
    return chunk[:MAX_PAGE_CHARS]


def _process_page(client: OpenAI, page_text: str, known_tables: list[str]) -> dict:
    response = client.chat.completions.create(
        model=settings.azure_model_deployment,
        messages=[
            {"role": "system", "content": _PAGE_SYSTEM},
            {"role": "user", "content": f"PAGE TEXT:\n\n{page_text}"},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


def _reconcile_names(client: OpenAI, detected_types: list[str]) -> dict[str, str]:
    response = client.chat.completions.create(
        model=settings.azure_model_deployment,
        messages=[
            {"role": "system", "content": _RECONCILE_SYSTEM},
            {"role": "user", "content": f"Table types detected:\n{json.dumps(detected_types, indent=2)}"},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content).get("mapping", {})


def _run_extraction(file_bytes: bytes) -> list[dict]:
    client = _get_client()

    pages_to_process: list[tuple[int, str]] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            if not page.extract_tables():
                continue
            pages_to_process.append((i + 1, _extract_page_text(page)))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            (page_num, pool.submit(_process_page, client, text, []))
            for page_num, text in pages_to_process
        ]
        raw_results = []
        for page_num, future in futures:
            try:
                raw_results.append({"page_number": page_num, **future.result()})
            except Exception:
                pass

    valid = [r for r in raw_results if r.get("table_type") and r.get("records")]

    detected_types = list({r["table_type"] for r in valid})
    if len(detected_types) > 1:
        try:
            name_map = _reconcile_names(client, detected_types)
        except Exception:
            name_map = {}
        for r in valid:
            r["table_type"] = name_map.get(r["table_type"], r["table_type"])

    return sorted(valid, key=lambda r: r["page_number"])


async def extract_and_save(filename: str, file_bytes: bytes) -> dict:
    from sqlalchemy import func, select
    from app.database import AsyncSessionLocal
    from app.dynamic_pdf.models import DynamicPdfRecord, MAX_DYNAMIC_PDFS

    pdf_hash = hashlib.sha256(file_bytes).hexdigest()
    doc_name = filename.rsplit(".", 1)[0]

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(func.count()).where(DynamicPdfRecord.pdf_hash == pdf_hash)
        )
        if existing:
            raise ValueError("This PDF has already been uploaded.")

        distinct_pdfs = await session.scalar(
            select(func.count(func.distinct(DynamicPdfRecord.pdf_hash)))
        )
        if distinct_pdfs >= MAX_DYNAMIC_PDFS:
            raise ValueError(f"Maximum of {MAX_DYNAMIC_PDFS} uploaded PDFs reached.")

        page_results = await asyncio.to_thread(_run_extraction, file_bytes)

        total_records = 0
        for page in page_results:
            for record in page["records"]:
                session.add(DynamicPdfRecord(
                    pdf_hash=pdf_hash,
                    filename=filename,
                    document_type=doc_name,
                    page_number=page["page_number"],
                    table_type=page["table_type"],
                    record=record,
                ))
                total_records += 1
        await session.commit()

    return {
        "pdf_hash": pdf_hash,
        "filename": filename,
        "pages_with_tables": [p["page_number"] for p in page_results],
        "tables": [
            {
                "table_type": p["table_type"],
                "page": p["page_number"],
                "records_stored": len(p["records"]),
                "sample": p["records"][0] if p["records"] else None,
            }
            for p in page_results
        ],
        "total_records": total_records,
    }
