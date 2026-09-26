import os
from datetime import datetime
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
    pool_pre_ping=True
)


# ============================================================
# DATABASE TABLE
# ============================================================

def ensure_table():

    with engine.begin() as conn:

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS public.observations (
                    id BIGSERIAL PRIMARY KEY,
                    observation_date DATE,
                    source TEXT,
                    series TEXT,
                    tenor TEXT,
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

        columns = [
            ("observation_date", "DATE"),
            ("source", "TEXT"),
            ("series", "TEXT"),
            ("tenor", "TEXT"),
            ("value", "DOUBLE PRECISION"),
            ("unit", "TEXT"),
            ("publication_time", "TIMESTAMP"),
            ("source_url", "TEXT"),
            ("status", "TEXT"),
            ("security_description", "TEXT"),
            ("maturity_date", "DATE"),
            ("ltp", "DOUBLE PRECISION"),
            ("event_date", "DATE"),
            ("notes", "TEXT"),
            ]

        for column, datatype in columns:

            conn.execute(
                text(
                    f"""
                    ALTER TABLE public.observations
                    ADD COLUMN IF NOT EXISTS
                    {column} {datatype};
                    """
                )
            )

    print("Database table check completed.")

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
    event_date=None,
    notes=None,
    ):

    with engine.begin() as conn:

        conn.execute(
            text(
                """
                INSERT INTO public.observations
                (
                    date,
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

    print("\nFetching money-market data...")

    url = "https://www.ccilindia.com/web/ccil/money-market"

    try:

        response = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        response.raise_for_status()

        tables = pd.read_html(response.text)

        saved = 0

        for table in tables:

            for _, row in table.iterrows():

                row_text = " ".join(
                    str(x) for x in row.tolist()
                ).lower()

                mapping = {
                    "call": "Call",
                    "treps": "TREPS",
                    "basket repo": "Basket Repo",
                    "special repo": "Special Repo",
                }

                tenor = None

                for key, value in mapping.items():

                    if key in row_text:
                        tenor = value
                        break

                if tenor is None:
                    continue

                numbers = []

                for value in row.tolist():

                    try:

                        number = float(
                            str(value)
                            .replace(",", "")
                            .replace("%", "")
                            .strip()
                        )

                        numbers.append(number)

                    except Exception:
                        pass

                if not numbers:
                    continue

                save_observation(
                    observation_date=reference_date,
                    source="CCIL",
                    series="MONEY_MARKET",
                    tenor=tenor,
                    value=numbers[-1],
                    unit="percent",
                    source_url=url,
                    status="success",
                )

                saved += 1

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
                    "query": {"types": []}
                },
                "columns": ["close"],
            }

            response = requests.post(
                url,
                json=payload,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0"}
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

    print("\nFetching OIS data...")

    url = (
        "https://www.ccilindia.com/"
        "web/ccil/interest-rate-derivatives"
    )

    try:

        response = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        if response.status_code != 200:
            print(
                f"OIS HTTP status: {response.status_code}"
            )
            return

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

            for _, row in table.iterrows():

                values = row.tolist()

                row_text = " ".join(
                    str(x) for x in values
                ).lower()

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

                    if candidate.lower() in row_text:

                        tenor = candidate
                        break

                if tenor is None:
                    continue

                numbers = []

                for value in values:

                    try:

                        number = float(
                            str(value)
                            .replace(",", "")
                            .replace("%", "")
                            .strip()
                        )

                        numbers.append(number)

                    except Exception:
                        pass

                if not numbers:
                    continue

                value = numbers[-1]

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
# LEGACY G-SEC
# ============================================================

def save_gsec(reference_date):

    print("\nFetching legacy G-Sec data...")

    url = (
        "https://www.ccilindia.com/"
        "web/ccil/tenorwise-indicative-yields"
    )

    try:

        response = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        response.raise_for_status()

        tables = pd.read_html(
            response.text
        )

        saved = 0

        for table in tables:

            for _, row in table.iterrows():

                values = row.tolist()

                row_text = " ".join(
                    str(x) for x in values
                ).lower()

                tenor = None

                if "1y-2y" in row_text:
                    tenor = "2Y"

                elif "4y-5y" in row_text:
                    tenor = "5Y"

                elif "9y-10y" in row_text:
                    tenor = "10Y"

                if tenor is None:
                    continue

                numbers = []

                for value in values:

                    try:

                        number = float(
                            str(value)
                            .replace(",", "")
                            .replace("%", "")
                            .strip()
                        )

                        numbers.append(number)

                    except Exception:
                        pass

                if not numbers:
                    continue

                save_observation(
                    observation_date=reference_date,
                    source="CCIL",
                    series="GSEC_LEGACY",
                    tenor=tenor,
                    value=numbers[-1],
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
        security = row.get("security_description")
        maturity = row.get("maturity_date")
        lty = row.get("lty")
        ltp = row.get("ltp")

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
            f"{security} | {maturity} | LTY {lty}"
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
                "https://www.ccilindia.com/market-watch"
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
        security = row.get("security_description")
        maturity = row.get("maturity_date")
        lty = row.get("lty")
        ltp = row.get("ltp")

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
            f"{security} | {maturity} | LTY {lty}"
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
                "https://www.ccilindia.com/market-watch"
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

    ensure_table()

    save_money_market(
        reference_date
    )

    save_tradingview(
        reference_date
    )

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

    save_gsec(
        reference_date
    )

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
