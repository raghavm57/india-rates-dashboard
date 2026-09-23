import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright


URL = "https://www.ccilindia.com/market-watch"

IST = ZoneInfo("Asia/Kolkata")


# ============================================================
# HELPERS
# ============================================================

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
            .strip()
        )

        if tenor_days == 91:

            if not description.startswith(
                "091 DTB"
            ):
                continue

        elif tenor_days == 182:

            if not description.startswith(
                "182 DTB"
            ):
                continue

        elif tenor_days == 364:

            if not description.startswith(
                "364 DTB"
            ):
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
        key=lambda x: (
            x[0],
            x[1]
        )
    )

    return candidates[0][2]


# ============================================================
# MAIN NDS-OM FETCHER
# ============================================================

async def _fetch_ndsom_data():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        # ----------------------------------------------------
        # OPEN CCIL MARKET WATCH
        # ----------------------------------------------------

        print(
            "Opening CCIL NDS-OM Market Watch..."
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
            f"Page loaded: {page.url}"
        )

        # ----------------------------------------------------
        # G-SEC DATA
        # ----------------------------------------------------

        print(
            "\n================ G-SEC DATA ================\n"
        )

        tables = await page.locator(
            "table"
        ).all()

        print(
            f"Initial table count: "
            f"{len(tables)}"
        )

        gsec_data = []

        if len(tables) > 0:

            rows = await tables[0].locator(
                "tbody tr"
            ).all()

            print(
                f"G-Sec rows: {len(rows)}"
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

                    "security_description":
                        security,

                    "maturity_date":
                        cells[1],

                    "ltp":
                        cells[8],

                    "lty":
                        cells[9],

                    "lta":
                        (
                            cells[10]
                            if len(cells) > 10
                            else ""
                        ),

                    "tta":
                        (
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

        # ----------------------------------------------------
        # T-BILL TAB
        # ----------------------------------------------------

        print(
            "\n================ T-BILL DATA ================\n"
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
                    f"Found T-Bill selector: "
                    f"{selector}"
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
                    f"Clicked: {selector}"
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
            f"T-Bill tab clicked: "
            f"{clicked}"
        )

        if not clicked:

            await browser.close()

            raise RuntimeError(
                "Could not click T-Bill Market Watch tab"
            )

        # ----------------------------------------------------
        # WAIT FOR T-BILL DATA
        # ----------------------------------------------------

        await page.wait_for_timeout(
            12000
        )

        # ----------------------------------------------------
        # EXTRACT RAW T-BILLS
        # ----------------------------------------------------

        tables = await page.locator(
            "table"
        ).all()

        tbill_data = []

        for table in tables:

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
                    security_upper.startswith(
                        "091 DTB"
                    )
                    or
                    security_upper.startswith(
                        "182 DTB"
                    )
                    or
                    security_upper.startswith(
                        "364 DTB"
                    )
                ):

                    continue

                record = {

                    "security_description":
                        security,

                    "maturity_date":
                        cells[1],

                    "ltp":
                        cells[8],

                    "lty":
                        cells[9],

                    "lta":
                        (
                            cells[10]
                            if len(cells) > 10
                            else ""
                        ),

                    "tta":
                        (
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

        # ----------------------------------------------------
        # SELECT 91D / 182D / 364D
        # ----------------------------------------------------

        selected_tbills = {}

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

            today = datetime.now(
                IST
            ).date()

            residual_days = (
                maturity - today
            ).days

            result["tenor"] = tenor

            result["residual_days"] = (
                residual_days
            )

            selected_tbills[tenor] = result

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

        # ----------------------------------------------------
        # CLOSE
        # ----------------------------------------------------

        await browser.close()

        # ----------------------------------------------------
        # RETURN STRUCTURED DATA
        # ----------------------------------------------------

        return {

            "gsecs":
                gsec_data,

            "tbills":
                list(
                    selected_tbills.values()
                )
        }


# ============================================================
# PUBLIC FUNCTION
# ============================================================

def fetch_ndsom_data():

    return asyncio.run(
        _fetch_ndsom_data()
    )


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    result = fetch_ndsom_data()

    print(
        "\n================ FINAL RESULT ================\n"
    )

    print(
        f"G-SECS RETURNED: "
        f"{len(result['gsecs'])}"
    )

    print(
        f"T-BILLS RETURNED: "
        f"{len(result['tbills'])}"
    )

    for tbill in result["tbills"]:

        print(
            f"{tbill['tenor']} | "
            f"{tbill['security_description']} | "
            f"{tbill['maturity_date']} | "
            f"LTY: {tbill['lty']}"
                )
