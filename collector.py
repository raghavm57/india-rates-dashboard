import os
import json
from io import StringIO
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from sqlalchemy import create_engine, text


# ============================================================
# DATABASE
# ============================================================

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)


# ============================================================
# CCIL URLs
# ============================================================

CCIL_MONEY_URL = (
    "https://www.ccilindia.com/"
    "money-market-rates-and-volumes-most-liquid-tenor-"
)

CCIL_OIS_URL = (
    "https://www.ccilindia.com/"
    "interbank-inr-interest-rate-swaps"
    "?p_p_cacheability=cacheLevelPage"
    "&p_p_id=CcilRealTimeMarketWatchMainPageAjax_CcilRealTimeMarketWatchMainPageAjaxPortlet_INSTANCE_qown"
    "&p_p_lifecycle=2"
    "&p_p_mode=view"
    "&p_p_resource_id=mainReport"
    "&p_p_state=normal"
)

CCIL_GSEC_URL = (
    "https://www.ccilindia.com/"
    "en/tenorwise-indicative-yields"
)

# ============================================================
# TRADINGVIEW
# ============================================================

TRADINGVIEW_SCANNER_URL = (
    "https://scanner.tradingview.com/bonds/scan"
)

TRADINGVIEW_SYMBOLS = [
    "TVC:US10Y",
    "TVC:JP10Y",
    "TVC:CN10Y",
]
# ============================================================
# COMMON HTTP HEADERS
# ============================================================

SOURCE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}


# ============================================================
# DATABASE TABLE
# ============================================================

