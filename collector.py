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
        f"Money-market
