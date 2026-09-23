import asyncio
import re
from datetime import datetime, date

from playwright.async_api import async_playwright


CCIL_URL = "https://www.ccilindia.com/market-watch"


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_date(value):
    value = clean_text(value)

    if not value:
        return None

    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d %b %Y",
        "%d %B %Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except Exception:
            pass

    return None


def parse_number(value):
    value = clean_text(value)

    if not value:
        return None

    value = value.replace(",", "").replace("%", "")

    try:
        return float(value)
    except Exception:
        return None


def normalize_header(value):
    value = clean_text(value).lower()
    value = value.replace(".", "")
    value = value.replace("-", " ")
    value = re.sub(r"\s+", " ", value)
    return value


# ============================================================
# READ TABLE
# ============================================================

async def read_table(table):

    rows = table.locator("tr")
    row_count = await rows.count()

    if row_count == 0:
        return []

    headers = None
    header_row_index = None

    # Find header row
    for i in range(min(row_count, 5)):

        cells = rows.nth(i).locator("th, td")
        cell_count = await cells.count()

        if cell_count == 0:
            continue

        values = []

        for j in range(cell_count):
            values.append(
                clean_text(
                    await cells.nth(j).inner_text()
                )
            )

        normalized = [
            normalize_header(x)
            for x in values
        ]

        # CCIL table header normally contains
        # Security Description + Maturity Date
        if (
            any("security" in x for x in normalized)
            and
            any("maturity" in x for x in normalized)
        ):
            headers = normalized
            header_row_index = i
            break

    if headers is None:
        return []

    # Read data rows
    data = []

    for i in range(header_row_index + 1, row_count):

        cells = rows.nth(i).locator("td")
        cell_count = await cells.count()

        if cell_count == 0:
            continue

        values = []

        for j in range(cell_count):

            # IMPORTANT:
            # use j here, not i
            value = clean_text(
                await cells.nth(j).inner_text()
            )

            values.append(value)

        if not values:
            continue

        row = {}

        for j, value in enumerate(values):

            if j < len(headers):
                row[headers[j]] = value

        data.append(row)

    return data


# ============================================================
# GET FIELD
# ============================================================

def get_field(row, names):

    for key, value in row.items():

        key_normalized = normalize_header(key)

        for name in names:

            if key_normalized == name:
                return clean_text(value)

    return ""


# ============================================================
# NORMALIZE ROW
# ============================================================

def normalize_row(row):

    security = get_field(
        row,
        [
            "security description",
            "security",
        ],
    )

    maturity_raw = get_field(
        row,
        [
            "maturity date",
            "maturity",
        ],
    )

    lty_raw = get_field(
        row,
        [
            "lty",
            "last traded yield",
        ],
    )

    ltp_raw = get_field(
        row,
        [
            "ltp",
            "last traded price",
        ],
    )

    return {
        "security_description": security,
        "maturity_date": parse_date(maturity_raw),
        "lty": parse_number(lty_raw),
        "ltp": parse_number(ltp_raw),
    }


# ============================================================
# FIND G-SEC TABLE
# ============================================================

async def find_gsec_table(page):

    tables = page.locator("table")
    count = await tables.count()

    candidates = []

    for i in range(count):

        try:

            table = tables.nth(i)

            rows = await read_table(table)

            normalized = [
                normalize_row(x)
                for x in rows
            ]

            valid = []

            for row in normalized:

                security = row["security_description"]

                if not security:
                    continue

                if row["maturity_date"] is None:
                    continue

                if row["lty"] is None:
                    continue

                if row["lty"] <= 0:
                    continue

                # Do not treat T-Bills as G-Secs
                if re.search(
                    r"\bDTB\b",
                    security,
                    re.IGNORECASE,
                ):
                    continue

                valid.append(row)

            if len(valid) >= 3:
                candidates.append(valid)

        except Exception:
            continue

    if not candidates:
        return []

    candidates.sort(
        key=len,
        reverse=True,
    )

    return candidates[0]


# ============================================================
# FIND T-BILL TABLE
# ============================================================

async def find_tbill_table(page):

    tables = page.locator("table")
    count = await tables.count()

    candidates = []

    for i in range(count):

        try:

            table = tables.nth(i)

            rows = await read_table(table)

            normalized = [
                normalize_row(x)
                for x in rows
            ]

            valid = []

            for row in normalized:

                security = row["security_description"]

                if not security:
                    continue

                if row["maturity_date"] is None:
                    continue

                if row["lty"] is None:
                    continue

                if row["lty"] <= 0:
                    continue

                # ==================================================
                # CRITICAL T-BILL FILTER
                #
                # Only accept securities containing DTB.
                # ==================================================

                if not re.search(
                    r"\bDTB\b",
                    security,
                    re.IGNORECASE,
                ):
                    continue

                valid.append(row)

            if len(valid) >= 2:
                candidates.append(valid)

        except Exception:
            continue

    if not candidates:
        return []

    candidates.sort(
        key=len,
        reverse=True,
    )

    return candidates[0]


# ============================================================
# SELECT G-SECS
# ============================================================

