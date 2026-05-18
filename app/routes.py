from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.limiter import limiter
from app.models import TaxRecord, WithholdingBracket
from app.schemas import EICCreditResponse, TaxRecordResponse, WithholdingBracketResponse

router = APIRouter()


@router.get(
    "/tax-records",
    response_model=list[TaxRecordResponse],
    summary="Federal income tax bracket lookup (p1040 · 2025)",
)
@limiter.limit("100/minute")
async def get_tax_records(
    request: Request,
    income: int = Query(
        ...,
        ge=0,
        le=99999,
        description="Taxpayer's taxable income in whole dollars (0 – 99,999).",
    ),
    filing_status: Literal[
        "single",
        "married_filing_jointly",
        "married_filing_separately",
        "head_of_household",
    ] = Query(..., description="Filing status as reported on Form 1040."),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TaxRecord).where(
            TaxRecord.year         == 2025,
            TaxRecord.table_type   == "tax_table",
            TaxRecord.filing_status == filing_status,
            TaxRecord.income_from  <= income,
            TaxRecord.income_to    >  income,
        )
    )
    record = result.scalar_one_or_none()
    return [record] if record else []


@router.get(
    "/eic-credits",
    response_model=list[EICCreditResponse],
    summary="Earned Income Credit lookup (p596 · 2024–2025)",
)
@limiter.limit("100/minute")
async def get_eic_credits(
    request: Request,
    income: int = Query(
        ...,
        ge=1,
        description="Taxpayer's earned income in whole dollars (must be at least $1).",
    ),
    filing_status: Literal[
        "single_mfs_hh",
        "married_filing_jointly",
    ] = Query(
        ...,
        description=(
            "**single_mfs_hh** → Single, Married Filing Separately, or Head of Household. "
            "**married_filing_jointly** → Married filing a joint return."
        ),
    ),
    qualifying_children: Literal["0", "1", "2", "3"] = Query(
        ...,
        description="Number of qualifying children with valid SSNs.",
    ),
    year: Literal["2024", "2025"] = Query(
        ...,
        description="Tax year. Use 2025 for current returns, 2024 for prior-year amendments.",
    ),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TaxRecord).where(
            TaxRecord.year                == int(year),
            TaxRecord.table_type          == "eic",
            TaxRecord.filing_status       == filing_status,
            TaxRecord.qualifying_children == int(qualifying_children),
            TaxRecord.income_from         <= income,
            TaxRecord.income_to           >  income,
        )
    )
    record = result.scalar_one_or_none()
    return [record] if record else []


@router.get(
    "/withholding-brackets",
    response_model=list[WithholdingBracketResponse],
    summary="Wage bracket withholding lookup (p15t · 2025–2026)",
)
@limiter.limit("100/minute")
async def get_withholding_brackets(
    request: Request,
    income: float = Query(
        ...,
        ge=0,
        description=(
            "Employee's adjusted wage amount for the pay period, in dollars. "
            "max_values: (DAILY, $400) · (WEEKLY, $1,925) · (BIWEEKLY, $3,875) · (SEMIMONTHLY, $4,185) · (MONTHLY, $8,395). "
            "Returns [] if income exceeds the table — use the IRS percentage method (Pub. 15-T)."
        ),
    ),
    filing_status: Literal[
        "Married Filing Jointly",
        "Head of Household",
        "Single or Married Filing Separately",
    ] = Query(..., description="Filing status as declared on the employee's W-4 (2020 or later)."),
    pay_period: Literal[
        "WEEKLY",
        "BIWEEKLY",
        "SEMIMONTHLY",
        "MONTHLY",
        "DAILY",
    ] = Query(..., description="Payroll frequency used by the employer."),
    withholding_type: Literal["standard", "checkbox"] = Query(
        ...,
        description=(
            "**standard** → Step 2 checkbox on W-4 is NOT checked. "
            "**checkbox** → Step 2 checkbox IS checked (employee has multiple jobs or spouse works)."
        ),
    ),
    year: Literal["2025", "2026"] = Query(
        ...,
        description="Tax year of the withholding tables to use.",
    ),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WithholdingBracket).where(
            WithholdingBracket.year             == int(year),
            WithholdingBracket.filing_status    == filing_status,
            WithholdingBracket.pay_period       == pay_period,
            WithholdingBracket.withholding_type == withholding_type,
            WithholdingBracket.income_from      <= income,
            WithholdingBracket.income_to        >  income,
        )
    )
    record = result.scalar_one_or_none()
    return [record] if record else []
