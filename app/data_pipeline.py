import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pdfplumber

BASE_DIR = Path(__file__).parent.parent

PDF_SOURCES = [
    {"path": str(BASE_DIR / "data/pdfs/p1040_2025.pdf"), "extractor": "p1040", "year": 2025},
    {"path": str(BASE_DIR / "data/pdfs/p596_2024.pdf"),  "extractor": "p596",  "year": 2024},
    {"path": str(BASE_DIR / "data/pdfs/p596_2025.pdf"),  "extractor": "p596",  "year": 2025},
    {"path": str(BASE_DIR / "data/pdfs/p15t_2025.pdf"),  "extractor": "p15t",  "year": 2025},
    {"path": str(BASE_DIR / "data/pdfs/p15t_2026.pdf"),  "extractor": "p15t",  "year": 2026},
]


## extracting p1040
def extract_p1040(pdf_path: str) -> list[dict]:
    nums_re = re.compile(r'\d[\d,]*')
    valid_widths = {5, 10, 25, 50}
    #Tuples of label, field
    statuses = [
        ('single',                    'single'),
        ('married_filing_jointly',    'married_filing_jointly'),
        ('married_filing_separately', 'married_filing_separately'),
        ('head_of_household',         'head_of_household'),
    ]

    def to_int(s: str) -> int:
        return int(s.replace(",",""))
    
    def process_lines(line: str) -> list[dict]:
        nums = nums_re.findall(line)
        records: list[dict] = []
        i = 0

        while i+5<len(nums):
            tax_line = nums[i:i+6]
            lower_limit = to_int(tax_line[0])
            upper_limit = to_int(tax_line[1])
            width = upper_limit-lower_limit

            if width in valid_widths and upper_limit%5==0 and lower_limit%5==0 and (0 <= lower_limit < 100_000):
                records.append({
                    "income_from"               : lower_limit,
                    "income_to"                 : upper_limit,
                    "single"                    : to_int(tax_line[2]),
                    "married_filing_jointly"    : to_int(tax_line[3]),
                    "married_filing_separately" : to_int(tax_line[4]),
                    "head_of_household"         : to_int(tax_line[5]),
                })
                i += 6

            else:
                i += 1

        return records
        
    results = []
    seen_bands : set[tuple[int,int]] = set()

    with pdfplumber.open(pdf_path) as pdf:
        for pg_idx in range(1,13):
            text = pdf.pages[pg_idx].extract_text() or ""
            for line in text.split("\n"):
                for raw in process_lines(line):
                    band = (raw["income_from"], raw["income_to"])
                    if band in seen_bands:
                        continue
                    seen_bands.add(band)
                    for label, field in statuses:
                        results.append({
                            'table_type'    : 'tax_table',
                            'filing_status' : label,
                            'income_from'   : raw['income_from'],
                            'income_to'     : raw['income_to'],
                            'tax_amount'    : raw[field],
                            'raw_data'      : raw,
                        })

    return results

## Extracting p596
def extract_p596(pdf_path: str) -> list[dict]:
    num_re = re.compile(r'[\d,]+')

    def to_int(s: str) -> int:
        return int(s.replace(',', ''))
    
    def is_eic_table(table) -> bool:
        if not table:
            return False
        try:
            ncols = max(len(r) for r in table if r)
        except ValueError:
            return False
        
        if ncols != 4:
            return False
        
        for row in table[0:3]:
            for cell in row:
                if cell and "credit" in cell.lower():
                    return True
        return False

    def parse_credit(s: str):
        nums = num_re.findall(re.sub(r'\*+', '0', s.strip()))
        return [to_int(n) for n in nums] if len(nums) == 4 else None
    
    def parse_subrow(c0: str, c2: str, c3:str):
        nums = num_re.findall(c0.strip())
        if len(nums)<2:
            return None
        try:
            lower_limit, upper_limit = to_int(nums[0]), to_int(nums[1])
        except ValueError:
            return None
        
        sgl = parse_credit(c2)
        married = parse_credit(c3)


        if sgl is None or married is None:
            return None
        
        return {
        'income_from': lower_limit, 'income_to': upper_limit,
        'single_0': sgl[0], 'single_1': sgl[1], 'single_2': sgl[2], 'single_3': sgl[3],
        'mfj_0':    married[0], 'mfj_1':    married[1], 'mfj_2':    married[2], 'mfj_3':    married[3],
        }
    
    raw_bands : list[dict] = []
    seen_bands : set[tuple[int,int]] = set()

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not is_eic_table(table):
                    continue

                for row in table[3:]:
                    if not row or row[0] is None:
                        continue
                    lines0 = (row[0] or "").split("\n")
                    lines2 = (row[2] or "").split('\n')
                    lines3 = (row[3] or "").split('\n')
                    n = min(len(lines0), len(lines2), len(lines3))

                    for i in range(n):
                        raw = parse_subrow(lines0[i], lines2[i], lines3[i])

                        if raw is None:
                            continue

                        band = (raw["income_from"], raw["income_to"])
                        if band in seen_bands:
                            continue
                        seen_bands.add(band)
                        raw_bands.append(raw)


    raw_bands.sort(key=lambda r: r['income_from'])           

    statuses = [
        ('single_mfs_hh',         'single'),
        ('married_filing_jointly', 'mfj'),]
    
    results: list[dict] = []

    for raw in raw_bands:
        for filing_status, prefix in statuses:
            for children in range(4):
                results.append({
                'table_type'          : 'eic',
                'filing_status'       : filing_status,
                'income_from'         : raw['income_from'],
                'income_to'           : raw['income_to'],
                'credit_amount'       : raw[f'{prefix}_{children}'],
                'qualifying_children' : children,
                'raw_data'            : raw,
            })
    return results