def select_gsecs(rows):

    today = date.today()

    valid = []

    for row in rows:

        security = row["security_description"]
        maturity = row["maturity_date"]
        lty = row["lty"]

        if not security or not maturity:
            continue

        if lty is None or lty <= 0:
            continue

        if re.search(
            r"\bDTB\b",
            security,
            re.IGNORECASE,
        ):
            continue

        residual_days = (
            maturity - today
        ).days

        if residual_days <= 0:
            continue

        row["residual_days"] = residual_days

        valid.append(row)

    print(
        f"VALID G-SECS: {len(valid)}"
    )

    targets = {
        "2Y": 365 * 2,
        "5Y": 365 * 5,
        "10Y": 365 * 10,
    }

    selected = []
    used = set()

    for tenor, target in targets.items():

        candidates = [
            row
            for row in valid
            if row["security_description"]
            not in used
        ]

        if not candidates:
            continue

        best = min(
            candidates,
            key=lambda row:
            abs(
                row["residual_days"]
                - target
            ),
        )

        best["tenor"] = tenor

        selected.append(best)

        used.add(
            best["security_description"]
        )

    return selected


# ============================================================
# SELECT T-BILLS
# ============================================================

def select_tbills(rows):

    valid = []

    for row in rows:

        security = row["security_description"]

        if not security:
            continue

        if row["maturity_date"] is None:
            continue

        if row["lty"] is None or row["lty"] <= 0:
            continue

        # Must contain DTB
        match = re.search(
            r"^\s*(091|91|182|364)\s+DTB\b",
            security,
            re.IGNORECASE,
        )

        if not match:
            continue

        code = match.group(1)

        if code in ("091", "91"):
            tenor = "91D"

        elif code == "182":
            tenor = "182D"

        elif code == "364":
            tenor = "364D"

        else:
            continue

        row["tenor"] = tenor

        valid.append(row)

    print(
        f"VALID T-BILLS: {len(valid)}"
    )

    selected = []

    for tenor in [
        "91D",
        "182D",
        "364D",
    ]:

        candidates = [
            row
            for row in valid
            if row["tenor"] == tenor
        ]

        if not candidates:

            print(
                f"No T-Bill found for {tenor}"
            )

            continue

        # Select nearest maturity
        # for that specific bucket.
        candidates.sort(
            key=lambda x:
            x["maturity_date"]
        )

        selected.append(
            candidates[0]
        )

    return selected


# ============================================================
# MAIN FETCHER
# ============================================================

async def _fetch_ndsom_data():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={
                "width": 1920,
                "height": 1080,
            }
        )

        try:

            print(
                "Opening CCIL Market Watch..."
            )

            await page.goto(
                CCIL_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(
                5000
            )

            # ==================================================
            # G-SECS
            # ==================================================

            print(
                "Reading G-Sec Market Watch..."
            )

            gsec_raw = await find_gsec_table(
                page
            )

            print(
                f"RAW G-SECS FOUND: {len(gsec_raw)}"
            )

            gsecs = select_gsecs(
                gsec_raw
            )

            for row in gsecs:

                print(
                    "G-SEC:",
                    row["tenor"],
                    "|",
                    row["security_description"],
                    "|",
                    row["maturity_date"],
                    "|",
                    row["residual_days"],
                    "days | LTY",
                    row["lty"],
                    "| LTP",
                    row["ltp"],
                )

            # ==================================================
            # T-BILL TAB
            # ==================================================

            print(
                "Looking for T-Bills tab..."
            )

            clicked = False

            selectors = [
                "text=T-Bills Mkt. Watch",
                "text=T-Bills",
            ]

            for selector in selectors:

                try:

                    locator = page.locator(
                        selector
                    ).first

                    if await locator.count() > 0:

                        await locator.click(
                            timeout=5000
                        )

                        clicked = True

                        print(
                            "T-Bill tab clicked:",
                            selector,
                        )

                        break

                except Exception:
                    continue

            if not clicked:

                print(
                    "WARNING: Could not click T-Bill tab"
                )

            await page.wait_for_timeout(
                3000
            )

            # ==================================================
            # T-BILLS
            # ==================================================

            print(
                "Searching specifically for DTB rows..."
            )

            tbill_raw = await find_tbill_table(
                page
            )

            print(
                f"RAW T-BILLS FOUND: {len(tbill_raw)}"
            )

            tbills = select_tbills(
                tbill_raw
            )

            for row in tbills:

                print(
                    "T-BILL:",
                    row["tenor"],
                    "|",
                    row["security_description"],
                    "|",
                    row["maturity_date"],
                    "| LTY",
                    row["lty"],
                    "| LTP",
                    row["ltp"],
                )

            print(
                "========================================"
            )

            print(
                "FINAL NDS-OM RESULT"
            )

            print(
                f"G-Secs: {len(gsecs)}"
            )

            print(
                f"T-Bills: {len(tbills)}"
            )

            print(
                "========================================"
            )

            return {
                "gsecs": gsecs,
                "tbills": tbills,
            }

        finally:

            await browser.close()


# ============================================================
# PUBLIC FUNCTION
# ============================================================

def fetch_ndsom_data():

    return asyncio.run(
        _fetch_ndsom_data()
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    data = fetch_ndsom_data()

    print("\nG-SECS:")

    for row in data["gsecs"]:
        print(row)

    print("\nT-BILLS:")

    for row in data["tbills"]:
        print(row)
