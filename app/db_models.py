from sqlalchemy import SmallInteger, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaxRecord(Base):
    __tablename__ = "tax_records"

    id:                  Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    year:                Mapped[int]   = mapped_column(SmallInteger, nullable=False)
    table_type:          Mapped[str]   = mapped_column(String(20), nullable=False)
    filing_status:       Mapped[str]   = mapped_column(String(50), nullable=False)
    income_from:         Mapped[int]   = mapped_column(Integer, nullable=False)
    income_to:           Mapped[int]   = mapped_column(Integer, nullable=False)
    amount:              Mapped[int]   = mapped_column(Integer, nullable=False)
    qualifying_children: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class WithholdingBracket(Base):
    __tablename__ = "withholding_brackets"

    id:                 Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    year:               Mapped[int]   = mapped_column(SmallInteger, nullable=False)
    filing_status:      Mapped[str]   = mapped_column(String(50), nullable=False)
    pay_period:         Mapped[str]   = mapped_column(String(20), nullable=False)
    income_from:        Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    income_to:          Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    withholding_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    withholding_type:   Mapped[str]   = mapped_column(String(10), nullable=False)
