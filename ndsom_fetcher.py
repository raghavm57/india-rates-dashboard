import asyncio
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright


URL = "https://www.ccilindia.com/market-watch"

IST = ZoneInfo("Asia/Kolkata")


def parse_date(value):

    try:
        return datetime.strptime(
            value.strip(),
            "%d/%m/%Y"
        ).date()

    except Exception:
        return None


def select_representative_tbill(
    tbills,
    tenor_days
):

    today = datetime.now(IST).date()

    target_date = today + timedelta(
        days=tenor_days
    )

    candidates = []

    for item in tbills:

        maturity = parse_date(
            item["maturity_date"]
        )

        if maturity is None:
            continue

        if maturity <= today:
            continue

        description = (
            item["security_description"]
            .upper()
        )

        if tenor_days == 91:
            if not description.startswith("091 DTB"):
                continue

        elif tenor_days == 182:
            if not description.startswith("182 DTB"):
                continue

        elif tenor_days == 364:
            if not description.startswith("364 DTB"):
                continue

        difference = abs(
            (maturity - target_date).days
        )

        candidates.append(
            (
                difference,
                maturity,
                item
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x[0]
    )

    return candidates[0][2]


async def main():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        # =========================================================
        # OPEN CCIL
        # =========================================================

        print(
            "\nOpening CCIL Market Watch...\n"
        )

        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        await page.wait_for_timeout(
            8000
        )

        print(
            f"PAGE: {page.url}"
        )

        # =========================================================
        # G-SEC EXTRACTION
        # =========================================================

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

                if not security:
                    continue

                record = {
                    "security_description": security,
                    "maturity_date": cells[1],
                    "ltp": cells[8],
                    "lty": cells[9],
                    "lta": (
                        cells[10]
                        if len(cells) > 10
                        else ""
                    ),
                    "tta": (
                        cells[11]
                        if len(cells) > 11
                        else ""
                    )
                }

                gsec_data.append(
                    record
                )

                print(
                    f"{security} | "
                    f"{cells[1]} | "
                    f"LTY: {cells[9]} | "
                    f"LTP: {cells[8]}"
                )

        print(
            f"\nTOTAL G-SECS: "
            f"{len(gsec_data)}"
        )

        # =========================================================
        # FIND T-BILL TAB
        # =========================================================

        print(
            "\n================ T-BILL TAB ================\n"
        )

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

                if await locator.count() == 0:
                    continue

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
                    f"Selector failed: "
                    f"{selector}"
                )

                print(
                    str(e)[:300]
                )

        print(
            f"\nT-BILL CLICKED: {clicked}"
        )

        # =========================================================
        # WAIT FOR T-BILL DATA
        # =========================================================

        print(
            "\nWaiting for T-Bill data...\n"
        )

        await page.wait_for_timeout(
            12000
        )

        # =========================================================
        # EXTRACT ALL T-BILLS
        # =========================================================

        print(
            "\n================ RAW T-BILLS ================\n"
        )

        tables = await page.locator(
            "table"
        ).all()

        tbill_data = []

        for i, table in enumerate(tables):

            rows = await table.locator(
                "tbody tr"
            ).all()

            if len(rows) <= 2:
                continue

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

                security_upper = (
                    security.upper()
                )

                if not (
                    security_upper.startswith("091 DTB")
                    or
                    security_upper.startswith("182 DTB")
                    or
                    security_upper.startswith("364 DTB")
                ):
                    continue

                record = {
                    "security_description": security,
                    "maturity_date": cells[1],
                    "ltp": cells[8],
                    "lty": cells[9],
                    "lta": (
                        cells[10]
                        if len(cells) > 10
                        else ""
                    ),
                    "tta": (
                        cells[11]
                        if len(cells) > 11
                        else ""
                    )
                }

                tbill_data.append(
                    record
                )

        print(
            f"TOTAL RAW T-BILLS: "
            f"{len(tbill_data)}"
        )

        # =========================================================
        # SELECT REPRESENTATIVE SECURITIES
        # =========================================================

        print(
            "\n================ SELECTED T-BILLS ================\n"
        )

        today = datetime.now(
            IST
        ).date()

        print(
            f"VALUATION DATE: "
            f"{today.strftime('%d/%m/%Y')}"
        )

        selected = {}

        for tenor, days in [
            ("91D", 91),
            ("182D", 182),
            ("364D", 364)
        ]:

            result = select_representative_tbill(
                tbill_data,
                days
            )

            if result is None:

                print(
                    f"{tenor}: NOT FOUND"
                )

                continue

            maturity = parse_date(
                result["maturity_date"]
            )

            residual_days = (
                maturity - today
            ).days

            selected[tenor] = result

            print(
                f"\n{tenor}"
            )

            print(
                f"Security : "
                f"{result['security_description']}"
            )

            print(
                f"Maturity : "
                f"{result['maturity_date']}"
            )

            print(
                f"Residual : "
                f"{residual_days} days"
            )

            print(
                f"LTP      : "
                f"{result['ltp']}"
            )

            print(
                f"LTY      : "
                f"{result['lty']}"
            )

            print(
                f"LTA      : "
                f"{result['lta']}"
            )

            print(
                f"TTA      : "
                f"{result['tta']}"
            )

        # =========================================================
        # FINAL SUMMARY
        # =========================================================

        print(
            "\n================ FINAL SUMMARY ================\n"
        )

        print(
            f"TOTAL G-SECS: "
            f"{len(gsec_data)}"
        )

        print(
            f"TOTAL RAW T-BILLS: "
            f"{len(tbill_data)}"
        )

        print(
            f"SELECTED T-BILLS: "
            f"{len(selected)}"
        )

        print(
            "\nThe three selected securities "
            "are ready for Neon integration."
        )

        await browser.close()


if __name__ == "__main__":

    asyncio.run(
        main()
                )
