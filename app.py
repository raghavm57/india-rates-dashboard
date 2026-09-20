import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

DB = Path(__file__).parent / "data" / "market.db"
st.set_page_config(page_title="India Rates Dashboard", layout="wide")

def read_data():
    if not DB.exists():
        return pd.DataFrame(columns=["date","source","series","tenor","value","unit"])
    con = sqlite3.connect(DB)
    df = pd.read_sql_query("SELECT * FROM observations ORDER BY date", con)
    con.close()
    return df

st.title("India Rates Dashboard")
st.caption("Personal market-data repository — benchmark / WACR observations")
df = read_data()

if df.empty:
    st.info("Database is empty. Run: python collector.py")
else:
    latest_date = df["date"].max()
    latest = df[df["date"] == latest_date]
    cols = st.columns(4)
    for col, src, series, tenor in [
        (cols[0],"FBIL","OIS","3M"), (cols[1],"FBIL","OIS","5Y"),
        (cols[2],"CCIL","CALL_WACR",""), (cols[3],"CCIL","TREPS_WACR","")
    ]:
        x = latest[(latest.source==src)&(latest.series==series)&(latest.tenor==tenor)]
        col.metric(f"{series} {tenor}".strip(), f"{x.value.iloc[-1]:.3f}%" if not x.empty else "—")
    options = df.apply(lambda r: f"{r.source} | {r.series} | {r.tenor}", axis=1).unique()
    selected = st.selectbox("Series", options)
    src, series, tenor = selected.split(" | ")
    c = df[(df.source==src)&(df.series==series)&(df.tenor==tenor)].copy()
    c["date"] = pd.to_datetime(c["date"])
    st.plotly_chart(px.line(c, x="date", y="value", title=selected), use_container_width=True)
    st.dataframe(latest.sort_values(["source","series","tenor"]), use_container_width=True)
