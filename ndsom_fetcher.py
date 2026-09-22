print("STARTING NDS-OM CLEAN FETCH")

from playwright.sync_api import sync_playwright
import json

URL = "https://www.ccilindia.com/market-watch"


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

    page.wait_for_timeout(15000)

    tables = page.locator("table")

    print("TABLE COUNT:", tables.count())

    securities = []

    # Table 0 = Central Government Securities
    table = tables.nth(0)

    rows = table.locator("tr")

    print("G-SEC ROWS:", rows.count())

    for i in range(1, rows.count()):

        cells = rows.nth(i).locator("td")

        if cells.count() < 12:
            continue

        values = []

        for j in range(cells.count()):
            values.append(
                cells.nth(j).inner_text().strip()
            )

        # Expected structure:
        # 0 Security Description
        # 1 Maturity Date
        # ...
        # 9 LTP
        # 10 LTY
        # 11 LTA
        # 12 TTA

    security = {
        "security_description": values[0],
        "maturity_date": values[1],
        "ltp": values[8],
        "lty": values[9],
        "lta": values[10],
        "tta": values[11]
    }

    securities.append(security)

    print("\n==============================")
    print("CLEAN NDS-OM DATA")
    print("==============================")

    for security in securities:

        print(
            security["security_description"],
            "|",
            security["maturity_date"],
            "| LTY:",
            security["lty"]
        )

    print("\nTOTAL SECURITIES:", len(securities))

    print("\nJSON OUTPUT:")

    print(
        json.dumps(
            securities,
            indent=2
        )
    )

    browser.close()

print("\nNDS-OM CLEAN FETCH FINISHED")
