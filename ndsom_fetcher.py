import asyncio
import json
import re

from playwright.async_api import async_playwright


URL = "https://www.ccilindia.com/market-watch"


async def main():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        # ---------------------------------------------------------
        # NETWORK DEBUGGING
        # ---------------------------------------------------------

        print("\n================ NETWORK LOG ================\n")

        async def log_request(request):

            if request.resource_type in [
                "xhr",
                "fetch"
            ]:

                print(
                    f"REQUEST | {request.method} | "
                    f"{request.resource_type} | "
                    f"{request.url}"
                )

        async def log_response(response):

            request = response.request

            if request.resource_type in [
                "xhr",
                "fetch"
            ]:

                print(
                    f"RESPONSE | {response.status} | "
                    f"{request.resource_type} | "
                    f"{response.url}"
                )

                # Print response preview for likely data calls
                url_lower = response.url.lower()

                interesting = any(
                    word in url_lower
                    for word in [
                        "market",
                        "watch",
                        "bill",
                        "tbill",
                        "security",
                        "ndsom",
                        "search",
                        "trade"
                    ]
                )

                if interesting:

                    try:

                        text = await response.text()

                        preview = text[:1000]

                        print(
                            "RESPONSE BODY PREVIEW:"
                        )

                        print(preview)

                        print(
                            "\n----------------------------------------\n"
                        )

                    except Exception as e:

                        print(
                            f"Could not read response body: {e}"
                        )

        page.on(
            "request",
            log_request
        )

        page.on(
            "response",
            log_response
        )

        # ---------------------------------------------------------
        # OPEN CCIL
        # ---------------------------------------------------------

        print("\nOpening CCIL Market Watch...\n")

        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        await page.wait_for_timeout(8000)

        print(
            "PAGE LOADED:"
        )

        print(
            page.url
        )

        # ---------------------------------------------------------
        # G-SEC EXTRACTION
        # ---------------------------------------------------------

        print(
            "\n================ G-SEC DATA ================\n"
        )

        tables = await page.locator(
            "table"
        ).all()

        print(
            f"TABLE COUNT: {len(tables)}"
        )

        gsec_data = []

        if len(tables) > 0:

            rows = await tables[0].locator(
                "tbody tr"
            ).all()

            print(
                f"G-SEC ROWS: {len(rows)}"
            )

            for row in rows:

                cells = await row.locator(
                    "td"
                ).all_text_contents()

                cells = [
                    c.strip()
                    for c in cells
                ]

                if len(cells) < 10:
                    continue

                security = cells[0]
                maturity = cells[1]

                ltp = cells[8]
                lty = cells[9]
                lta = cells[10] if len(cells) > 10 else ""
                tta = cells[11] if len(cells) > 11 else ""

                if not security:
                    continue

                record = {
                    "security_description": security,
                    "maturity_date": maturity,
                    "ltp": ltp,
                    "lty": lty,
                    "lta": lta,
                    "tta": tta
                }

                gsec_data.append(
                    record
                )

                print(
                    f"{security} | "
                    f"{maturity} | "
                    f"LTY: {lty} | "
                    f"LTP: {ltp}"
                )

        print(
            f"\nTOTAL G-SECS: {len(gsec_data)}"
        )

        # ---------------------------------------------------------
        # FIND T-BILL TAB
        # ---------------------------------------------------------

        print(
            "\n================ T-BILL TAB ================\n"
        )

        # Try several ways of identifying the T-Bill tab.

        selectors = [
            "text=T-Bills Mkt. Watch",
            "text=T-Bills Mkt Watch",
            "text=T-Bills",
            "a:has-text('T-Bills')",
            "button:has-text('T-Bills')"
        ]

        clicked = False

        for selector in selectors:

            try:

                locator = page.locator(
                    selector
                ).first

                count = await locator.count()

                if count > 0:

                    print(
                        f"Found selector: {selector}"
                    )

                    try:

                        await locator.scroll_into_view_if_needed()

                    except Exception:
                        pass

                    await locator.click(
                        force=True,
                        timeout=10000
                    )

                    clicked = True

                    print(
                        f"CLICKED: {selector}"
                    )

                    break

            except Exception as e:

                print(
                    f"Selector failed: {selector}"
                )

                print(
                    str(e)[:300]
                )

        print(
            f"\nT-BILL CLICKED: {clicked}"
        )

        # ---------------------------------------------------------
        # WAIT FOR AJAX / FETCH
        # ---------------------------------------------------------

        print(
            "\nWaiting for T-Bill network activity...\n"
        )

        await page.wait_for_timeout(
            15000
        )

        # ---------------------------------------------------------
        # INSPECT TABLES AFTER T-BILL CLICK
        # ---------------------------------------------------------

        print(
            "\n================ TABLE INSPECTION ================\n"
        )

        tables = await page.locator(
            "table"
        ).all()

        print(
            f"TABLE COUNT AFTER T-BILL ACTION: "
            f"{len(tables)}"
        )

        for i, table in enumerate(tables):

            rows = await table.locator(
                "tbody tr"
            ).all()

            print(
                f"\nTABLE {i} | ROWS: {len(rows)}"
            )

            # Print first few rows only
            for row in rows[:5]:

                cells = await row.locator(
                    "td"
                ).all_text_contents()

                cells = [
                    c.strip()
                    for c in cells
                ]

                print(
                    cells
                )

        # ---------------------------------------------------------
        # ATTEMPT TO IDENTIFY T-BILL TABLE BY HEADER
        # ---------------------------------------------------------

        print(
            "\n================ T-BILL DATA SEARCH ================\n"
        )

        tbill_data = []

        for i, table in enumerate(tables):

            text = (
                await table.inner_text()
            ).lower()

            if (
                "security description" in text
                and "maturity date" in text
                and "lty" in text
                and "ltp" in text
            ):

                print(
                    f"Potential market table: TABLE {i}"
                )

                rows = await table.locator(
                    "tbody tr"
                ).all()

                for row in rows:

                    cells = await row.locator(
                        "td"
                    ).all_text_contents()

                    cells = [
                        c.strip()
                        for c in cells
                    ]

                    if len(cells) < 10:
                        continue

                    security = cells[0]

                    if not security:
                        continue

                    maturity = cells[1]

                    # T-Bill table column order:
                    #
                    # 0 Security Description
                    # 1 Maturity Date
                    # 2 Bid Amt
                    # 3 Bid Price
                    # 4 Bid Yield
                    # 5 Offer Yield
                    # 6 Offer Price
                    # 7 Offer Amt
                    # 8 LTP
                    # 9 LTY
                    # 10 LTA
                    # 11 TTA

                    record = {
                        "security_description": security,
                        "maturity_date": maturity,
                        "ltp": cells[8],
                        "lty": cells[9],
                        "lta": cells[10],
                        "tta": cells[11]
                        if len(cells) > 11
                        else ""
                    }

                    tbill_data.append(
                        record
                    )

                    print(
                        record
                    )

        print(
            f"\nTOTAL T-BILLS: "
            f"{len(tbill_data)}"
        )

        # ---------------------------------------------------------
        # FINAL SUMMARY
        # ---------------------------------------------------------

        print(
            "\n================ SUMMARY ================\n"
        )

        print(
            f"TOTAL G-SECS: {len(gsec_data)}"
        )

        print(
            f"TOTAL T-BILLS: {len(tbill_data)}"
        )

        print(
            "\nIf T-Bills are still zero, the network "
            "log above should reveal the CCIL endpoint "
            "responsible for loading them."
        )

        await browser.close()


if __name__ == "__main__":

    asyncio.run(
        main()
        )
