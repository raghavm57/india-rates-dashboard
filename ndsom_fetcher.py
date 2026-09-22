print("STARTING NDS-OM G-SEC + T-BILL FETCH")

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

    page.wait_for_timeout(10000)


    # =========================================================
    # G-SEC
    # =========================================================

    tables = page.locator("table")

    print("INITIAL TABLE COUNT:", tables.count())

    gsecs = []

    gsec_table = tables.nth(0)

    gsec_rows = gsec_table.locator("tr")

    print("G-SEC ROWS:", gsec_rows.count())

    for i in range(1, gsec_rows.count()):

        values = get_row_values(
            gsec_rows.nth(i)
        )

        if len(values) < 12:
            continue

        gsec = {
            "security_description": values[0],
            "maturity_date": values[1],
            "ltp": values[8],
            "lty": values[9],
            "lta": values[10],
            "tta": values[11]
        }

        gsecs.append(gsec)


    print("\n==============================")
    print("CLEAN G-SEC DATA")
    print("==============================")

    for gsec in gsecs:

        print(
            gsec["security_description"],
            "|",
            gsec["maturity_date"],
            "| LTP:",
            gsec["ltp"],
            "| LTY:",
            gsec["lty"]
        )

    print(
        "\nTOTAL G-SECS:",
        len(gsecs)
    )


    # =========================================================
    # ACTIVATE T-BILLS TAB
    # =========================================================

    print("\n==============================")
    print("OPENING T-BILLS MARKET WATCH")
    print("==============================")


    # Find the T-Bills tab/link
    tbill_links = page.get_by_text(
        "T-Bills Market Watch",
        exact=False
    )

    print(
        "T-BILL TAB COUNT:",
        tbill_links.count()
    )


    if tbill_links.count() > 0:

        print("Clicking T-Bills tab...")

        tbill_links.first.click()

        # Allow AJAX request to complete
        page.wait_for_timeout(10000)

    else:

        print("T-Bills tab not found")


    # =========================================================
    # READ T-BILL TABLES AFTER TAB ACTIVATION
    # =========================================================

    tables = page.locator("table")

    print(
        "\nTABLE COUNT AFTER T-BILL CLICK:",
        tables.count()
    )


    tbills = []


    for i in range(tables.count()):

        table = tables.nth(i)

        rows = table.locator("tr")

        print(
            "\nTABLE",
            i,
            "| ROWS:",
            rows.count()
        )


        for j in range(
            min(rows.count(), 5)
        ):

            text = (
                rows.nth(j)
                .inner_text()
                .strip()
                .replace("\n", " | ")
            )

            if text:

                print(
                    "ROW:",
                    text
                )


        # Look for DTB rows
        for j in range(1, rows.count()):

            values = get_row_values(
                rows.nth(j)
            )

            if len(values) < 12:
                continue

            description = values[0].upper()

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


    # =========================================================
    # T-BILL OUTPUT
    # =========================================================

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
    # FINAL JSON
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


print("\nNDS-OM FETCH FINISHED")
