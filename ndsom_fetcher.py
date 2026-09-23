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

    value = value.replace(",", "")
    value = value.replace("%", "")

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
# READ A TABLE
# ============================================================

async def read_table(table):
    """
    Convert a Playwright HTML table into a list of dictionaries.
    Header names are used rather than fixed column positions.
    """

    rows = table.locator("tr")
    row_count = await rows.count()

    if row_count == 0:
        return []

    # --------------------------------------------------------
    # Find header row
    # --------------------------------------------------------

    headers = None
    header_row_index = None

    for i in range(min(row_count, 5)):

        cells = rows.nth(i).locator("th, td")
        cell_count = await cells.count()

        if cell_count == 0:
            continue

        values = []

        for j in range(cell_count):
            values.append(
                clean_text(await cells.nth(j).inner_text())
            )

        normalized = [normalize_header(x) for x in values]

        has_security = any(
            "security" in x for x in normalized
        )

        has_maturity = any(
            "maturity" in x for x in normalized
        )

        has_lty = any(
            x == "lty" or "last traded yield" in x
            for x in normalized
        )

        if has_security and has_maturity and has_lty:
            headers = normalized
            header_row_index = i
            break

    if headers is None:
        return []

    # --------------------------------------------------------
    # Read data rows
    # --------------------------------------------------------

    data = []

    for i in range(header_row_index + 1, row_count):

        cells = rows.nth(i).locator("td")
        cell_count = await cells.count()

        if cell_count == 0:
            continue

        values = []

        for j in range(cell_count):
            values.append(
                clean_text(await cells.nth(i).locator("td").nth(j).inner_text())
            )

        if not values:
            continue

        row = {}

        for j, value in enumerate(values):

            if j < len(headers):
                row[headers[j]] = value

        data.append(row)

    return data


# ============================================================
# FIND FIELD
# ============================================================

def get_field(row, possible_names):

    for key, value in row.items():

        key_normalized = normalize_header(key)

        for name in possible_names:

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

    maturity = parse_date(maturity_raw)

    lty = parse_number(lty_raw)
    ltp = parse_number(ltp_raw)

    return {
        "security_description": security,
        "maturity_date": maturity,
        "lty": lty,
        "ltp": ltp,
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

            if not await table.is_visible():
                continue

            rows = await read_table(table)

            normalized_rows = [
                normalize_row(x)
                for x in rows
            ]

            valid = []

            for row in normalized_rows:

                security = row["security_description"]

                if not security:
                    continue

                if row["maturity_date"] is None:
                    continue

                if row["lty"] is None or row["lty"] <= 0:
                    continue

                # G-Secs generally contain GS / FRB etc.
                # Explicitly exclude DTB rows.
                if re.search(
                    r"\bDTB\b",
                    security,
                    re.IGNORECASE,
                ):
                    continue

                valid.append(row)

            if len(valid) >= 3:
                candidates.append(
                    (i, valid)
                )

        except Exception:
            continue

    if not candidates:
        return []

    # Pick the table with the most valid G-Sec rows
    candidates.sort(
        key=lambda x: len(x[1]),
        reverse=True,
    )

    return candidates[0][1]


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

            normalized_rows = [
                normalize_row(x)
                for x in rows
            ]

            valid = []

            for row in normalized_rows:

                security = row["security_description"]

                if not security:
                    continue

                if row["maturity_date"] is None:
                    continue

                if row["lty"] is None or row["lty"] <= 0:
                    continue

                # ====================================================
                # CRITICAL:
                #
                # T-Bills have DTB in the security description.
                #
                # Examples:
                # 091 DTB 27112026
                # 182 DTB 18032027
                # 364 DTB 16092027
                #
                # This prevents G-Secs from being mistaken as T-Bills.
                # ====================================================

                if not re.search(
                    r"\bDTB\b",
                    security,
                    re.IGNORECASE,
                ):
                    continue

                valid.append(row)

            # We need a genuine T-Bill table
            if len(valid) >= 2:

                candidates.append(
                    (i, valid)
                )

        except Exception:
            continue

    if not candidates:
        return []

    # Pick table having the largest number of DTB rows
    candidates.sort(
        key=lambda x: len(x[1]),
        reverse=True,
    )

    selected = candidates[0][1]

    return selected


# ============================================================
# SELECT G-SECS
# ============================================================

def select_gsecs(rows):

    today = date.today()

    valid = []

    for row in rows:

        maturity = row["maturity_date"]
        security = row["security_description"]
        lty = row["lty"]

        if not maturity:
            continue

        if not security:
            continue

        if lty is None or lty <= 0:
            continue

        # Do not allow T-Bills into G-Sec selection
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

    if not valid:
        return []

    targets = {
        "2Y": 365 * 2,
        "5Y": 365 * 5,
        "10Y": 365 * 10,
    }

    selected = []

    used = set()

    for tenor, target_days in targets.items():

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
            key=lambda row: abs(
                row["residual_days"]
                - target_days
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
        maturity = row["maturity_date"]
        lty = row["lty"]

        if not security:
            continue

        if not maturity:
            continue

        if lty is None or lty <= 0:
            continue

        # ----------------------------------------------------
        # Identify T-Bill bucket from SECURITY DESCRIPTION
        # ----------------------------------------------------

        match = re.search(
            r"^\s*(0?91|182|364)\s+DTB\b",
            security,
            re.IGNORECASE,
        )

        if not match:
            continue

        bucket = match.group(1)

        if bucket in ("091", "91"):
            tenor = "91D"

        elif bucket == "182":
            tenor = "182D"

        elif bucket == "364":
            tenor = "364D"

        else:
            continue

        row["tenor"] = tenor

        valid.append(row)

    print(
        f"VALID T-BILLS: {len(valid)}"
    )

    # --------------------------------------------------------
    # Select one security for each bucket
    # --------------------------------------------------------

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

        # Prefer the earliest maturity within
        # the relevant T-Bill bucket.
        candidates.sort(
            key=lambda x: x["maturity_date"]
        )

        selected.append(
            candidates[0]
        )

    return selected


# ============================================================
# MAIN PLAYWRIGHT FETCHER
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

            # ====================================================
            # G-SEC
            # ====================================================

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

            # ====================================================
            # CLICK T-BILLS TAB
            # ====================================================

            print(
                "Looking for T-Bills tab..."
            )

            tbill_clicked = False

            selectors = [
                "text=T-Bills Mkt. Watch",
                "text=T-Bills",
                "text=T Bill",
                "text=TBills",
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

                        tbill_clicked = True

                        print(
                            "T-Bill tab clicked:",
                            selector,
                        )

                        break

                except Exception:
                    continue

            if not tbill_clicked:

                print(
                    "WARNING: T-Bill tab could not be clicked"
                )

            await page.wait_for_timeout(
                3000
            )

            # ====================================================
            # T-BILL TABLE
            # ====================================================

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
                "================================================"
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
                "================================================"
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
# LOCAL TEST
# ============================================================

if __name__ == "__main__":

    data = fetch_ndsom_data()

    print("\nG-SECS:")

    for row in data["gsecs"]:
        print(row)

    print("\nT-BILLS:")

    for row in data["tbills"]:
        print(row)
