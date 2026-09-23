import asyncio
from datetime import datetime
from itertools import combinations, permutations

from playwright.async_api import async_playwright


CCIL_URL = "https://www.ccilindia.com/market-watch"


# ============================================================
# HELPERS
# ============================================================

def clean_number(value):

    if value is None:
        return None

    text = str(value).strip()
    text = text.replace(",", "")

    if text in ("", "-", "—", "NA", "N/A", "null", "None"):
        return None

    try:
        return float(text)
    except Exception:
        return None


def parse_date(value):

    if value is None:
        return None

    text = str(value).strip()

    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%d-%m-%y"
    ]

    for fmt in formats:

        try:
            return datetime.strptime(
                text,
                fmt
            ).date()

        except Exception:
            pass

    return None


def find_column(record, names):

    normalized = {}

    for key in record.keys():

        clean_key = (
            str(key)
            .strip()
            .lower()
            .replace(" ", "")
            .replace(".", "")
            .replace("-", "")
            .replace("_", "")
            .replace("(", "")
            .replace(")", "")
        )

        normalized[clean_key] = key

    for name in names:

        clean_name = (
            name
            .lower()
            .replace(" ", "")
            .replace(".", "")
            .replace("-", "")
            .replace("_", "")
            .replace("(", "")
            .replace(")", "")
        )

        if clean_name in normalized:

            return normalized[clean_name]

    return None


def normalize_row(record):

    security_col = find_column(
        record,
        [
            "Security Description",
            "SecurityDescription",
            "Security"
        ]
    )

    maturity_col = find_column(
        record,
        [
            "Maturity Date",
            "MaturityDate",
            "Maturity"
        ]
    )

    ltp_col = find_column(
        record,
        ["LTP"]
    )

    lty_col = find_column(
        record,
        ["LTY"]
    )

    security = (
        record.get(security_col)
        if security_col
        else None
    )

    maturity = parse_date(
        record.get(maturity_col)
        if maturity_col
        else None
    )

    ltp = clean_number(
        record.get(ltp_col)
        if ltp_col
        else None
    )

    lty = clean_number(
        record.get(lty_col)
        if lty_col
        else None
    )

    return {
        "security_description": security,
        "maturity_date": maturity,
        "ltp": ltp,
        "lty": lty
    }


def residual_days(
    maturity,
    today
):

    if maturity is None:
        return None

    return (
        maturity - today
    ).days


# ============================================================
# TABLE READER
# ============================================================

async def read_table(
    page,
    table_index
):

    tables = page.locator("table")

    count = await tables.count()

    if table_index >= count:
        return []

    table = tables.nth(
        table_index
    )

    rows = table.locator("tr")

    row_count = await rows.count()

    if row_count == 0:
        return []

    raw_rows = []

    for i in range(row_count):

        cells = rows.nth(i).locator(
            "th, td"
        )

        cell_count = await cells.count()

        values = []

        for j in range(cell_count):

            value = await cells.nth(j).inner_text()

            values.append(
                value.strip()
            )

        if values:
            raw_rows.append(values)

    if len(raw_rows) < 2:
        return []

    headers = raw_rows[0]

    records = []

    for values in raw_rows[1:]:

        if len(values) != len(headers):
            continue

        record = {}

        for i, header in enumerate(headers):

            record[
                header
            ] = values[i]

        records.append(record)

    return records


# ============================================================
# T-BILL SELECTION
# ============================================================

def select_tbills(
    rows,
    today
):

    targets = {
        "91D": 91,
        "182D": 182,
        "364D": 364
    }

    selected = {}

    used = set()

    for tenor, target in targets.items():

        candidates = []

        for row in rows:

            security = row[
                "security_description"
            ]

            maturity = row[
                "maturity_date"
            ]

            lty = row["lty"]

            if not security:
                continue

            if security in used:
                continue

            if maturity is None:
                continue

            # Reject zero / blank LTY
            if lty is None or lty <= 0:
                continue

            days = residual_days(
                maturity,
                today
            )

            if days is None or days <= 0:
                continue

            distance = abs(
                days - target
            )

            candidates.append(
                (
                    distance,
                    row
                )
            )

        if not candidates:

            selected[tenor] = None
            continue

        candidates.sort(
            key=lambda x: x[0]
        )

        chosen = candidates[0][1]

        selected[tenor] = chosen

        used.add(
            chosen[
                "security_description"
            ]
        )

    return selected


