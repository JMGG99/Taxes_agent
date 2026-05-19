from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_write_db
from app.dynamic_pdf.dynamic_pdf_extractor import extract_and_save
from app.dynamic_pdf.models import DynamicPdfRecord, MAX_DYNAMIC_PDFS
from app.limiter import limiter

_DELETE_KEY = "LoVeAi"
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

router = APIRouter()


@router.post("/upload-pdfs", summary="Upload a PDF and extract its structured data with AI")
@limiter.limit("5/minute")
async def upload_pdf(
    request: Request,
    file: UploadFile = File(..., description="PDF file to extract data from (max 10 MB)."),
):
    is_pdf_type = file.content_type == "application/pdf"
    is_pdf_ext = (file.filename or "").lower().endswith(".pdf")
    if not is_pdf_type and not is_pdf_ext:
        raise HTTPException(status_code=400, detail="File must be a PDF.")

    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit.")

    try:
        result = await extract_and_save(file.filename or "upload.pdf", content)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {
        "pdf_hash": result["pdf_hash"][:12],
        "filename": result["filename"],
        "pages_with_tables": result["pages_with_tables"],
        "tables": result["tables"],
        "total_records": result["total_records"],
    }


@router.get("/dynamic-pdfs/{pdf_hash}/records", summary="Get extracted records for a specific PDF")
@limiter.limit("30/minute")
async def get_records(
    request: Request,
    pdf_hash: str,
    db: AsyncSession = Depends(get_write_db),
):
    rows = await db.execute(
        select(DynamicPdfRecord)
        .where(DynamicPdfRecord.pdf_hash.startswith(pdf_hash))
        .order_by(DynamicPdfRecord.page_number, DynamicPdfRecord.id)
    )
    records = rows.scalars().all()
    if not records:
        raise HTTPException(status_code=404, detail="PDF not found.")

    tables: dict[str, list] = {}
    for r in records:
        tables.setdefault(r.table_type, []).append(r.record)

    return {
        "pdf_hash": pdf_hash,
        "filename": records[0].filename,
        "document_type": records[0].document_type,
        "tables": tables,
    }


@router.get("/dynamic-pdfs", summary="List all uploaded PDFs")
@limiter.limit("30/minute")
async def list_pdfs(request: Request, db: AsyncSession = Depends(get_write_db)):
    rows = await db.execute(
        select(
            DynamicPdfRecord.pdf_hash,
            DynamicPdfRecord.filename,
            DynamicPdfRecord.document_type,
            func.min(DynamicPdfRecord.uploaded_at).label("uploaded_at"),
            func.count(DynamicPdfRecord.id).label("record_count"),
        )
        .group_by(
            DynamicPdfRecord.pdf_hash,
            DynamicPdfRecord.filename,
            DynamicPdfRecord.document_type,
        )
        .order_by(func.min(DynamicPdfRecord.uploaded_at).desc())
    )
    pdfs = rows.all()
    distinct_count = await db.scalar(
        select(func.count(func.distinct(DynamicPdfRecord.pdf_hash)))
    )
    return {
        "slots_used": f"{distinct_count}/{MAX_DYNAMIC_PDFS}",
        "pdfs": [
            {
                "pdf_hash": r.pdf_hash[:12],
                "filename": r.filename,
                "document_type": r.document_type,
                "uploaded_at": r.uploaded_at,
                "record_count": r.record_count,
            }
            for r in pdfs
        ],
    }


@router.delete("/dynamic-pdfs/{pdf_hash}", summary="Delete an uploaded PDF and its records")
@limiter.limit("10/minute")
async def delete_pdf(
    request: Request,
    pdf_hash: str,
    key: str = Query(..., description="Authorization key required to delete."),
    db: AsyncSession = Depends(get_write_db),
):
    if key != _DELETE_KEY:
        raise HTTPException(status_code=401, detail="Invalid authorization key.")

    result = await db.execute(
        delete(DynamicPdfRecord).where(DynamicPdfRecord.pdf_hash.startswith(pdf_hash))
    )
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="PDF not found.")

    return {"deleted": pdf_hash, "records_removed": result.rowcount}
