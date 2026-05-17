# One-off analysis script — not part of the application.
import fitz  # PyMuPDF
import pdfplumber
import os
from collections import defaultdict

PDF_DIR = "data/pdfs"
PDFS = ["p1040.pdf", "p15t.pdf", "p596.pdf", "p505.pdf", "p15a.pdf"]

def is_text_embedded(path):
    doc = fitz.open(path)
    chars = sum(len(page.get_text("text").strip()) for page in doc)
    doc.close()
    return chars > 100

def analyze_with_pdfplumber(path):
    results = []
    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for t_idx, table in enumerate(tables):
                if not table:
                    continue
                # First non-empty row as header
                header = None
                for row in table:
                    if any(c and str(c).strip() for c in row):
                        header = [str(c).strip() if c else "" for c in row]
                        break
                num_cols = max(len(row) for row in table if row)
                results.append({
                    "page": i + 1,
                    "table_index": t_idx,
                    "num_cols": num_cols,
                    "header": header,
                    "num_rows": len(table),
                })
    return total_pages, results

def sample_text(path, pages=(0, 1, 2)):
    doc = fitz.open(path)
    snippets = []
    for p in pages:
        if p < len(doc):
            text = doc[p].get_text("text").strip()[:300]
            snippets.append((p + 1, text))
    doc.close()
    return snippets

for pdf_name in PDFS:
    path = os.path.join(PDF_DIR, pdf_name)
    print("=" * 70)
    print(f"PDF: {pdf_name}")
    print("=" * 70)

    embedded = is_text_embedded(path)
    print(f"  Text embedded: {'YES' if embedded else 'NO (likely scanned)'}")

    total_pages, table_data = analyze_with_pdfplumber(path)
    print(f"  Total pages  : {total_pages}")

    if not table_data:
        print("  Tables found : NONE detected by pdfplumber")
    else:
        pages_with_tables = sorted(set(t["page"] for t in table_data))
        print(f"  Tables found : {len(table_data)} across pages {pages_with_tables[:30]}")
        # Group by page
        by_page = defaultdict(list)
        for t in table_data:
            by_page[t["page"]].append(t)

        shown = 0
        for page_num in sorted(by_page.keys()):
            for t in by_page[page_num]:
                print(f"\n  [Page {page_num}, Table {t['table_index'] + 1}]")
                print(f"    Columns : {t['num_cols']}")
                print(f"    Rows    : {t['num_rows']}")
                print(f"    Header  : {t['header']}")
            shown += 1
            if shown >= 8:
                remaining = len(by_page) - shown
                if remaining > 0:
                    print(f"\n  ... and {remaining} more pages with tables (pattern repeats)")
                break

    print("\n  --- Text sample (first 2 pages) ---")
    for page_num, snippet in sample_text(path, pages=[0, 1]):
        print(f"  Page {page_num}: {repr(snippet[:200])}")
    print()
