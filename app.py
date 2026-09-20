import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="India Rates Dashboard",
    layout="wide"
)

DATABASE_URL = st.secrets["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_sql(
    text("""
        SELECT
            date,
            source,
            series,
            tenor,
            value,
            unit
        FROM observations
        WHERE status = 'published'
        ORDER BY date
    """),
    engine
)

if df.empty:

    st.info(
        "PostgreSQL is connected, but no market observations "
        "have been loaded yet."
    )

    st.stop()


df["date"] = pd.to_datetime(
    df["date"]
)


# ============================================================
# GLOBAL LATEST DATE
# ============================================================

latest_date = df["date"].max()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_market_dates(source, series):

    market_df = df[
        (df["source"] == source)
        & (df["series"] == series)
    ]

    dates = sorted(
        market_df["date"].drop_duplicates(),
        reverse=True
    )

    if not dates:
        return None, None, None

    today_date = dates[0]

    yesterday_date = (
        dates[1]
        if len(dates) > 1
        else None
    )

    one_week_target = (
        today_date - pd.Timedelta(days=7)
    )

    week_dates = [
        d
        for d in dates
        if d <= one_week_target
    ]

    one_week_date = (
        week_dates[0]
        if week_dates
        else None
    )

    return (
        today_date,
        yesterday_date,
        one_week_date
    )


def get_value(
    source,
    series,
    tenor,
    date
):

    if date is None:
        return None

    x = df[
        (df["source"] == source)
        & (df["series"] == series)
        & (df["tenor"] == tenor)
        & (df["date"] == date)
    ]

    if x.empty:
        return None

    return float(
        x.iloc[0]["value"]
    )


def format_value(value):

    if value is None:
        return "—"

    return f"{value:.3f}"


def format_change(
    current,
    previous,
    rate=True
):

    if current is None or previous is None:
        return "—"

    change = current - previous

    if rate:

        return f"{change * 100:+.1f} bps"

    return f"{change:+.3f}"


def market_row(
    name,
    source,
    series,
    tenor=""
):

    (
        today_date,
        yesterday_date,
        one_week_date
    ) = get_market_dates(
        source,
        series
    )

    today = get_value(
        source,
        series,
        tenor,
        today_date
    )

    yesterday = get_value(
        source,
        series,
        tenor,
        yesterday_date
    )

    week = get_value(
        source,
        series,
        tenor,
        one_week_date
    )

    return {

        "Particulars": name,

        "Today": format_value(
            today
        ),

        "Yesterday": format_value(
            yesterday
        ),

        "1 Week": format_value(
            week
        ),

        "Δ 1D": format_change(
            today,
            yesterday
        ),

        "Δ 1W": format_change(
            today,
            week
        )
    }


# ============================================================
# HEADER
# ============================================================

st.title(
    "India Rates Dashboard"
)

st.caption(
    f"Latest available market date: "
    f"{latest_date.strftime('%d-%b-%Y')}"
)


# ============================================================
# OIS
# ============================================================

st.subheader(
    "OIS Curve"
)

ois_tenors = [

    ("OIS 1M", "1M"),

    ("OIS 2M", "2M"),

    ("OIS 3M", "3M"),

    ("OIS 6M", "6M"),

    ("OIS 1Y", "1Y"),

    ("OIS 2Y", "2Y"),

    ("OIS 3Y", "3Y"),

    ("OIS 5Y", "5Y"),

    ("OIS 10Y", "10Y")
]


ois_rows = []

for name, tenor in ois_tenors:

    ois_rows.append(
        market_row(
            name,
            "CCIL",
            "OIS",
            tenor
        )
    )


st.dataframe(
    pd.DataFrame(ois_rows),
    use_container_width=True,
    hide_index=True
)


# ============================================================
# MONEY MARKET
# ============================================================

st.subheader(
    "Money Market"
)

money_market = [

    ("Call WACR", "CALL_WACR"),

    ("TREPS WACR", "TREPS_WACR"),

    ("Repo WACR", "REPO_WACR"),

    (
        "Special Repo WACR",
        "SPECIAL_REPO_WACR"
    )
]


money_rows = []

for name, series in money_market:

    money_rows.append(
        market_row(
            name,
            "CCIL",
            series,
            ""
        )
    )


st.dataframe(
    pd.DataFrame(money_rows),
    use_container_width=True,
    hide_index=True
)


# ============================================================
# GOVERNMENT SECURITIES
# ============================================================

st.subheader(
    "Government Securities"
)

gsec_tenors = [

    ("3Y G-Sec", "3Y"),

    ("5Y G-Sec", "5Y"),

    ("10Y G-Sec", "10Y"),

    ("30Y G-Sec", "30Y")
]


gsec_rows = []

for name, tenor in gsec_tenors:

    gsec_rows.append(
        market_row(
            name,
            "CCIL",
            "GSEC",
            tenor
        )
    )


st.dataframe(
    pd.DataFrame(gsec_rows),
    use_container_width=True,
    hide_index=True
)


# ============================================================
# GLOBAL BONDS
# ============================================================

st.subheader(
    "Global Bonds"
)

global_bonds = [

    ("US 10Y", "US10Y"),

    ("Japan 10Y", "JP10Y"),

    ("China 10Y", "CN10Y")
]


global_rows = []

for name, tenor in global_bonds:

    global_rows.append(
        market_row(
            name,
            "TradingView",
            "GLOBAL_BOND",
            tenor
        )
    )


st.dataframe(
    pd.DataFrame(global_rows),
    use_container_width=True,
    hide_index=True
)


# ============================================================
# DATABASE INFORMATION
# ============================================================

st.divider()

st.caption(
    f"Global latest date: "
    f"{latest_date.strftime('%d-%b-%Y')}"
)

st.caption(
    "Each market section uses its own latest available "
    "observation date."
)

st.caption(
    "Source: CCIL / TradingView • "
    "Database: Neon PostgreSQL"
)