# ============================================================
# G-SEC SELECTION
# ============================================================

def select_gsecs(
    rows,
    today
):

    targets = {
        "2Y": 365 * 2,
        "5Y": 365 * 5,
        "10Y": 365 * 10
    }

    candidates = []

    for row in rows:

        security = row[
            "security_description"
        ]

        maturity = row[
            "maturity_date"
        ]

        lty = row["lty"]

        if not security:
            continue

        if maturity is None:
            continue

        # Reject zero / blank LTY
        if lty is None or lty <= 0:
            continue

        days = residual_days(
            maturity,
            today
        )

        if days is None or days <= 0:
            continue

        candidates.append({
            "security": security,
            "days": days,
            "row": row
        })

    if len(candidates) < 3:

        return {
            "2Y": None,
            "5Y": None,
            "10Y": None
        }

    best_score = None
    best_assignment = None

    indices = range(
        len(candidates)
    )

    # Find three DIFFERENT securities
    # that collectively best match
    # 2Y / 5Y / 10Y.

    for combination_set in combinations(
        indices,
        3
    ):

        for permutation_set in permutations(
            combination_set
        ):

            score = 0

            for (
                tenor,
                index
            ) in zip(
                targets.keys(),
                permutation_set
            ):

                target_days = targets[
                    tenor
                ]

                actual_days = candidates[
                    index
                ]["days"]

                score += abs(
                    actual_days -
                    target_days
                )

            if (
                best_score is None
                or score < best_score
            ):

                best_score = score

                best_assignment = (
                    permutation_set
                )

    result = {}

    for (
        tenor,
        index
    ) in zip(
        targets.keys(),
        best_assignment
    ):

        result[tenor] = candidates[
            index
        ]["row"]

    return result


# ============================================================
# MAIN FETCHER
# ============================================================

