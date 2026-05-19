from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

MAX_DYNAMIC_PDFS = 5


class DynamicPdfRecord(Base):
    __tablename__ = "dynamic_pdf_records"

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    pdf_hash:      Mapped[str]      = mapped_column(String(64), nullable=False, index=True)
    filename:      Mapped[str]      = mapped_column(String(255), nullable=False)
    document_type: Mapped[str]      = mapped_column(String(255), nullable=False)
    page_number:   Mapped[int]      = mapped_column(Integer, nullable=False)
    table_type:    Mapped[str]      = mapped_column(String(100), nullable=False)
    record:        Mapped[dict]     = mapped_column(JSONB, nullable=False)
    uploaded_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
