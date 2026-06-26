"""
historical_backtest.py — Tab 5: Historical Backtest
Same leg builder as spread chart, past date picker, full day spread chart.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

from fyers_client import (
    LOT_SIZES, get_expiries, get_strikes, build_symbol_from_label,
    get_candles, dark_chart_layout, get_ist_now,
)
from styles import (
    section_header, render_stat_row, leg_badge,
    C_GREEN, C_RED, C_BLUE, C_ORANGE, C_MUTED, C_TEXT,
)


def _build_bt_legs():
    """Build leg inputs for backtest."""
    _SS = st.session_state
    num_legs = _SS.get("bt_num_legs", 2)
    legs = []
    cols = st.columns(num_legs)

    for i in range(num_legs):
        leg_num = i + 1
        with cols[i]:
            st.markdown(leg_badge(leg_num), unsafe_allow_html=True)

            idx = st.selectbox(
                "Index", ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY"],
                key=f"bt_leg{leg_num}_index",
            )

            expiries = get_expiries(idx)
            exp = st.selectbox(
                "Expiry", expiries if expiries else ["Loading..."],
                key=f"bt_leg{leg_num}_expiry",
            )

            strikes = get_strikes(idx, exp) if exp and exp != "Loading..." else []
            strike = st.selectbox(
                "Strike", strikes if strikes else [0],
                key=f"bt_leg{leg_num}_strike",
            )

            c1, c2 = st.columns(2)
            with c1:
                opt_type = st.selectbox("Type", ["CE", "PE"], key=f"bt_leg{leg_num}_opt_type")
            with c2:
                buy_sell = st.selectbox("Side", ["Buy", "Sell"], key=f"bt_leg{leg_num}_buy_sell")

            ratio = st.number_input(
                "Ratio", min_value=1, max_value=10, value=1,
                key=f"bt_leg{leg_num}_ratio",
            )

            if exp and exp != "Loading..." and strike and strike != 0:
                sym = build_symbol_from_label(idx, exp, opt_type, strike)
                lot = LOT_SIZES.get(idx, 1)
                legs.append({
                    "leg_num": leg_num,
                    "index": idx,
                    "expiry": exp,
                    "strike": strike,
                    "opt_type": opt_type,
                    "buy_sell": buy_sell,
                    "ratio": ratio,
                    "symbol": sym,
                    "lot_size": lot,
                })

    return legs


def render_backtest():
    """Main render function for Historical Backtest tab."""
    _SS = st.session_state

    st.markdown(
        '<div style="font-size:20px;font-weight:600;color:#d1d4dc;padding:4px 0;">🕰️ Historical Backtest</div>',
        unsafe_allow_html=True,
    )

    # Controls
    c1, c2, c3 = st.columns(3)
    with c1:
        _SS["bt_num_legs"] = st.selectbox(
            "Number of Legs", [2, 3, 4, 5, 6],
            index=[2, 3, 4, 5, 6].index(_SS.get("bt_num_legs", 2)),
            key="bt_num_legs_sel",
        )
    with c2:
        bt_date = st.date_input(
            "Date",
            value=get_ist_now().date(),
            key="bt_date",
        )
    with c3:
        tf_options = ["1", "5", "15", "60"]
        tf_labels = ["1m", "5m", "15m", "1h"]
        tf_idx = tf_options.index(_SS.get("bt_timeframe", "1")) if _SS.get("bt_timeframe", "1") in tf_options else 0
        selected_tf = st.selectbox("Timeframe", tf_labels, index=tf_idx, key="bt_tf_sel")
        _SS["bt_timeframe"] = tf_options[tf_labels.index(selected_tf)]

    # Time range filter
    c4, c5 = st.columns(2)
    with c4:
        time_from = st.time_input("From", value=pd.Timestamp("09:15").time(), key="bt_time_from")
    with c5:
        time_to = st.time_input("To", value=pd.Timestamp("15:30").time(), key="bt_time_to")

    st.markdown(section_header("LEG CONFIGURATION"), unsafe_allow_html=True)
    legs = _build_bt_legs()

    if st.button("📊 Run Backtest", key="bt_run", use_container_width=True):
        if not legs:
            st.warning("Add valid legs first.")
            return
        _run_backtest(legs, bt_date, _SS["bt_timeframe"], time_from, time_to)


def _run_backtest(legs, bt_date, timeframe, time_from, time_to):
    """Execute backtest and display results."""
    date_str = bt_date.strftime("%Y-%m-%d") if hasattr(bt_date, "strftime") else str(bt_date)

    all_candles = {}
    with st.spinner("Fetching historical data..."):
        for leg in legs:
            df = get_candles(
                leg["symbol"],
                resolution=timeframe,
                range_from=date_str,
                range_to=date_str,
            )
            if not df.empty:
                # Apply time filter
                df = df[
                    (df["timestamp"].dt.time >= time_from) &
                    (df["timestamp"].dt.time <= time_to)
                ]
                all_candles[leg["symbol"]] = df

    if not all_candles:
        st.warning("No historical data available for the selected date. Try a recent trading day.")
        return

    # Merge into spread OHLCV
    first_sym = legs[0]["symbol"]
    if first_sym not in all_candles:
        st.warning("No data for first leg.")
        return

    base = all_candles[first_sym][["timestamp"]].copy()
    spread_df = base.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        spread_df[col] = 0.0

    for leg in legs:
        sym = leg["symbol"]
        if sym not in all_candles:
            continue
        ldf = all_candles[sym].copy()
        mult = leg["ratio"] * leg["lot_size"]
        sign = 1 if leg["buy_sell"] == "Buy" else -1

        merged = spread_df.merge(ldf, on="timestamp", how="left", suffixes=("", "_l"))
        for col in ["open", "high", "low", "close"]:
            lcol = f"{col}_l"
            if lcol in merged.columns:
                spread_df[col] = spread_df[col] + merged[lcol].fillna(0) * mult * sign
        if "volume_l" in merged.columns:
            spread_df["volume"] = spread_df["volume"] + merged["volume_l"].fillna(0)

    if spread_df.empty:
        st.warning("No combined data available.")
        return

    # Day stats
    day_open = spread_df["open"].iloc[0]
    day_close = spread_df["close"].iloc[-1]
    day_high = spread_df["high"].max()
    day_low = spread_df["low"].min()
    day_change = day_close - day_open
    day_change_pct = (day_change / abs(day_open) * 100) if day_open != 0 else 0

    render_stat_row([
        ("OPEN", f"₹{day_open:,.2f}", C_MUTED),
        ("CLOSE", f"₹{day_close:,.2f}", C_TEXT),
        ("HIGH", f"₹{day_high:,.2f}", C_GREEN),
        ("LOW", f"₹{day_low:,.2f}", C_RED),
        ("CHANGE", f"₹{day_change:,.2f} ({day_change_pct:+.1f}%)",
         C_GREEN if day_change >= 0 else C_RED),
    ])

    # Chart
    fig = go.Figure()

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=spread_df["timestamp"],
        open=spread_df["open"], high=spread_df["high"],
        low=spread_df["low"], close=spread_df["close"],
        increasing_line_color=C_GREEN,
        decreasing_line_color=C_RED,
        name="Spread",
    ))

    # Day high/low lines
    fig.add_hline(y=day_high, line_dash="dot", line_color=C_GREEN, line_width=1,
                  annotation_text=f"High: ₹{day_high:,.2f}")
    fig.add_hline(y=day_low, line_dash="dot", line_color=C_RED, line_width=1,
                  annotation_text=f"Low: ₹{day_low:,.2f}")
    fig.add_hline(y=0, line_dash="dash", line_color=C_MUTED, line_width=1)

    layout = dark_chart_layout(
        title=f"Backtest — {date_str}",
        height=550,
        yaxis_title="₹",
    )
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, key="bt_chart")

    # Data table
    with st.expander("📋 Candle Data"):
        st.dataframe(spread_df, use_container_width=True)

    # Export buttons
    st.markdown(section_header("EXPORT"), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        buf = io.BytesIO()
        spread_df.to_excel(buf, index=False, engine="openpyxl")
        st.download_button(
            "📥 Export Excel",
            data=buf.getvalue(),
            file_name=f"backtest_{date_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="bt_export_xlsx",
        )
    with c2:
        csv = spread_df.to_csv(index=False)
        st.download_button(
            "📥 Export CSV",
            data=csv,
            file_name=f"backtest_{date_str}.csv",
            mime="text/csv",
            key="bt_export_csv",
        )
