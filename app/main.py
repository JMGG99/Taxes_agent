from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine, Base, AsyncSessionLocal
from app.pipeline import run_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Load PDFs into the database (skips if already loaded)
    async with AsyncSessionLocal() as session:
        summary = await run_pipeline(session)
        print(f"Pipeline: {summary}")

    yield


app = FastAPI(
    title="IRS Tax Tables API",
    description="Structured tax data extracted from IRS publications.",
    version="1.0.0",
    lifespan=lifespan,
)

from app.routes import router          # noqa: E402
app.include_router(router)
