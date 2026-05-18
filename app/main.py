import asyncio
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import engine, Base, AsyncSessionLocal, get_db
from app.limiter import limiter
from app.db_models import TaxRecord, WithholdingBracket
from app.data_pipeline import run_pipeline
from app.agent_tools import setup_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_loop(asyncio.get_running_loop())

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        summary = await run_pipeline(session)
        print(f"Pipeline: {summary}")

    yield


app = FastAPI(
    title="IRS Tax Tables API",
    description="Structured tax data extracted from IRS publications.",
    version="2.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from app.routes import router          # noqa: E402
from app.agent_routes import router as agent_router  # noqa: E402
app.include_router(router, tags=["tax queries"])
app.include_router(agent_router, tags=["agent"])


@app.get("/health", summary="Health check", tags=["info"])
async def health():
    """Returns ok if the service is running."""
    return {"status": "ok"}


@app.get("/stats", summary="Record counts and years loaded per table", tags=["info"])
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Returns total record counts and a per-year breakdown for each table."""
    def by_year(rows):
        return [{"year": year, "count": count} for year, count in sorted(rows)]

    tax_rows = (await db.execute(
        select(TaxRecord.year, func.count())
        .where(TaxRecord.table_type == "tax_table")
        .group_by(TaxRecord.year)
    )).all()

    eic_rows = (await db.execute(
        select(TaxRecord.year, func.count())
        .where(TaxRecord.table_type == "eic")
        .group_by(TaxRecord.year)
    )).all()

    wh_rows = (await db.execute(
        select(WithholdingBracket.year, func.count())
        .group_by(WithholdingBracket.year)
    )).all()

    return {
        "tax_records":          {"total": sum(r[1] for r in tax_rows), "by_year": by_year(tax_rows)},
        "eic_credits":          {"total": sum(r[1] for r in eic_rows), "by_year": by_year(eic_rows)},
        "withholding_brackets": {"total": sum(r[1] for r in wh_rows),  "by_year": by_year(wh_rows)},
    }
