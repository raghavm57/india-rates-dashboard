import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="India Rates Dashboard",
    page_icon="📊",
    layout="wide"
)


# ============================================================
# DATABASE
# ============================================================

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
            unit,
            security_description,
            maturity_date,
            ltp,
            publication_time
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


# ============================================================
# DATA CLEANING
# ============================================================

df["date"] = pd.to_datetime(
    df["date"]
)

df["maturity_date"] = pd.to_datetime(
    df["maturity_date"],
    errors="coerce"
)

df["value"] = pd.to_numeric(
    df["value"],
    errors="coerce"
)

df["ltp"] = pd.to_numeric(
    df["ltp"],
    errors="coerce"
)

df["publication_time"] = pd.to_datetime(
    df["publication_time"],
    errors="coerce"
)


# ============================================================
# HELPERS
# ============================================================

def get_market_dates(
    source,
    series
):

    market_df = df[
        (df["source"] == source)
        &
        (df["series"] == series)
    ]

    dates = sorted(
        market_df["date"].drop_duplicates(),
        reverse=True
    )

    if not dates:

        return (
            None,
            None,
            None
        )

    today_date = dates[0]

    yesterday_date = (
        dates[1]
        if len(dates) > 1
        else None
    )

    one_week_target = (
        today_date -
        pd.Timedelta(days=7)
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
    observation_date
):

    if observation_date is None:

        return None

    x = df[
        (df["source"] == source)
        &
        (df["series"] == series)
        &
        (df["tenor"] == tenor)
        &
        (df["date"] == observation_date)
    ]

    if x.empty:

        return None

    return float(
        x.iloc[0]["value"]
    )


def get_metadata(
    source,
    series,
    tenor,
    observation_date
):

    if observation_date is None:

        return {
            "security": None,
            "maturity": None,
            "ltp": None
        }

    x = df[
        (df["source"] == source)
        &
        (df["series"] == series)
        &
        (df["tenor"] == tenor)
        &
        (df["date"] == observation_date)
    ]

    if x.empty:

        return {
            "security": None,
            "maturity": None,
            "ltp": None
        }

    row = x.iloc[0]

    return {
        "security":
            row.get(
                "security_description"
            ),

        "maturity":
            row.get(
                "maturity_date"
            ),

        "ltp":
            row.get(
                "ltp"
            )
    }


def format_value(
    value
):

    if value is None:

        return "—"

    return f"{value:.3f}"


def format_change(
    current,
    previous,
    rate=True
):

    if (
        current is None
        or previous is None
    ):

        return "—"

    change = (
        current -
        previous
    )

    if rate:

        return (
            f"{change * 100:+.1f} bps"
        )

    return (
        f"{change:+.3f}"
    )


def market_row(
    name,
    source,
    series,
    tenor="",
    rate=True
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

        "Particulars":
            name,

        "Today":
            format_value(
                today
            ),

        "Yesterday":
            format_value(
                yesterday
            ),

        "1 Week":
            format_value(
                week
            ),

        "Δ 1D":
            format_change(
                today,
                yesterday,
                rate
            ),

        "Δ 1W":
            format_change(
                today,
                week,
                rate
            )
    }


# ============================================================
# LATEST UPDATE TIMESTAMP
# ============================================================

timestamp_df = df[
    df["publication_time"].notna()
].copy()

if not timestamp_df.empty:

    latest_timestamp = (
        timestamp_df["publication_time"].max()
    )

    # Convert timezone-aware timestamps to IST
    if latest_timestamp.tzinfo is not None:

        latest_timestamp = (
            latest_timestamp
            .tz_convert("Asia/Kolkata")
        )

    else:

        latest_timestamp = (
            latest_timestamp
            .tz_localize("Asia/Kolkata")
        )

    last_updated_text = (
        latest_timestamp.strftime(
            "%d-%b-%Y %I:%M:%S %p IST"
        )
    )

else:

    latest_date = df["date"].max()

    last_updated_text = (
        latest_date.strftime(
            "%d-%b-%Y"
        )
    )


# ============================================================
# HEADER
# ============================================================

st.title(
    "India Rates Dashboard"
)

st.caption(
    f"🕒 Last updated: **{last_updated_text}**"
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
    pd.DataFrame(
        ois_rows
    ),
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

    (
        "Call WACR",
        "CALL_WACR"
    ),

    (
        "TREPS WACR",
        "TREPS_WACR"
    ),

    (
        "Basket Repo WACR",
        "REPO_WACR"
    ),

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
            series
        )
    )