##Extracting 15T
def extract_p15t(pdf_path: str) -> list[dict]:
    payment_periods = r"(WEEKLY|BIWEEKLY|SEMIMONTHLY|MONTHLY|DAILY)"

    S2_COLUMNS = [
        ("Married Filing Jointly",              "standard"),
        ("Married Filing Jointly",              "checkbox"),
        ("Head of Household",                   "standard"),
        ("Head of Household",                   "checkbox"),
        ("Single or Married Filing Separately", "standard"),
        ("Single or Married Filing Separately", "checkbox"),
    ]

    def to_num(s: str) -> float:
        return float(s.replace("$", "").replace(",", ""))

    results: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""

            if not ("Wage Bracket Method Tables" in text and "2020 or Later" in text):
                continue

            pp_m = re.search(payment_periods + r"\s+Payroll Period", text)

            if not pp_m:
                continue
            
            pay_period = pp_m.group(1)

            for line in text.split("\n"):
                parts = line.split()

                if len(parts) != 8:
                    continue
                if not (parts[0].startswith("$") and parts[1].startswith("$")):
                    continue

                try:
                    income_from = to_num(parts[0])
                    income_to   = to_num(parts[1])
                    amounts     = [to_num(p) for p in parts[2:]]
                except ValueError:
                    continue

                
                for (filing_status, wh_type), amount in zip(S2_COLUMNS, amounts):
                    results.append({
                        "table_type":         "wage_bracket_2020plus",
                        "filing_status":       filing_status,
                        "pay_period":          pay_period,
                        "income_from":         income_from,
                        "income_to":           income_to,
                        "withholding_amount":  amount,
                        "raw_data": {
                            "withholding_type": wh_type,
                            "page":             page_idx + 1,
                            "row":              parts,
                        },
                    })

    return results


def _extract(source: dict) -> tuple[str, int, list[dict]]:
    extractors = {
        "p1040": extract_p1040,
        "p596":  extract_p596,
        "p15t":  extract_p15t,
    }
    records = extractors[source["extractor"]](source["path"])
    return source["extractor"], source["year"], records


def _normalize_tax_records(extractor: str, year: int, records: list[dict]):
    from app.db_models import TaxRecord
    orm_objects = []
    for r in records:
        if extractor == "p1040":
            amount              = -r["tax_amount"]   # money owed → negative
            qualifying_children = None
            table_type          = "tax_table"
        else:
            amount              = r["credit_amount"]  # EIC credit → positive
            qualifying_children = r["qualifying_children"]
            table_type          = "eic"

        orm_objects.append(TaxRecord(
            year=year,
            table_type=table_type,
            filing_status=r["filing_status"],
            income_from=r["income_from"],
            income_to=r["income_to"],
            amount=amount,
            qualifying_children=qualifying_children,
        ))
    return orm_objects


def _normalize_withholding(year: int, records: list[dict]):
    from app.db_models import WithholdingBracket
    return [
        WithholdingBracket(
            year=year,
            filing_status=r["filing_status"],
            pay_period=r["pay_period"],
            income_from=r["income_from"],
            income_to=r["income_to"],
            withholding_amount=r["withholding_amount"],
            withholding_type=r["raw_data"]["withholding_type"],
        )
        for r in records
    ]


async def run_pipeline(session) -> dict:
    from sqlalchemy import select
    from app.db_models import TaxRecord

    existing = await session.scalar(select(TaxRecord).limit(1))
    if existing is not None:
        return {"status": "already_loaded"}

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [loop.run_in_executor(pool, _extract, source) for source in PDF_SOURCES]
        results = await asyncio.gather(*futures)

    summary = {}
    for extractor, year, records in results:
        key = f"{extractor}_{year}"
        if extractor in ("p1040", "p596"):
            orm_objects = _normalize_tax_records(extractor, year, records)
        else:
            orm_objects = _normalize_withholding(year, records)
        session.add_all(orm_objects)
        summary[key] = len(orm_objects)

    await session.commit()
    return {"status": "loaded", "records": summary}