print("STARTING NDS-OM CLEAN FETCH")

from playwright.sync_api import sync_playwright
import json

URL = "https://www.ccilindia.com/market-watch"


def get_row_values(row):

    cells = row.locator("td")

    values = []

    for j in range(cells.count()):
        values.append(
            cells.nth(j).inner_text().strip()
        )

    return values


with sync_playwright() as p:

    browser = p.chromium.launch(headless=True)

    page = browser.new_page(
        user_agent="Mozilla/5.0"
    )

    print("Opening CCIL...")

    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    print("Page loaded")

    # Allow JavaScript/AJAX to populate NDS-OM data
    page.wait_for_timeout(15000)

    tables = page.locator("table")

    print("TABLE COUNT:", tables.count())


    # =========================================================
    # 1. G-SEC DATA
    # =========================================================

    print("\n==============================")
    print("G-SEC DATA")
    print("==============================")

    gsecs = []

    # Table 0 = Central Government Securities
    gsec_table = tables.nth(0)

    gsec_rows = gsec_table.locator("tr")

    print("G-SEC ROWS:", gsec_rows.count())

    for i in range(1, gsec_rows.count()):

        values = get_row_values(
            gsec_rows.nth(i)
        )

        # Expected:
        # 0 Security Description
        # 1 Maturity Date
        # 2 Bid Amt
        # 3 Bid Yield
        # 4 Bid Price
        # 5 Offer Price
        # 6 Offer Yield
        # 7 Offer Amt
        # 8 LTP
        # 9 LTY
        # 10 LTA
        # 11 TTA

        if len(values) < 12:
            continue

        security = {
            "security_description": values[0],
            "maturity_date": values[1],
            "ltp": values[8],
            "lty": values[9],
            "lta": values[10],
            "tta": values[11]
        }

        gsecs.append(security)


    print("\nCLEAN G-SEC DATA")
    print("==============================")

    for security in gsecs:

        print(
            security["security_description"],
            "|",
            security["maturity_date"],
            "| LTP:",
            security["ltp"],
            "| LTY:",
            security["lty"]
        )

    print(
        "\nTOTAL G-SECS:",
        len(gsecs)
    )


    # =========================================================
    # 2. FIND T-BILL TABLE
    # =========================================================

    print("\n==============================")
    print("SEARCHING FOR T-BILL TABLE")
    print("==============================")


    tbill_table_index = None

    for i in range(1, tables.count()):

        table = tables.nth(i)

        rows = table.locator("tr")

        table_text = table.inner_text().upper()

        print(
            "TABLE",
            i,
            "| ROWS:",
            rows.count()
        )

        # Look for DTB securities
        if "DTB" in table_text:

            tbill_table_index = i

            print(
                "T-BILL TABLE FOUND:",
                i
            )

            break


    # =========================================================
    # 3. EXTRACT T-BILLS
    # =========================================================

    tbills = []


    if tbill_table_index is not None:

        tbill_table = tables.nth(
            tbill_table_index
        )

        tbill_rows = tbill_table.locator("tr")

        for i in range(1, tbill_rows.count()):

            values = get_row_values(
                tbill_rows.nth(i)
            )

            if len(values) < 12:
                continue

            description = values[0].upper()

            # Only keep actual DTB securities
            if "DTB" not in description:
                continue

            tbill = {
                "security_description": values[0],
                "maturity_date": values[1],
                "ltp": values[8],
                "lty": values[9],
                "lta": values[10],
                "tta": values[11]
            }

            tbills.append(tbill)


    print("\n==============================")
    print("CLEAN T-BILL DATA")
    print("==============================")


    for tbill in tbills:

        print(
            tbill["security_description"],
            "|",
            tbill["maturity_date"],
            "| LTP:",
            tbill["ltp"],
            "| LTY:",
            tbill["lty"]
        )


    print(
        "\nTOTAL T-BILLS:",
        len(tbills)
    )


    # =========================================================
    # 4. FINAL JSON
    # =========================================================

    output = {
        "gsecs": gsecs,
        "tbills": tbills
    }


    print("\n==============================")
    print("FINAL JSON")
    print("==============================")

    print(
        json.dumps(
            output,
            indent=2
        )
    )


    browser.close()


print("\nNDS-OM CLEAN FETCH FINISHED")
