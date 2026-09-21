print("STARTING NDS-OM NETWORK TEST")

from playwright.sync_api import sync_playwright

URL = "https://www.ccilindia.com/market-watch"

with sync_playwright() as p:

    browser = p.chromium.launch(headless=True)

    page = browser.new_page(
        user_agent="Mozilla/5.0"
    )

    # Capture network requests
    def request_handler(request):
        resource = request.resource_type

        if resource in ["xhr", "fetch"]:
            print("\nXHR/FETCH:")
            print(request.method, request.url)

    page.on("request", request_handler)

    print("Opening CCIL...")

    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    print("Initial page loaded")

    # Allow JavaScript/AJAX to populate market data
    page.wait_for_timeout(15000)

    print("\n==============================")
    print("CHECKING TABLES")
    print("==============================")

    tables = page.locator("table")

    print("TABLE COUNT:", tables.count())

    for i in range(tables.count()):

        table = tables.nth(i)

        print("\n------------------------------")
        print("TABLE:", i)
        print("------------------------------")

        rows = table.locator("tr")

        print("ROWS:", rows.count())

        for j in range(min(rows.count(), 10)):

            text = rows.nth(j).inner_text().strip()

            if text:
                print("ROW:", text.replace("\n", " | "))

    browser.close()

print("\nNDS-OM NETWORK TEST FINISHED")