async def _fetch_ndsom_data():

    print("")
    print(
        "========================================"
    )
    print(
        "NDS-OM MARKET WATCH"
    )
    print(
        "========================================"
    )

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={
                "width": 1600,
                "height": 1200
            }
        )

        try:

            # ------------------------------------------------
            # OPEN CCIL
            # ------------------------------------------------

            await page.goto(
                CCIL_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            await page.wait_for_timeout(
                5000
            )

            today = datetime.now().date()

            # ------------------------------------------------
            # G-SEC DATA
            # ------------------------------------------------

            print("")
            print(
                "================ G-SEC DATA ================"
            )

            gsec_raw = await read_table(
                page,
                0
            )

            print(
                "TOTAL RAW G-SECS:",
                len(gsec_raw)
            )

            gsec_rows = []

            for record in gsec_raw:

                row = normalize_row(
                    record
                )

                if (
                    row[
                        "security_description"
                    ]
                    and row[
                        "maturity_date"
                    ]
                ):

                    gsec_rows.append(
                        row
                    )

                    print(
                        row[
                            "security_description"
                        ],
                        "|",
                        row[
                            "maturity_date"
                        ],
                        "| LTY:",
                        row["lty"],
                        "| LTP:",
                        row["ltp"]
                    )

            print(
                "VALID G-SECS:",
                len(gsec_rows)
            )

            # ------------------------------------------------
            # T-BILL TAB
            # ------------------------------------------------

            print("")
            print(
                "================ T-BILL DATA ================"
            )

            clicked = False

            selectors = [
                "text=T-Bills Mkt. Watch",
                "text=T-Bills",
                "text=T Bills"
            ]

            for selector in selectors:

                try:

                    locator = page.locator(
                        selector
                    ).first

                    if await locator.count() > 0:

                        print(
                            "Found T-Bill selector:",
                            selector
                        )

                        await locator.click(
                            timeout=10000
                        )

                        clicked = True

                        print(
                            "T-Bill tab clicked:",
                            True
                        )

                        break

                except Exception:
                    pass

            await page.wait_for_timeout(
                2500
            )

            # ------------------------------------------------
            # FIND T-BILL TABLE
            # ------------------------------------------------

            tbill_raw = []

            table_count = await page.locator(
                "table"
            ).count()

            for i in range(
                table_count
            ):

                rows = await read_table(
                    page,
                    i
                )

                if not rows:
                    continue

                first_record = rows[0]

                columns = " ".join(
                    str(x).lower()
                    for x in first_record.keys()
                )

                if (
                    "security" in columns
                    and "lty" in columns
                ):

                    tbill_raw = rows

                    print(
                        "T-Bill table found:",
                        i
                    )

                    break

            print(
                "TOTAL RAW T-BILLS:",
                len(tbill_raw)
            )

            tbill_rows = []

            for record in tbill_raw:

                row = normalize_row(
                    record
                )

                if (
                    row[
                        "security_description"
                    ]
                    and row[
                        "maturity_date"
                    ]
                ):

                    tbill_rows.append(
                        row
                    )

            print(
                "VALID T-BILLS:",
                len(tbill_rows)
            )

            # ------------------------------------------------
            # SELECT T-BILLS
            # ------------------------------------------------

            selected_tbills = select_tbills(
                tbill_rows,
                today
            )

            print("")
            print(
                "================ SELECTED T-BILLS ================"
            )

            for tenor in (
                "91D",
                "182D",
                "364D"
            ):

                row = selected_tbills.get(
                    tenor
                )

                print("")

                if row is None:

                    print(
                        "NDS-OM T-BILL",
                        tenor,
                        ": NO VALID SECURITY"
                    )

                    continue

                days = residual_days(
                    row[
                        "maturity_date"
                    ],
                    today
                )

                print(
                    "NDS-OM T-BILL",
                    tenor,
                    ":",
                    row[
                        "security_description"
                    ],
                    "|",
                    row[
                        "maturity_date"
                    ].strftime(
                        "%d/%m/%Y"
                    ),
                    "| Residual:",
                    days,
                    "days",
                    "| LTY",
                    row["lty"],
                    "| LTP",
                    row["ltp"]
                )

            # ------------------------------------------------
            # SELECT G-SECS
            # ------------------------------------------------

            selected_gsecs = select_gsecs(
                gsec_rows,
                today
            )

            print("")
            print(
                "================ SELECTED G-SECS ================"
            )

            for tenor in (
                "2Y",
                "5Y",
                "10Y"
            ):

                row = selected_gsecs.get(
                    tenor
                )

                print("")

                if row is None:

                    print(
                        "NDS-OM GSEC",
                        tenor,
                        ": NO VALID SECURITY"
                    )

                    continue

                days = residual_days(
                    row[
                        "maturity_date"
                    ],
                    today
                )

                print(
                    "NDS-OM GSEC",
                    tenor,
                    ":",
                    row[
                        "security_description"
                    ],
                    "|",
                    row[
                        "maturity_date"
                    ].strftime(
                        "%d/%m/%Y"
                    ),
                    "| Residual:",
                    days,
                    "days",
                    "| LTY",
                    row["lty"],
                    "| LTP",
                    row["ltp"]
                )

            print("")

            # ------------------------------------------------
            # RETURN DATA TO COLLECTOR
            # ------------------------------------------------

            return {

                "gsecs": [

                    {
                        "tenor":
                            tenor,

                        "security_description":
                            row[
                                "security_description"
                            ],

                        "maturity_date":
                            row[
                                "maturity_date"
                            ],

                        "ltp":
                            row["ltp"],

                        "lty":
                            row["lty"]
                    }

                    for tenor, row
                    in selected_gsecs.items()
                    if row is not None
                ],

                "tbills": [

                    {
                        "tenor":
                            tenor,

                        "security_description":
                            row[
                                "security_description"
                            ],

                        "maturity_date":
                            row[
                                "maturity_date"
                            ],

                        "ltp":
                            row["ltp"],

                        "lty":
                            row["lty"]
                    }

                    for tenor, row
                    in selected_tbills.items()
                    if row is not None
                ]
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
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    data = fetch_ndsom_data()

    print("")
    print(
        "NDS-OM FETCH COMPLETE"
    )

    print(
        "G-SECS RETURNED:",
        len(data["gsecs"])
    )

    print(
        "T-BILLS RETURNED:",
        len(data["tbills"])
    )