st.dataframe(
    pd.DataFrame(
        money_rows
    ),
    use_container_width=True,
    hide_index=True
)


# ============================================================
# T-BILLS
# ============================================================

st.subheader(
    "Treasury Bills — NDS-OM"
)

tbill_tenors = [

    (
        "91D",
        "91D"
    ),

    (
        "182D",
        "182D"
    ),

    (
        "364D",
        "364D"
    )
]

tbill_rows = []

for label, tenor in tbill_tenors:

    (
        today_date,
        yesterday_date,
        one_week_date
    ) = get_market_dates(
        "NDS-OM",
        "TBILL"
    )

    today = get_value(
        "NDS-OM",
        "TBILL",
        tenor,
        today_date
    )

    yesterday = get_value(
        "NDS-OM",
        "TBILL",
        tenor,
        yesterday_date
    )

    week = get_value(
        "NDS-OM",
        "TBILL",
        tenor,
        one_week_date
    )

    metadata = get_metadata(
        "NDS-OM",
        "TBILL",
        tenor,
        today_date
    )

    security = metadata["security"]

    maturity = metadata["maturity"]

    if pd.notna(maturity):

        maturity_text = (
            maturity.strftime(
                "%d-%b-%Y"
            )
        )

    else:

        maturity_text = "—"

    tbill_rows.append({

        "Tenor":
            label,

        "Security":
            security
            if pd.notna(security)
            else "—",

        "Maturity":
            maturity_text,

        "Today":
            format_value(
                today
            ),

        "Yesterday":
            format_value(
                yesterday
            ),

        "1 Week":
            format_value(
                week
            ),

        "Δ 1D":
            format_change(
                today,
                yesterday
            ),

        "Δ 1W":
            format_change(
                today,
                week
            )
    })


st.dataframe(
    pd.DataFrame(
        tbill_rows
    ),
    use_container_width=True,
    hide_index=True
)


# ============================================================
# G-SEC
# ============================================================

st.subheader(
    "Government Securities — NDS-OM"
)

gsec_tenors = [

    (
        "2Y",
        "2Y"
    ),

    (
        "5Y",
        "5Y"
    ),

    (
        "10Y",
        "10Y"
    )
]

gsec_rows = []

for label, tenor in gsec_tenors:

    (
        today_date,
        yesterday_date,
        one_week_date
    ) = get_market_dates(
        "NDS-OM",
        "GSEC"
    )

    today = get_value(
        "NDS-OM",
        "GSEC",
        tenor,
        today_date
    )

    yesterday = get_value(
        "NDS-OM",
        "GSEC",
        tenor,
        yesterday_date
    )

    week = get_value(
        "NDS-OM",
        "GSEC",
        tenor,
        one_week_date
    )

    metadata = get_metadata(
        "NDS-OM",
        "GSEC",
        tenor,
        today_date
    )

    security = metadata["security"]

    maturity = metadata["maturity"]

    if pd.notna(maturity):

        maturity_text = (
            maturity.strftime(
                "%d-%b-%Y"
            )
        )

    else:

        maturity_text = "—"

    gsec_rows.append({

        "Tenor":
            label,

        "Security":
            security
            if pd.notna(security)
            else "—",

        "Maturity":
            maturity_text,

        "Today":
            format_value(
                today
            ),

        "Yesterday":
            format_value(
                yesterday
            ),

        "1 Week":
            format_value(
                week
            ),

        "Δ 1D":
            format_change(
                today,
                yesterday
            ),

        "Δ 1W":
            format_change(
                today,
                week
            )
    })


st.dataframe(
    pd.DataFrame(
        gsec_rows
    ),
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

    (
        "US 10Y",
        "US10Y"
    ),

    (
        "Japan 10Y",
        "JP10Y"
    ),

    (
        "China 10Y",
        "CN10Y"
    )
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
    pd.DataFrame(
        global_rows
    ),
    use_container_width=True,
    hide_index=True
)


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "NDS-OM: G-Secs & T-Bills • "
    "CCIL: OIS & Money Market • "
    "TradingView: Global Bonds"
)

st.caption(
    "Today reflects the latest observation stored "
    "in Neon. Data is collected approximately every "
    "5 minutes during market hours."
)

st.caption(
    "Database: Neon PostgreSQL"
)
