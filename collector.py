import os
from datetime import datetime, date
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from sqlalchemy import create_engine, text

from ndsom_fetcher import fetch_ndsom_data


# ============================================================
# DATABASE
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not found")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


# ============================================================
# DATABASE TABLE
# ============================================================

def ensure_table():

    with engine.begin() as conn:

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS observations (

                    id BIGSERIAL PRIMARY KEY,

                    observation_date DATE NOT NULL,

                    source TEXT NOT NULL,

                    series TEXT NOT NULL,

                    tenor TEXT NOT NULL,

                    value DOUBLE PRECISION,

                    unit TEXT,

                    publication_time TIMESTAMP,

                    source_url TEXT,

                    status TEXT,

                    security_description TEXT,

                    maturity_date DATE,

                    ltp DOUBLE PRECISION

                );
                """
            )
        )

        # Add newer columns if the table already existed
        for statement in [
            """
            ALTER TABLE observations
            ADD COLUMN IF NOT EXISTS security_description TEXT;
            """,
            """
            ALTER TABLE observations
            ADD COLUMN IF NOT EXISTS maturity_date DATE;
            """,
            """
            ALTER TABLE observations
            ADD COLUMN IF NOT EXISTS ltp DOUBLE PRECISION;
            """,
            """
            ALTER TABLE observations
            ADD COLUMN IF NOT EXISTS publication_time TIMESTAMP;
            """,
        ]:

            conn.execute(text(statement))


# ============================================================
# SAVE OBSERVATION
# ============================================================

def save_observation(
    observation_date,
    source,
    series,
    tenor,
    value,
    unit=None,
    publication_time=None,
    source_url=None,
    status="success",
    security_description=None,
    maturity_date=None,
    ltp=None,
):

    with engine.begin() as conn:

        conn.execute(
            text(
                """
                INSERT INTO observations
                (
                    observation_date,
                    source,
                    series,
                    tenor,
                    value,
                    unit,
                    publication_time,
                    source_url,
                    status,
                    security_description,
                    maturity_date,
                    ltp
                )
                VALUES
                (
                    :observation_date,
                    :source,
                    :series,
                    :tenor,
                    :value,
                    :unit,
                    :publication_time,
                    :source_url,
                    :status,
                    :security_description,
                    :maturity_date,
                    :ltp
                )
                """
            ),
            {
                "observation_date": observation_date,
                "source": source,
                "series": series,
                "tenor": tenor,
                "value": value,
                "unit": unit,
                "publication_time": publication_time,
                "source_url": source_url,
                "status": status,
                "security_description": security_description,
                "maturity_date": maturity_date,
                "ltp": ltp,
            },
        )


# ============================================================
# MONEY MARKET
# ============================================================

def save_money_market(reference_date):

    print("\nFetching CCIL money-market data...")

    url = "https://www.ccilindia.com/web/ccil/money-market"

    try:

        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )

        response.raise_for_status()

        tables = pd.read_html(response.text)

        if not tables:

            print("No money-market tables found.")
            return

        saved = 0

        for table in tables:

            table.columns = [
                str(c).strip()
                for c in table.columns
            ]

            for _, row in table.iterrows():

                row_text = " ".join(
                    str(x)
                    for x in row.tolist()
                ).lower()

                mappings = {
                    "call": "Call",
                    "treps": "TREPS",
                    "basket repo": "Basket Repo",
                    "special repo": "Special Repo",
                }

                for search_name, tenor in mappings.items():

                    if search_name not in row_text:
                        continue

                    numeric_values = []

                    for value in row.tolist():

                        try:

                            number = float(
                                str(value)
                                .replace(",", "")
                                .replace("%", "")
                                .strip()
                            )

                            numeric_values.append(number)

                        except Exception:
                            continue

                    if not numeric_values:
                        continue

                    value = numeric_values[-1]

                    save_observation(
                        observation_date=reference_date,
                        source="CCIL",
                        series="MONEY_MARKET",
                        tenor=tenor,
                        value=value,
                        unit="percent",
                        source_url=url,
                        status="success",
                    )

                    saved += 1

                    break

        print(
            f"Money-market observations saved: {saved}"
        )

    except Exception as e:

        print(
            f"Money-market fetch failed: {e}"
        )


# ============================================================
# TRADINGVIEW GLOBAL BONDS
# ============================================================

TRADINGVIEW_SYMBOLS = [
    "TVC:US10Y",
    "TVC:JP10Y",
    "TVC:CN10Y",
]


def save_tradingview(reference_date):

    print("\nFetching TradingView global bonds...")

    saved = 0

    for symbol in TRADINGVIEW_SYMBOLS:

        try:

            url = (
                "https://scanner.tradingview.com/global/scan"
            )

            payload = {
                "symbols": {
                    "tickers": [symbol],
                    "query": {
                        "types": []
                    },
                },
                "columns": [
                    "close"
                ],
            }

            response = requests.post(
                url,
                json=payload,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0"
                },
            )

            response.raise_for_status()

            data = response.json()

            rows = data.get("data", [])

            if not rows:
                continue

            value = rows[0]["d"][0]

            if value is None:
                continue

            if symbol == "TVC:US10Y":
                tenor = "US10Y"

            elif symbol == "TVC:JP10Y":
                tenor = "JP10Y"

            elif symbol == "TVC:CN10Y":
                tenor = "CN10Y"

            else:
                continue

            save_observation(
                observation_date=reference_date,
                source="TradingView",
                series="GLOBAL_BOND",
                tenor=tenor,
                value=float(value),
                unit="percent",
                source_url="https://www.tradingview.com/",
                status="success",
            )

            saved += 1

        except Exception as e:

            print(
                f"TradingView {symbol} failed: {e}"
            )

    print(
        f"TradingView global bond observations saved: {saved}"
    )


# ============================================================
# OIS
# ============================================================

def save_ois(reference_date):

    print("\nFetching CCIL OIS data...")

    url = (
        "https://www.ccilindia.com/"
        "web/ccil/interest-rate-derivatives"
    )

    try:

        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )

        if response.status_code != 200:

            print(
                f"OIS HTTP status: {response.status_code}"
            )

            return

        # CCIL may sometimes return HTML instead
        # of the expected data response.
        if "<html" in response.text.lower():

            print(
                "OIS response is HTML; skipping."
            )

            return

        tables = pd.read_html(
            response.text
        )

        saved = 0

        for table in tables:

            table.columns = [
                str(c).strip()
                for c in table.columns
            ]

            for _, row in table.iterrows():

                row_values = row.tolist()

                text_row = " ".join(
                    str(x)
                    for x in row_values
                )

                text_lower = text_row.lower()

                tenor = None

                for candidate in [
                    "1M",
                    "2M",
                    "3M",
                    "6M",
                    "1Y",
                    "2Y",
                    "3Y",
                    "5Y",
                    "10Y",
                ]:

                    if candidate.lower() in text_lower:

                        tenor = candidate
                        break

                if tenor is None:
                    continue

                numeric_values = []

                for value in row_values:

                    try:

                        number = float(
                            str(value)
                            .replace(",", "")
                            .replace("%", "")
                            .strip()
                        )

                        numeric_values.append(number)

                    except Exception:
                        continue

                if not numeric_values:
                    continue

                value = numeric_values[-1]

                if value <= 0:
                    continue

                save_observation(
                    observation_date=reference_date,
                    source="CCIL",
                    series="OIS",
                    tenor=tenor,
                    value=value,
                    unit="percent",
                    source_url=url,
                    status="success",
                )

                saved += 1

        print(
            f"OIS observations saved: {saved}"
        )

    except Exception as e:

        print(
            f"OIS fetch failed: {e}"
        )


# ============================================================
# LEGACY CCIL G-SEC
# ============================================================

def save_gsec(reference_date):

    print("\nFetching legacy CCIL G-Sec data...")

    url = (
        "https://www.ccilindia.com/"
        "web/ccil/tenorwise-indicative-yields"
    )

    try:

        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )

        response.raise_for_status()

        tables = pd.read_html(
            response.text
        )

        saved = 0

        for table in tables:

            for _, row in table.iterrows():

                row_text = " ".join(
                    str(x)
                    for x in row.tolist()
                )

                text_lower = row_text.lower()

                tenor = None

                if "1y-2y" in text_lower:
                    tenor = "2Y"

                elif "4y-5y" in text_lower:
                    tenor = "5Y"

                elif "9y-10y" in text_lower:
                    tenor = "10Y"

                if tenor is None:
                    continue

                numeric_values = []

                for value in row.tolist():

                    try:

                        number = float(
                            str(value)
                            .replace(",", "")
                            .replace("%", "")
                            .strip()
                        )

                        numeric_values.append(number)

                    except Exception:
                        continue

                if not numeric_values:
                    continue

                value = numeric_values[-1]

                save_observation(
                    observation_date=reference_date,
                    source="CCIL",
                    series="GSEC_LEGACY",
                    tenor=tenor,
                    value=value,
                    unit="percent",
                    source_url=url,
                    status="success",
                )

                saved += 1

        print(
            f"Legacy G-sec observations saved: {saved}"
        )

    except Exception as e:

        print(
            f"Legacy G-sec fetch failed: {e}"
        )


# ============================================================
# NDS-OM
# ============================================================

def save_ndsom(reference_date):

    print("\nStarting NDS-OM browser fetch...")

    try:

        data = fetch_ndsom_data()

    except Exception as e:

        print(
            f"NDS-OM fetch failed: {e}"
        )

        return

    gsecs = data.get(
        "gsecs",
        []
    )

    tbills = data.get(
        "tbills",
        []
    )

    print(
        f"NDS-OM G-Secs received: {len(gsecs)}"
    )

    print(
        f"NDS-OM T-Bills received: {len(tbills)}"
    )

    # ========================================================
    # G-SECS
    # ========================================================

    gsec_saved = 0

    for row in gsecs:

        tenor = row.get("tenor")

        security = row.get(
            "security_description"
        )

        maturity = row.get(
            "maturity_date"
        )

        lty = row.get(
            "lty"
        )

        ltp = row.get(
            "ltp"
        )

        if tenor not in [
            "2Y",
            "5Y",
            "10Y",
        ]:
            continue

        if not security:
            continue

        if lty is None:
            continue

        print(
            f"NDS-OM G-Sec {tenor}: "
            f"{security} | "
            f"{maturity} | "
            f"LTY {lty}"
        )

        save_observation(
            observation_date=reference_date,
            source="NDS-OM",
            series="GSEC",
            tenor=tenor,
            value=lty,
            unit="percent",
            publication_time=None,
            source_url=(
                "https://www.ccilindia.com/"
                "market-watch"
            ),
            status="success",
            security_description=security,
            maturity_date=maturity,
            ltp=ltp,
        )

        gsec_saved += 1

    # ========================================================
    # T-BILLS
    # ========================================================

    tbill_saved = 0

    for row in tbills:

        tenor = row.get("tenor")

        security = row.get(
            "security_description"
        )

        maturity = row.get(
            "maturity_date"
        )

        lty = row.get(
            "lty"
        )

        ltp = row.get(
            "ltp"
        )

        if tenor not in [
            "91D",
            "182D",
            "364D",
        ]:
            continue

        if not security:
            continue

        if lty is None:
            continue

        print(
            f"NDS-OM T-Bill {tenor}: "
            f"{security} | "
            f"{maturity} | "
            f"LTY {lty}"
        )

        save_observation(
            observation_date=reference_date,
            source="NDS-OM",
            series="TBILL",
            tenor=tenor,
            value=lty,
            unit="percent",
            publication_time=None,
            source_url=(
                "https://www.ccilindia.com/"
                "market-watch"
            ),
            status="success",
            security_description=security,
            maturity_date=maturity,
            ltp=ltp,
        )

        tbill_saved += 1

    print(
        f"NDS-OM G-Secs saved: {gsec_saved}"
    )

    print(
        f"NDS-OM T-Bills saved: {tbill_saved}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "Starting market-data collector..."
    )

    reference_date = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).date()

    print(
        f"India date: {reference_date}"
    )

    # Database
    ensure_table()

    # Money market
    save_money_market(
        reference_date
    )

    # TradingView global bonds
    save_tradingview(
        reference_date
    )

    # OIS
    if reference_date.weekday() < 5:

        print(
            "Trading weekday – collecting OIS."
        )

        save_ois(
            reference_date
        )

    else:

        print(
            "Weekend – skipping OIS."
        )

    # Legacy CCIL G-Sec data
    save_gsec(
        reference_date
    )

    # NDS-OM live market watch
    save_ndsom(
        reference_date
    )

    print("")
    print(
        "========================================"
    )
    print(
        "MARKET-DATA COLLECTION COMPLETED"
    )
    print(
        "========================================"
        )
