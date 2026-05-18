import asyncio
import json

from sqlalchemy import text

from app.database import AsyncSessionLocal

MAX_ROWS = 50
_main_loop: asyncio.AbstractEventLoop | None = None


def setup_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


async def _run_sql_query(query: str) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text(query))
        rows = result.mappings().fetchmany(MAX_ROWS)
        records = [dict(row) for row in rows]
        response = {"results": records, "count": len(records)}
        if len(records) >= MAX_ROWS:
            response["note"] = (
                f"Results limited to {MAX_ROWS} rows. "
                "For complete IRS data visit https://www.irs.gov/publications"
            )
        return response


def run_sql_query(query: str) -> str:
    if not query.strip().upper().startswith("SELECT"):
        return json.dumps({"error": "Only SELECT statements are allowed."})

    future = asyncio.run_coroutine_threadsafe(_run_sql_query(query), _main_loop)
    return json.dumps(future.result(timeout=30), default=str)
