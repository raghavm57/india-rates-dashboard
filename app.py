import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(page_title="India Rates Dashboard", layout="wide")

DATABASE_URL = st.secrets["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

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
            PRIMARY KEY (date, source, series, tenor)
        );
    """))

st.title("India Rates Dashboard")
st.caption("Personal market-data repository — PostgreSQL-backed")

df = pd.read_sql(text("""
    SELECT date, source, series, tenor, value, unit, status
    FROM observations
    ORDER BY date, source, series, tenor
"""), engine)

if df.empty:
    st.info("PostgreSQL is connected, but no market observations have been loaded yet.")
else:
    latest_date = df["date"].max()
    latest = df[df["date"] == latest_date]

    cols = st.columns(4)
    cards = [
        ("FBIL", "OIS", "3M"),
        ("FBIL", "OIS", "5Y"),
        ("CCIL", "CALL_WACR", ""),
        ("CCIL", "TREPS_WACR", ""),
    ]
    for col, (src, series, tenor) in zip(cols, cards):
        x = latest[(latest.source == src) & (latest.series == series) & (latest.tenor == tenor)]
        col.metric(f"{series} {tenor}".strip(), f"{x.iloc[0].value:.3f}%" if not x.empty else "—")

    st.subheader(f"Latest observations — {latest_date}")
    st.dataframe(latest, use_container_width=True)

    st.subheader("Historical series")
    options = sorted(df.apply(lambda r: f"{r.source} | {r.series} | {r.tenor}", axis=1).unique())
    selected = st.selectbox("Series", options)
    src, series, tenor = selected.split(" | ")
    chart = df[(df.source == src) & (df.series == series) & (df.tenor == tenor)].copy()
    chart["date"] = pd.to_datetime(chart["date"])
    st.line_chart(chart.sort_values("date").set_index("date")["value"])

st.divider()
st.caption("Database: Neon PostgreSQL • Dashboard: Streamlit Community Cloud")

