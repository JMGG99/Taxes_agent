from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.models import TaxRecord, WithholdingBracket

router = APIRouter()


@router.get("/tax-records")
async def get_tax_records(
    year:           Optional[int] = Query(None, description="Tax year, e.g. 2024 or 2025"),
    table_type:     Optional[str] = Query(None, description="'tax_table' or 'eic'"),
    filing_status:  Optional[str] = Query(None, description="Filing status value"),
    db: AsyncSession = Depends(get_db),
):
    """Return tax bracket and EIC credit records.

    Negative amount = tax owed (p1040).
    Positive amount = EIC credit returned to taxpayer (p596).
    """
    query = select(TaxRecord)
    if year:
        query = query.where(TaxRecord.year == year)
    if table_type:
        query = query.where(TaxRecord.table_type == table_type)
    if filing_status:
        query = query.where(TaxRecord.filing_status == filing_status)

    result = await db.execute(query)
    records = result.scalars().all()

    return [
        {
            "id":                   r.id,
            "year":                 r.year,
            "table_type":           r.table_type,
            "filing_status":        r.filing_status,
            "income_from":          r.income_from,
            "income_to":            r.income_to,
            "amount":               r.amount,
            "qualifying_children":  r.qualifying_children,
        }
        for r in records
    ]


@router.get("/withholding-brackets")
async def get_withholding_brackets(
    year:           Optional[int] = Query(None, description="Tax year, e.g. 2025 or 2026"),
    pay_period:     Optional[str] = Query(None, description="WEEKLY | BIWEEKLY | SEMIMONTHLY | MONTHLY | DAILY"),
    filing_status:  Optional[str] = Query(None, description="Filing status value"),
    db: AsyncSession = Depends(get_db),
):
    """Return wage bracket withholding records from p15t (2020+ W-4 only)."""
    query = select(WithholdingBracket)
    if year:
        query = query.where(WithholdingBracket.year == year)
    if pay_period:
        query = query.where(WithholdingBracket.pay_period == pay_period)
    if filing_status:
        query = query.where(WithholdingBracket.filing_status == filing_status)

    result = await db.execute(query)
    records = result.scalars().all()

    return [
        {
            "id":                   r.id,
            "year":                 r.year,
            "filing_status":        r.filing_status,
            "pay_period":           r.pay_period,
            "income_from":          float(r.income_from),
            "income_to":            float(r.income_to),
            "withholding_amount":   float(r.withholding_amount),
            "withholding_type":     r.withholding_type,
        }
        for r in records
    ]
