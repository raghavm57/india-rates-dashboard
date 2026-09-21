print("STARTING NDS-OM BROWSER TEST")

from playwright.sync_api import sync_playwright
import pandas as pd

URL = "https://www.ccilindia.com/market-watch"

with sync_playwright() as p:

    print("Launching Chromium...")

    browser = p.chromium.launch(headless=True)

    page = browser.new_page(
        user_agent="Mozilla/5.0"
    )

    print("Opening CCIL Market Watch...")

    page.goto(
        URL,
        wait_until="networkidle",
        timeout=60000
    )

    print("Page loaded")

    # Give CCIL's JavaScript additional time
    page.wait_for_timeout(5000)

    html = page.content()

    print("Rendered HTML length:", len(html))

    tables = pd.read_html(html)

    print("TABLES FOUND:", len(tables))

    for i, table in enumerate(tables):

        print("\n====================")
        print("TABLE:", i)
        print("====================")

        print(
            table.head(10).to_string()
        )

    browser.close()

print("\nNDS-OM BROWSER TEST FINISHED")