def ensure_table():

    with engine.begin() as conn:

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS observations (

                date DATE NOT NULL,

                source TEXT NOT NULL,

                series TEXT NOT NULL,

                tenor TEXT NOT NULL DEFAULT '',

                value DOUBLE PRECISION NOT NULL,

                unit TEXT NOT NULL DEFAULT '%',

                publication_time TIMESTAMPTZ,

                source_url TEXT,

                status TEXT NOT NULL DEFAULT 'published',

                PRIMARY KEY (
                    date,
                    source,
                    series,
                    tenor
                )
            );
        """))


# ============================================================
# SAVE ONE OBSERVATION
# ============================================================

def save_observation(
    obs_date,
    source,
    series,
    tenor,
    value,
    source_url
):

    if value is None:
        return

    sql = text("""
        INSERT INTO observations
        (
            date,
            source,
            series,
            tenor,
            value,
            unit,
            publication_time,
            source_url,
            status
        )

        VALUES
        (
            :date,
            :source,
            :series,
            :tenor,
            :value,
            '%',
            CURRENT_TIMESTAMP,
            :source_url,
            'published'
        )

        ON CONFLICT
        (
            date,
            source,
            series,
            tenor
        )

        DO UPDATE SET

            value = EXCLUDED.value,

            publication_time =
                EXCLUDED.publication_time,

            source_url =
                EXCLUDED.source_url,

            status =
                EXCLUDED.status
    """)

    with engine.begin() as conn:

        conn.execute(
            sql,
            {
                "date": obs_date,
                "source": source,
                "series": series,
                "tenor": tenor,
                "value": float(value),
                "source_url": source_url
            }
        )


# ============================================================
# MONEY MARKET
# ============================================================

def fetch_money_market():

    response = requests.get(
        CCIL_MONEY_URL,
        headers=SOURCE_HEADERS,
        timeout=30
    )

    response.raise_for_status()

    tables = pd.read_html(
        StringIO(response.text)
    )

    table = None

    for t in tables:

        columns = [
            str(c).lower()
            for c in t.columns
        ]

        if (
            any("date" in c for c in columns)
            and
            any("wtd avg" in c for c in columns)
        ):

            table = t
            break

    if table is None:

        raise RuntimeError(
            "CCIL money-market table not found"
        )

    table.columns = [
        str(c).strip()
        for c in table.columns
    ]

    column_map = {}

    for col in table.columns:

        name = col.lower()

        if name == "date":

            column_map[col] = "date"

        elif name == "type":

            column_map[col] = "type"

        elif "wtd avg" in name:

            column_map[col] = "value"

    table = table.rename(
        columns=column_map
    )

    required = {
        "date",
        "type",
        "value"
    }

    if not required.issubset(
        table.columns
    ):

        raise RuntimeError(
            "Unexpected CCIL money-market "
            f"columns: {table.columns.tolist()}"
        )

    table["date"] = pd.to_datetime(
        table["date"],
        errors="coerce"
    ).dt.date

    table["value"] = pd.to_numeric(
        table["value"],
        errors="coerce"
    )

    table["type"] = (
        table["type"]
        .astype(str)
        .str.strip()
    )

    table = table.dropna(
        subset=[
            "date",
            "value"
        ]
    )

    return table


def save_money_market():

    table = fetch_money_market()

    series_map = {

        "Call":
            "CALL_WACR",

        "TREP":
            "TREPS_WACR",

        "Basket Repo":
            "REPO_WACR",

        "Special Repo":
            "SPECIAL_REPO_WACR"
    }

    count = 0

    for _, row in table.iterrows():

        series = series_map.get(
            row["type"]
        )

        if series is None:
            continue

        save_observation(

            obs_date=row["date"],

            source="CCIL",

            series=series,

            tenor="",

            value=row["value"],

            source_url=CCIL_MONEY_URL
        )

        count += 1

    print(
        f"Money-market observations saved: {count}"
    )

def fetch_tradingview():

    payload = {
        "symbols": {
            "tickers": TRADINGVIEW_SYMBOLS,
            "query": {
                "types": []
            }
        },
        "columns": [
            "name",
            "close",
            "change"
        ]
    }

    response = requests.post(
        "https://scanner.tradingview.com/bonds/scan",
        json=payload,
        headers=SOURCE_HEADERS,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    return data.get("data", [])
# ============================================================
# OIS
# ============================================================

def fetch_ois():

    response = requests.get(
        CCIL_OIS_URL,
        headers=SOURCE_HEADERS,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    raw = data.get(
        "resultMiborOis"
    )

    if raw is None:

        raise RuntimeError(
            "CCIL OIS data not found"
        )

    rows = json.loads(raw)

    return rows


def save_ois(reference_date):

    rows = fetch_ois()

    wanted_tenors = {

        "1M",
        "2M",
        "3M",
        "6M",
        "1Y",
        "2Y",
        "3Y",
        "5Y",
        "10Y"
    }

    count = 0

    for row in rows:

        tenor = row.get(
            "ismy_trad_mrty"
        )

        if tenor not in wanted_tenors:
            continue

        value = row.get(
            "ismy_drvt_warr"
        )

        if value in (
            None,
            "",
            "null"
        ):

            continue

        save_observation(

            obs_date=reference_date,

            source="CCIL",

            series="OIS",

            tenor=tenor,

            value=float(value),

            source_url=CCIL_OIS_URL
        )

        count += 1

    print(
        f"OIS observations saved: {count}"
    )


# ============================================================
# G-SEC
# ============================================================

def fetch_gsec():

    response = requests.get(
        CCIL_GSEC_URL,
        headers=SOURCE_HEADERS,
        timeout=30
    )

    response.raise_for_status()

    tables = pd.read_html(
        StringIO(response.text)
    )

    table = None

    for t in tables:

        columns = [
            str(c).lower()
            for c in t.columns
        ]

        if (
            any("date" in c for c in columns)
            and
            any("tenor" in c for c in columns)
            and
            any("ytm" in c for c in columns)
        ):

            table = t
            break

    if table is None:

        raise RuntimeError(
            "CCIL G-sec table not found"
        )

    table.columns = [
        str(c).strip()
        for c in table.columns
    ]

    return table


def save_gsec():

    table = fetch_gsec()

    date_col = next(
        c
        for c in table.columns
        if "date" in c.lower()
    )

    tenor_col = next(
        c
        for c in table.columns
        if "tenor" in c.lower()
    )

    ytm_col = next(
        c
        for c in table.columns
        if "ytm" in c.lower()
    )

    table[date_col] = pd.to_datetime(
        table[date_col],
        errors="coerce"
    ).dt.date

    table[ytm_col] = pd.to_numeric(
        table[ytm_col],
        errors="coerce"
    )

    table = table.dropna(
        subset=[
            date_col,
            ytm_col
        ]
    )

    wanted = {

        "4Y-5Y":
            "5Y",

        "9Y-10Y":
            "10Y",

        "28Y-30Y":
            "30Y"
    }

    count = 0

    for _, row in table.iterrows():

        bucket = str(
            row[tenor_col]
        ).strip()

        dashboard_tenor = wanted.get(
            bucket
        )

        if dashboard_tenor is None:
            continue

        save_observation(

            obs_date=row[date_col],

            source="CCIL",

            series="GSEC",

            tenor=dashboard_tenor,

            value=row[ytm_col],

            source_url=CCIL_GSEC_URL
        )

        count += 1

    print(
        f"G-sec observations saved: {count}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "Starting CCIL market-data collector..."
    )

    # Create database table if required
    ensure_table()

    # --------------------------------------------------------
    # Money market
    # --------------------------------------------------------

    save_money_market()

    # --------------------------------------------------------
    # Determine today's India date
    # --------------------------------------------------------

    india_date = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).date()

    print(
        f"India date: {india_date}"
    )

    # --------------------------------------------------------
    # OIS
    #
    # Run only Monday-Friday.
    # Skip Saturday and Sunday.
    # --------------------------------------------------------

    print("DEBUG — collecting OIS regardless of weekday.")
    save_ois(india_date)

    # --------------------------------------------------------
    # G-sec
    # --------------------------------------------------------

    save_gsec()

    # --------------------------------------------------------
    # Finished
    # --------------------------------------------------------

    print(
        "CCIL collection completed successfully."
)
