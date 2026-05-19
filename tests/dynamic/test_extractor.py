"""Quick test for the per-page PDF extractor + DB write. Run from project root:
   PYTHONPATH=. python tests/test_extractor.py
"""
import asyncio
import json
from pathlib import Path

from app.dynamic_pdf.dynamic_pdf_extractor import extract_and_save

PDF_PATH = Path("data/pdfs/tablas_impuestos_federales_2026.pdf")


async def main():
    print(f"Reading {PDF_PATH} ...")
    file_bytes = PDF_PATH.read_bytes()

    print("\nRunning per-page extraction + DB write ...")
    result = await extract_and_save(PDF_PATH.name, file_bytes)

    print(f"\nFilename          : {result['filename']}")
    print(f"Pages with tables : {result['pages_with_tables']}")
    print(f"Total records     : {result['total_records']}")
    print(f"\nTables detected:")
    for t in result["tables"]:
        print(f"  page {t['page']} → [{t['table_type']}] {t['records_stored']} records")
        if t.get("sample"):
            print(f"  sample: {json.dumps(t['sample'], indent=4)}")


if __name__ == "__main__":
    asyncio.run(main())
