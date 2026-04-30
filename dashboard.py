"""
FYERS BOT DASHBOARD v1.0
Real-time monitoring dashboard for the Beyond Human Trading Bot
Run with: streamlit run dashboard.py
"""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import os
import re
import time

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "trading_bot.db")
LOG_PATH = os.path.join(os.path.dirname(__file__), "trading_bot.log")
FYERS_LOG = os.path.join(os.path.dirname(__file__), "fyersRequests.log")

st.set_page_config(
    page_title="Fyers Bot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def load_table(query, params=()):
    conn = get_conn()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_scalar(query, params=()):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else 0

def color_pnl(val):
    color = "green" if val > 0 else ("red" if val < 0 else "gray")
    return f"color: {color}; font-weight: bold"

def tail_log(path, n=200):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    return lines[-n:]

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 Bot Dashboard")
    st.caption("Beyond Human v3.0 — NSE Intraday")
    st.divider()

    auto_refresh = st.toggle("Auto-refresh (30s)", value=True)
    if auto_refresh:
        st.caption("Page refreshes every 30 seconds")

    st.divider()
    mode_val = get_scalar("SELECT value FROM bot_state WHERE key='paper_trading'")
    capital_val = float(get_scalar("SELECT value FROM bot_state WHERE key='current_capital'") or 100000)
    mode_label = "📄 Paper Trading" if str(mode_val).lower() in ("1", "true", "") else "💰 Live Trading"
    st.metric("Mode", mode_label)
    st.metric("Capital", f"₹{capital_val:,.0f}")

    st.divider()
    page = st.radio("Navigate", [
        "Overview",
        "Trade History",
        "Symbol Performance",
        "Active Positions",
        "Signals",
        "Log Viewer",
    ])

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if auto_refresh:
    st.markdown(
        """<meta http-equiv="refresh" content="30">""",
        unsafe_allow_html=True,
    )

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
if page == "Overview":
    st.title("📊 Overview")
    st.caption(f"Last updated: {datetime.now().strftime('%d %b %Y, %I:%M:%S %p')}")

    # ── KPI Row ───────────────────────────────────────────────────────────────
    total_trades  = get_scalar("SELECT COUNT(*) FROM trades WHERE paper_trading=1")
    wins          = get_scalar("SELECT COUNT(*) FROM trades WHERE pnl>0 AND paper_trading=1")
    total_pnl     = get_scalar("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE paper_trading=1")
    today_pnl     = get_scalar("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE DATE(exit_time)=DATE('now','localtime') AND paper_trading=1")
    win_rate      = (wins / total_trades * 100) if total_trades > 0 else 0
    active_pos    = get_scalar("SELECT COUNT(*) FROM active_positions")
    active_cool   = get_scalar("SELECT COUNT(*) FROM cooldowns WHERE cooldown_until > DATETIME('now','localtime')")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Today's P&L",    f"₹{today_pnl:+,.0f}")
    c2.metric("Total P&L",      f"₹{total_pnl:+,.0f}")
    c3.metric("Win Rate",       f"{win_rate:.1f}%",    delta=f"Target: 55%")
    c4.metric("Total Trades",   total_trades)
    c5.metric("Active Positions", active_pos)
    c6.metric("Cooldowns",      active_cool)

    st.divider()

    # ── P&L Chart ─────────────────────────────────────────────────────────────
    st.subheader("📈 Capital Growth")
    ds = load_table("SELECT date, ending_capital, total_pnl, win_rate, total_trades FROM daily_stats ORDER BY date")
    if not ds.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=ds["date"], y=ds["ending_capital"],
            mode="lines+markers",
            name="Capital",
            line=dict(color="#00C853", width=2),
            fill="tozeroy",
            fillcolor="rgba(0,200,83,0.08)",
        ))
        fig.update_layout(
            height=280, margin=dict(l=0, r=0, t=10, b=0),
            xaxis_title="Date", yaxis_title="Capital (₹)",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ccc"),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No daily stats yet — run the bot to populate data.")

    col_l, col_r = st.columns(2)

    # ── Daily P&L Bar ─────────────────────────────────────────────────────────
    with col_l:
        st.subheader("📅 Daily P&L")
        if not ds.empty:
            colors = ["#00C853" if v >= 0 else "#FF1744" for v in ds["total_pnl"]]
            fig2 = go.Figure(go.Bar(
                x=ds["date"], y=ds["total_pnl"],
                marker_color=colors, name="Daily P&L"
            ))
            fig2.update_layout(
                height=240, margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#ccc"),
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No data yet.")

    # ── Cooldowns ─────────────────────────────────────────────────────────────
    with col_r:
        st.subheader("⏳ Active Cooldowns")
        cd = load_table(
            "SELECT symbol, cooldown_until, reason FROM cooldowns WHERE cooldown_until > DATETIME('now','localtime') ORDER BY cooldown_until"
        )
        if not cd.empty:
            cd["cooldown_until"] = pd.to_datetime(cd["cooldown_until"])
            cd["remaining"] = cd["cooldown_until"].apply(
                lambda x: str(x - datetime.now()).split(".")[0] if x > datetime.now() else "Expired"
            )
            st.dataframe(cd[["symbol", "remaining", "reason"]], use_container_width=True, hide_index=True)
        else:
            st.success("No active cooldowns — all stocks tradeable!")

    # ── Recent Trades ─────────────────────────────────────────────────────────
    st.subheader("🕐 Recent Trades")
    recent = load_table(
        "SELECT symbol, side, entry_price, exit_price, pnl, pnl_percent, exit_reason, exit_time FROM trades ORDER BY exit_time DESC LIMIT 10"
    )
    if not recent.empty:
        st.dataframe(
            recent.style.applymap(color_pnl, subset=["pnl", "pnl_percent"]),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("No completed trades yet. Bot is warming up!")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: TRADE HISTORY
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Trade History":
    st.title("📋 Trade History")

    trades = load_table("SELECT * FROM trades ORDER BY exit_time DESC")

    if trades.empty:
        st.info("No trades recorded yet.")
    else:
        # Filters
        fc1, fc2, fc3 = st.columns(3)
        symbols = ["All"] + sorted(trades["symbol"].unique().tolist())
        sides   = ["All", "BUY", "SELL"]
        reasons = ["All"] + sorted(trades["exit_reason"].dropna().unique().tolist())

        sel_sym    = fc1.selectbox("Symbol", symbols)
        sel_side   = fc2.selectbox("Side", sides)
        sel_reason = fc3.selectbox("Exit Reason", reasons)

        df = trades.copy()
        if sel_sym    != "All": df = df[df["symbol"]      == sel_sym]
        if sel_side   != "All": df = df[df["side"]        == sel_side]
        if sel_reason != "All": df = df[df["exit_reason"] == sel_reason]

        # Summary strip
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Trades shown", len(df))
        s2.metric("Wins",  int((df["pnl"] > 0).sum()))
        s3.metric("Losses", int((df["pnl"] < 0).sum()))
        s4.metric("Net P&L", f"₹{df['pnl'].sum():+,.0f}")

        display_cols = ["symbol","side","entry_price","exit_price","quantity","pnl","pnl_percent","exit_reason","entry_time","exit_time"]
        st.dataframe(
            df[display_cols].style.applymap(color_pnl, subset=["pnl","pnl_percent"]),
            use_container_width=True, hide_index=True
        )

        # Win/Loss pie
        pie_col, scatter_col = st.columns(2)
        with pie_col:
            st.subheader("Win / Loss split")
            pie_data = df["pnl"].apply(lambda x: "Win" if x > 0 else "Loss")
            counts = pie_data.value_counts()
            fig = px.pie(values=counts.values, names=counts.index,
                         color=counts.index,
                         color_discrete_map={"Win": "#00C853", "Loss": "#FF1744"})
            fig.update_layout(height=280, paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#ccc"))
            st.plotly_chart(fig, use_container_width=True)

        with scatter_col:
            st.subheader("P&L per trade")
            fig2 = go.Figure(go.Bar(
                x=list(range(len(df))),
                y=df["pnl"].tolist(),
                marker_color=["#00C853" if v >= 0 else "#FF1744" for v in df["pnl"]],
            ))
            fig2.update_layout(height=280, paper_bgcolor="rgba(0,0,0,0)",
                               plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#ccc"))
            st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SYMBOL PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Symbol Performance":
    st.title("🏦 Symbol Performance")

    sp = load_table("SELECT * FROM symbol_performance ORDER BY total_pnl DESC")
    if sp.empty:
        st.info("No symbol performance data yet.")
    else:
        best = sp.iloc[0]["symbol"] if sp.iloc[0]["total_pnl"] > 0 else "—"
        worst = sp.iloc[-1]["symbol"] if sp.iloc[-1]["total_pnl"] < 0 else "—"
        b1, b2, b3 = st.columns(3)
        b1.metric("Best Performer",  best)
        b2.metric("Worst Performer", worst)
        b3.metric("Stocks Tracked",  len(sp))

        st.dataframe(
            sp.style.applymap(color_pnl, subset=["total_pnl","avg_win","avg_loss"]),
            use_container_width=True, hide_index=True
        )

        fig = px.bar(sp, x="symbol", y="total_pnl", color="total_pnl",
                     color_continuous_scale=["#FF1744","#888","#00C853"],
                     title="P&L by Symbol")
        fig.update_layout(height=320, paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#ccc"))
        st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ACTIVE POSITIONS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Active Positions":
    st.title("💼 Active Positions")

    ap = load_table("SELECT * FROM active_positions")
    if ap.empty:
        st.info("No active positions right now.")
    else:
        for _, row in ap.iterrows():
            with st.expander(f"{row['symbol']} — {row['side']} @ ₹{row['entry_price']:.2f}"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Entry",      f"₹{row['entry_price']:.2f}")
                c2.metric("Stop Loss",  f"₹{row['current_stop']:.2f}")
                c3.metric("Target",     f"₹{row['target']:.2f}")
                c4.metric("Max Profit", f"₹{row['max_profit']:.2f}" if row['max_profit'] else "—")
                flags = []
                if row["breakeven_set"]: flags.append("✅ Breakeven set")
                if row["partial_booked"]: flags.append("✅ Partial booked")
                if flags:
                    st.caption("  |  ".join(flags))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SIGNALS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Signals":
    st.title("📡 Recent Signals")

    sigs = load_table("SELECT * FROM signals ORDER BY timestamp DESC LIMIT 100")
    if sigs.empty:
        st.info("No signals recorded yet.")
    else:
        fc1, fc2 = st.columns(2)
        syms = ["All"] + sorted(sigs["symbol"].unique().tolist())
        sel  = fc1.selectbox("Symbol", syms)
        only_executed = fc2.checkbox("Executed signals only")

        df = sigs.copy()
        if sel != "All": df = df[df["symbol"] == sel]
        if only_executed: df = df[df["executed"] == 1]

        executed_count = int(df["executed"].sum())
        s1, s2, s3 = st.columns(3)
        s1.metric("Signals shown", len(df))
        s2.metric("Executed",       executed_count)
        s3.metric("Filtered out",   len(df) - executed_count)

        st.dataframe(df[["timestamp","symbol","signal_type","price","strength","reasons","executed"]],
                     use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: LOG VIEWER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Log Viewer":
    st.title("🪵 Log Viewer")

    tab1, tab2 = st.tabs(["trading_bot.log", "fyersRequests.log"])

    with tab1:
        lines = tail_log(LOG_PATH, 300)
        if not lines:
            st.info("trading_bot.log is empty or doesn't exist yet.")
        else:
            level_filter = st.selectbox("Filter level", ["ALL", "ERROR", "WARNING", "INFO"], key="lvl1")
            keyword = st.text_input("Search keyword", key="kw1")
            filtered = lines
            if level_filter != "ALL":
                filtered = [l for l in filtered if level_filter in l]
            if keyword:
                filtered = [l for l in filtered if keyword.lower() in l.lower()]

            errors   = sum(1 for l in lines if "ERROR"   in l)
            warnings = sum(1 for l in lines if "WARNING" in l)
            c1, c2, c3 = st.columns(3)
            c1.metric("Total lines", len(lines))
            c2.metric("Errors",   errors,   delta=None)
            c3.metric("Warnings", warnings, delta=None)

            log_text = "".join(filtered[-200:])
            st.code(log_text, language="log")

    with tab2:
        lines2 = tail_log(FYERS_LOG, 100)
        if not lines2:
            st.info("fyersRequests.log is empty.")
        else:
            keyword2 = st.text_input("Search keyword", key="kw2")
            filtered2 = lines2
            if keyword2:
                filtered2 = [l for l in filtered2 if keyword2.lower() in l.lower()]

            errors2   = sum(1 for l in lines2 if "error" in l.lower())
            c1, c2 = st.columns(2)
            c1.metric("Lines shown", len(filtered2))
            c2.metric("Errors",      errors2)

            st.code("".join(filtered2[-100:]), language="log")
