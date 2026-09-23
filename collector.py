import os
import json
from io import StringIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from sqlalchemy import create_engine, text

from ndsom_fetcher import fetch_ndsom_data


# ============================================================
# DATABASE
# ============================================================

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)


# ============================================================
# CCIL URLS
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
# HTTP HEADERS
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

                security_description TEXT,
                maturity_date DATE,
                ltp DOUBLE PRECISION,

                status TEXT NOT NULL DEFAULT 'published',

                PRIMARY KEY (
                    date,
                    source,
                    series,
                    tenor
                )
            );
        """))

        # Existing table may already exist without these columns.
        conn.execute(text("""
            ALTER TABLE observations
            ADD COLUMN IF NOT EXISTS
            security_description TEXT;
        """))

        conn.execute(text("""
            ALTER TABLE observations
            ADD COLUMN IF NOT EXISTS
            maturity_date DATE;
        """))

        conn.execute(text("""
            ALTER TABLE observations
            ADD COLUMN IF NOT EXISTS
            ltp DOUBLE PRECISION;
        """))


# ============================================================
# SAVE OBSERVATION
# ============================================================

def save_observation(
    obs_date,
    source,
    series,
    tenor,
    value,
    source_url,
    security_description=None,
    maturity_date=None,
    ltp=None
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
            security_description,
            maturity_date,
            ltp,
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
            :security_description,
            :maturity_date,
            :ltp,
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

            value =
                EXCLUDED.value,

            publication_time =
                EXCLUDED.publication_time,

            source_url =
                EXCLUDED.source_url,

            security_description =
                EXCLUDED.security_description,

            maturity_date =
                EXCLUDED.maturity_date,

            ltp =
                EXCLUDED.ltp,

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
                "source_url": source_url,
                "security_description":
                    security_description,
                "maturity_date":
                    maturity_date,
                "ltp":
                    float(ltp)
                    if ltp not in (
                        None,
                        "",
                        "null"
                    )
                    else None
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
            "Unexpected CCIL money-market columns"
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

    return table.dropna(
        subset=[
            "date",
            "value"
        ]
    )


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


# ============================================================
# TRADINGVIEW GLOBAL BONDS
# ============================================================

def fetch_tradingview():

    payload = {

        "symbols": {

            "tickers":
                TRADINGVIEW_SYMBOLS,

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
        TRADINGVIEW_SCANNER_URL,
        json=payload,
        headers=SOURCE_HEADERS,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    return data.get(
        "data",
        []
    )


def save_tradingview(reference_date):

    rows = fetch_tradingview()

    ticker_map = {

        "TVC:US10Y":
            "US10Y",

        "TVC:JP10Y":
            "JP10Y",

        "TVC:CN10Y":
            "CN10Y"
    }

    count = 0

    for row in rows:

        ticker = row.get("s")

        if ticker not in ticker_map:
            continue

        data = row.get(
            "d",
            []
        )

        if len(data) < 2:
            continue

        value = data[1]

        if value is None:
            continue

        save_observation(
            obs_date=reference_date,
            source="TradingView",
            series="GLOBAL_BOND",
            tenor=ticker_map[ticker],
            value=float(value),
            source_url="https://www.tradingview.com/"
        )

        count += 1

    print(
        f"TradingView global bond observations saved: {count}"
    )


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

    try:

        data = response.json()

    except ValueError:

        print(
            "CCIL OIS unavailable — skipping OIS."
        )

        print(
            f"Status: {response.status_code}"
        )

        print(
            f"Content-Type: "
            f"{response.headers.get('Content-Type')}"
        )

        print(
            f"Response preview: "
            f"{response.text[:200]}"
        )

        return []

    raw = data.get(
        "resultMiborOis"
    )

    if raw is None:

        print(
            "CCIL OIS data not found — skipping OIS."
        )

        return []

    return json.loads(raw)


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
# LEGACY G-SEC
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
        f"Legacy G-sec observations saved: {count}"
    )


# ============================================================
# NDS-OM
# ============================================================

def parse_maturity_date(value):

    try:

        return datetime.strptime(
            value.strip(),
            "%d/%m/%Y"
        ).date()

    except Exception:

        return None


def select_gsec_bucket(
    gsecs,
    target_years
):

    today = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).date()

    target_date = today + timedelta(
        days=365.25 * target_years
    )

    candidates = []

    for item in gsecs:

        maturity = parse_maturity_date(
            item["maturity_date"]
        )

        if maturity is None:
            continue

        if maturity <= today:
            continue

        try:

            lty = float(
                item["lty"]
            )

        except Exception:

            continue

        if lty <= 0:
            continue

        distance = abs(
            (
                maturity -
                target_date
            ).days
        )

        candidates.append(
            (
                distance,
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


def save_ndsom(reference_date):

    print(
        "\nStarting NDS-OM browser fetch..."
    )

    result = fetch_ndsom_data()

    gsecs = result.get(
        "gsecs",
        []
    )

    tbills = result.get(
        "tbills",
        []
    )

    print(
        f"NDS-OM G-Secs received: "
        f"{len(gsecs)}"
    )

    print(
        f"NDS-OM T-Bills received: "
        f"{len(tbills)}"
    )

    # --------------------------------------------------------
    # G-SEC BUCKETS
    # --------------------------------------------------------

    gsec_targets = {

        "2Y": 2,

        "5Y": 5,

        "10Y": 10
    }

    gsec_count = 0

    for tenor, years in gsec_targets.items():

        item = select_gsec_bucket(
            gsecs,
            years
        )

        if item is None:

            print(
                f"NDS-OM {tenor}: "
                f"not found"
            )

            continue

        maturity = parse_maturity_date(
            item["maturity_date"]
        )

        save_observation(
            obs_date=reference_date,
            source="NDS-OM",
            series="GSEC",
            tenor=tenor,
            value=float(item["lty"]),
            source_url=(
                "https://www.ccilindia.com/"
                "market-watch"
            ),
            security_description=
                item["security_description"],
            maturity_date=maturity,
            ltp=item.get("ltp")
        )

        print(
            f"NDS-OM GSEC {tenor}: "
            f"{item['security_description']} | "
            f"{item['maturity_date']} | "
            f"LTY {item['lty']}"
        )

        gsec_count += 1

    # --------------------------------------------------------
    # T-BILLS
    # --------------------------------------------------------

    tbill_count = 0

    for item in tbills:

        tenor = item.get(
            "tenor"
        )

        if tenor not in {
            "91D",
            "182D",
            "364D"
        }:

            continue

        maturity = parse_maturity_date(
            item["maturity_date"]
        )

        save_observation(
            obs_date=reference_date,
            source="NDS-OM",
            series="TBILL",
            tenor=tenor,
            value=float(item["lty"]),
            source_url=(
                "https://www.ccilindia.com/"
                "market-watch"
            ),
            security_description=
                item["security_description"],
            maturity_date=maturity,
            ltp=item.get("ltp")
        )

        print(
            f"NDS-OM T-Bill {tenor}: "
            f"{item['security_description']} | "
            f"{item['maturity_date']} | "
            f"LTY {item['lty']}"
        )

        tbill_count += 1

    print(
        f"NDS-OM G-Secs saved: "
        f"{gsec_count}"
    )

    print(
        f"NDS-OM T-Bills saved: "
        f"{tbill_count}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "Starting market-data collector..."
    )

    ensure_table()

    # --------------------------------------------------------
    # India date
    # --------------------------------------------------------

    india_date = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).date()

    print(
        f"India date: {india_date}"
    )

    # --------------------------------------------------------
    # Money market
    # --------------------------------------------------------

    save_money_market()

    # --------------------------------------------------------
    # TradingView
    # --------------------------------------------------------

    save_tradingview(
        india_date
    )

    # --------------------------------------------------------
    # OIS
    # --------------------------------------------------------

    if india_date.weekday() < 5:

        print(
            "Trading weekday — collecting OIS."
        )

        save_ois(
            india_date
        )

    else:

        print(
            "Weekend — skipping OIS collection."
        )

    # --------------------------------------------------------
    # Legacy CCIL G-Sec
    # --------------------------------------------------------

    # Keep this for historical continuity.
    save_gsec()

    # --------------------------------------------------------
    # NDS-OM G-Secs + T-Bills
    # --------------------------------------------------------

    save_ndsom(
        india_date
    )

    # --------------------------------------------------------
    # FINISHED
    # -------------------------------------

    print(
        "\n=========================================="
    )

    print(
        "MARKET-DATA COLLECTION COMPLETED"
    )

    print(
        "=========================================="
    )
