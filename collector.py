import os
from io import StringIO

import pandas as pd
import requests
from sqlalchemy import create_engine, text


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

DATABASE_URL = os.environ["DATABASE_URL"]

CCIL_URL = (
    "https://www.ccilindia.com/"
    "money-market-rates-and-volumes-most-liquid-tenor-"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)


# ---------------------------------------------------------
# FETCH CCIL DATA
# ---------------------------------------------------------

def fetch_ccil():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36"
        )
    }

    response = requests.get(
        CCIL_URL,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))

    if not tables:
        raise RuntimeError("No table found on CCIL page")

    # Find the money-market table
    table = None

    for t in tables:
        columns = [str(c).lower() for c in t.columns]

        if (
            any("date" in c for c in columns)
            and any("wtd avg" in c for c in columns)
        ):
            table = t
            break

    if table is None:
        raise RuntimeError("CCIL money-market table not found")

    table.columns = [
        str(c).strip()
        for c in table.columns
    ]

    print("CCIL table found:")
    print(table.head())


    # -----------------------------------------------------
    # NORMALISE COLUMN NAMES
    # -----------------------------------------------------

    column_map = {}

    for col in table.columns:

        name = col.lower()

        if name == "date":
            column_map[col] = "date"

        elif name == "type":
            column_map[col] = "type"

        elif "wtd avg" in name:
            column_map[col] = "value"

        elif "volume" in name:
            column_map[col] = "volume"


    table = table.rename(columns=column_map)


    required = {"date", "type", "value"}

    if not required.issubset(table.columns):
        raise RuntimeError(
            f"Required columns missing. "
            f"Found: {table.columns.tolist()}"
        )


    # -----------------------------------------------------
    # CLEAN DATA
    # -----------------------------------------------------

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
        subset=["date", "value"]
    )


    # -----------------------------------------------------
    # KEEP ONLY REQUIRED MARKETS
    # -----------------------------------------------------

    series_map = {
        "Call": "CALL_WACR",
        "TREP": "TREPS_WACR",
        "Basket Repo": "REPO_WACR",
    }

    table["series"] = table["type"].map(series_map)

    table = table.dropna(
        subset=["series"]
    )

    return table


# ---------------------------------------------------------
# WRITE TO NEON
# ---------------------------------------------------------

def save_to_database(table):

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
            'CCIL',
            :series,
            '',
            :value,
            '%',
            CURRENT_TIMESTAMP,
            :source_url,
            'published'
        )
        ON CONFLICT
        (date, source, series, tenor)
        DO UPDATE SET
            value = EXCLUDED.value,
            publication_time = EXCLUDED.publication_time,
            source_url = EXCLUDED.source_url,
            status = EXCLUDED.status
    """)

    rows = []

    for _, row in table.iterrows():

        rows.append({
            "date": row["date"],
            "series": row["series"],
            "value": float(row["value"]),
            "source_url": CCIL_URL,
        })

    with engine.begin() as conn:

        conn.execute(
            sql,
            rows
        )

    print(
        f"Inserted/updated {len(rows)} observations."
    )


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

if __name__ == "__main__":

    print("Starting CCIL collector...")

    data = fetch_ccil()

    print(
        f"Fetched {len(data)} CCIL observations."
    )

    save_to_database(data)

    print("CCIL collection completed successfully.")
