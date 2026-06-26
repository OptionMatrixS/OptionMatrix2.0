"""
spread_chart.py — Tab 1: Spread Chart + Safety Calculator
Live feed with st.rerun() pattern, historical candles, Greeks, safety table.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import io

from fyers_client import (
    LOT_SIZES, INDEX_SYMBOLS, LEG_COLORS, get_expiries, get_strikes,
    build_symbol_from_label, get_quotes, get_candles, get_spread_value,
    compute_spread_value, bs_greeks, implied_vol, time_to_expiry_years,
    get_spot_price, dark_chart_layout, get_ist_now, is_market_open,
    RISK_FREE_RATE,
)
from styles import (
    section_header, stat_chip, leg_badge, render_stat_row,
    C_GREEN, C_RED, C_BLUE, C_ORANGE, C_MUTED, C_TEXT, C_PANEL, C_BORDER,
)

REFRESH_INTERVAL = 3  # seconds


def _build_legs():
    """Build and render leg inputs. Returns list of valid leg dicts."""
    _SS = st.session_state
    num_legs = _SS.get("sp_num_legs", 2)

    legs = []
    cols = st.columns(num_legs)

    for i in range(num_legs):
        leg_num = i + 1
        with cols[i]:
            st.markdown(leg_badge(leg_num), unsafe_allow_html=True)

            idx = st.selectbox(
                "Index",
                ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY"],
                key=f"sp_leg{leg_num}_index",
            )

            expiries = get_expiries(idx)
            exp = st.selectbox(
                "Expiry",
                expiries if expiries else ["Loading..."],
                key=f"sp_leg{leg_num}_expiry",
            )

            strikes = get_strikes(idx, exp) if exp and exp != "Loading..." else []
            strike = st.selectbox(
                "Strike",
                strikes if strikes else [0],
                key=f"sp_leg{leg_num}_strike",
            )

            c1, c2 = st.columns(2)
            with c1:
                opt_type = st.selectbox(
                    "Type", ["CE", "PE"], key=f"sp_leg{leg_num}_opt_type"
                )
            with c2:
                buy_sell = st.selectbox(
                    "Side", ["Buy", "Sell"], key=f"sp_leg{leg_num}_buy_sell"
                )

            ratio = st.number_input(
                "Ratio", min_value=1, max_value=10, value=1,
                key=f"sp_leg{leg_num}_ratio",
            )

            # Build symbol and show LTP inline
            if exp and exp != "Loading..." and strike and strike != 0:
                sym = build_symbol_from_label(idx, exp, opt_type, strike)
                q = get_quotes([sym])
                ltp = q.get(sym, {}).get("ltp", 0)
                lot = LOT_SIZES.get(idx, 1)
                net = ltp * ratio * lot * (1 if buy_sell == "Buy" else -1)
                color = C_GREEN if buy_sell == "Buy" else C_RED
                st.markdown(
                    f'<div style="font-size:12px;color:{color};">LTP: ₹{ltp:.2f} | Net: ₹{net:.2f}</div>',
                    unsafe_allow_html=True,
                )
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
                    "ltp": ltp,
                })

    return legs


def _render_live_feed(legs):
    """Live feed sub-tab with st.rerun() pattern."""
    _SS = st.session_state

    st.markdown(section_header("LIVE SPREAD FEED"), unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("▶️ Start", key="sp_live_start", use_container_width=True):
            _SS["sp_live_on"] = True
            _SS["sp_last_tick"] = 0
            st.rerun()
    with c2:
        if st.button("⏹️ Stop", key="sp_live_stop", use_container_width=True):
            _SS["sp_live_on"] = False
    with c3:
        if st.button("🗑️ Clear", key="sp_live_clear", use_container_width=True):
            _SS["sp_live_on"] = False
            _SS["sp_live_hist"] = []

    # Status badge
    hist = _SS.get("sp_live_hist", [])
    if hist:
        last_ts = hist[-1][0]
        ts_str = last_ts.strftime("%H:%M:%S") if hasattr(last_ts, "strftime") else str(last_ts)
        st.markdown(
            f'<div style="background:{C_PANEL};border:1px solid {C_BORDER};border-radius:4px;'
            f'padding:6px 12px;display:inline-block;font-size:12px;color:{C_MUTED};">'
            f'Ticks: {len(hist)} | Last: {ts_str} IST</div>',
            unsafe_allow_html=True,
        )

    # Current spread value
    if legs:
        val, err = get_spread_value(legs)
        color = C_GREEN if val >= 0 else C_RED
        st.markdown(
            f'<div style="font-size:32px;font-weight:700;color:{color};text-align:center;'
            f'padding:12px 0;">SPREAD: ₹{val:,.2f}</div>',
            unsafe_allow_html=True,
        )

    # Chart
    if hist:
        df = pd.DataFrame(hist, columns=["time", "value"])
        chart_type = _SS.get("sp_chart_type", "Line")

        fig = go.Figure()
        if chart_type == "Line":
            fig.add_trace(go.Scatter(
                x=df["time"], y=df["value"],
                mode="lines",
                line=dict(color=C_BLUE, width=2),
                name="Spread",
                fill="tozeroy",
                fillcolor="rgba(41,98,255,0.1)",
            ))
        else:
            # Resample to 1-minute OHLC for candlestick
            df = df.set_index("time")
            ohlc = df["value"].resample("1min").ohlc().dropna()
            if not ohlc.empty:
                fig.add_trace(go.Candlestick(
                    x=ohlc.index,
                    open=ohlc["open"], high=ohlc["high"],
                    low=ohlc["low"], close=ohlc["close"],
                    increasing_line_color=C_GREEN,
                    decreasing_line_color=C_RED,
                    name="Spread",
                ))

        # Zero line
        fig.add_hline(y=0, line_dash="dash", line_color=C_MUTED, line_width=1)

        layout = dark_chart_layout(title="Live Spread", height=450, yaxis_title="₹")
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, key="sp_live_chart")

    # Live feed cycle
    if _SS.get("sp_live_on") and legs:
        val, err = get_spread_value(legs)
        ts = get_ist_now()
        if not _SS.get("sp_live_hist"):
            _SS["sp_live_hist"] = []
        _SS["sp_live_hist"].append((ts, val))

        remaining = REFRESH_INTERVAL - (time.time() - _SS.get("sp_last_tick", 0))
        if remaining > 0:
            time.sleep(remaining)
        _SS["sp_last_tick"] = time.time()
        st.rerun()


def _render_historical(legs):
    """Historical candles sub-tab."""
    _SS = st.session_state

    st.markdown(section_header("HISTORICAL CANDLES"), unsafe_allow_html=True)

    if not is_market_open():
        st.info("📊 Historical candle data is only available during market hours (9:15–15:30 IST). The chart will show today's data when market opens.")

    timeframe = _SS.get("sp_timeframe", "1")

    if st.button("📊 Calculate & Plot", key="sp_hist_calc", use_container_width=True):
        if not legs:
            st.warning("Add valid legs first.")
            return

        today = get_ist_now().strftime("%Y-%m-%d")
        all_candles = {}

        with st.spinner("Fetching candle data..."):
            for leg in legs:
                df = get_candles(leg["symbol"], resolution=timeframe, range_from=today, range_to=today)
                if not df.empty:
                    all_candles[leg["symbol"]] = df

        if not all_candles:
            st.warning("No candle data available. Market may be closed.")
            return

        # Merge candles into spread OHLCV
        # Use timestamps from the first leg as base
        first_sym = legs[0]["symbol"]
        if first_sym not in all_candles:
            st.warning("No data for first leg.")
            return

        base_df = all_candles[first_sym][["timestamp"]].copy()
        spread_df = base_df.copy()
        spread_df["open"] = 0.0
        spread_df["high"] = 0.0
        spread_df["low"] = 0.0
        spread_df["close"] = 0.0
        spread_df["volume"] = 0

        for leg in legs:
            sym = leg["symbol"]
            if sym not in all_candles:
                continue
            ldf = all_candles[sym].copy()
            mult = leg["ratio"] * leg["lot_size"]
            sign = 1 if leg["buy_sell"] == "Buy" else -1

            merged = spread_df.merge(ldf, on="timestamp", how="left", suffixes=("", "_leg"))
            for col in ["open", "high", "low", "close"]:
                leg_col = f"{col}_leg" if f"{col}_leg" in merged.columns else col
                if leg_col in merged.columns:
                    spread_df[col] = spread_df[col] + merged[leg_col].fillna(0) * mult * sign
            if "volume_leg" in merged.columns:
                spread_df["volume"] = spread_df["volume"] + merged["volume_leg"].fillna(0)

        chart_type = _SS.get("sp_chart_type", "Line")
        fig = go.Figure()

        if chart_type == "Candlestick":
            fig.add_trace(go.Candlestick(
                x=spread_df["timestamp"],
                open=spread_df["open"], high=spread_df["high"],
                low=spread_df["low"], close=spread_df["close"],
                increasing_line_color=C_GREEN,
                decreasing_line_color=C_RED,
                name="Spread",
            ))
        else:
            fig.add_trace(go.Scatter(
                x=spread_df["timestamp"], y=spread_df["close"],
                mode="lines", line=dict(color=C_BLUE, width=2),
                name="Spread",
                fill="tozeroy",
                fillcolor="rgba(41,98,255,0.1)",
            ))

        fig.add_hline(y=0, line_dash="dash", line_color=C_MUTED, line_width=1)
        layout = dark_chart_layout(title="Historical Spread", height=500, yaxis_title="₹")
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, key="sp_hist_chart")

        # Data table
        with st.expander("📋 Candle Data"):
            st.dataframe(spread_df, use_container_width=True)


def _render_summary(legs):
    """Render summary chips below chart."""
    if not legs:
        return

    st.markdown(section_header("SUMMARY"), unsafe_allow_html=True)

    syms = [lg["symbol"] for lg in legs]
    quotes = get_quotes(syms)

    spread_val = compute_spread_value(legs, quotes)
    net_premium = sum(
        quotes.get(lg["symbol"], {}).get("ltp", 0) * lg["ratio"] * lg["lot_size"]
        * (1 if lg["buy_sell"] == "Buy" else -1)
        for lg in legs
    )

    # Simple max profit/loss estimation
    buy_premium = sum(
        quotes.get(lg["symbol"], {}).get("ltp", 0) * lg["ratio"] * lg["lot_size"]
        for lg in legs if lg["buy_sell"] == "Buy"
    )
    sell_premium = sum(
        quotes.get(lg["symbol"], {}).get("ltp", 0) * lg["ratio"] * lg["lot_size"]
        for lg in legs if lg["buy_sell"] == "Sell"
    )

    chips = [
        ("SPREAD", f"₹{spread_val:,.2f}", C_GREEN if spread_val >= 0 else C_RED),
        ("NET PREMIUM", f"₹{net_premium:,.2f}", C_GREEN if net_premium >= 0 else C_RED),
        ("BUY PREMIUM", f"₹{buy_premium:,.2f}", C_BLUE),
        ("SELL PREMIUM", f"₹{sell_premium:,.2f}", C_ORANGE),
    ]
    render_stat_row(chips)


def _render_greeks(legs):
    """Render net Greeks section."""
    _SS = st.session_state
    if not _SS.get("sp_show_greeks"):
        return
    if not legs:
        return

    st.markdown(section_header("NET GREEKS"), unsafe_allow_html=True)

    net_delta = 0.0
    net_gamma = 0.0
    net_vega = 0.0
    net_theta = 0.0
    net_iv = 0.0
    iv_count = 0

    for leg in legs:
        idx = leg["index"]
        spot = get_spot_price(idx)
        if spot <= 0:
            continue

        T = time_to_expiry_years(leg["expiry"])
        ltp = leg.get("ltp", 0)
        strike = leg["strike"]
        opt_type = leg["opt_type"]
        ratio = leg["ratio"]
        lot = leg["lot_size"]
        sign = 1 if leg["buy_sell"] == "Buy" else -1

        if ltp > 0 and T > 0:
            iv = implied_vol(ltp, spot, strike, T, RISK_FREE_RATE, opt_type)
            sigma = iv / 100.0
            greeks = bs_greeks(spot, strike, T, RISK_FREE_RATE, sigma, opt_type)

            net_delta += greeks["delta"] * ratio * lot * sign
            net_gamma += greeks["gamma"] * ratio * lot * sign
            net_vega += greeks["vega"] * ratio * lot * sign
            net_theta += greeks["theta"] * ratio * lot * sign
            net_iv += iv
            iv_count += 1

    avg_iv = net_iv / iv_count if iv_count > 0 else 0

    chips = [
        ("NET DELTA", f"{net_delta:,.2f}", C_BLUE),
        ("NET GAMMA", f"{net_gamma:,.4f}", C_GREEN),
        ("NET VEGA", f"{net_vega:,.2f}", "#9c27b0"),
        ("NET THETA", f"{net_theta:,.2f}", C_RED),
        ("AVG IV", f"{avg_iv:.1f}%", C_ORANGE),
    ]
    render_stat_row(chips)


def _render_safety_calculator(legs):
    """Safety Calculator embedded below chart."""
    _SS = st.session_state

    st.markdown(section_header("SAFETY CALCULATOR"), unsafe_allow_html=True)

    if not legs:
        st.info("Add legs above to use the Safety Calculator.")
        return

    # Per-leg interval inputs
    intervals = []
    cols = st.columns(len(legs))
    for i, leg in enumerate(legs):
        with cols[i]:
            default_int = 500 if leg["index"] == "SENSEX" else 100
            interval = st.number_input(
                f"L{leg['leg_num']} Interval",
                min_value=1, value=default_int,
                key=f"sp_safety_int_{leg['leg_num']}",
            )
            intervals.append(interval)

    rows_above_below = st.number_input(
        "Rows Above/Below", min_value=1, max_value=10, value=3,
        key="sp_safety_rows",
    )

    if st.button("🔨 Build Safety Table", key="sp_safety_build", use_container_width=True):
        with st.spinner("Building safety table..."):
            _build_safety_table(legs, intervals, rows_above_below)


def _build_safety_table(legs, intervals, rows_n):
    """Build and display safety table with live prices."""
    table_rows = []

    for row_offset in range(-rows_n, rows_n + 1):
        row_data = {"SERIES": row_offset}
        symbols = []
        leg_strikes = {}

        for i, leg in enumerate(legs):
            base_strike = leg["strike"]
            interval = intervals[i]
            new_strike = base_strike + (row_offset * interval)
            leg_key = f"LEG {leg['leg_num']}"
            row_data[leg_key] = new_strike
            leg_strikes[i] = new_strike

            sym = build_symbol_from_label(
                leg["index"], leg["expiry"], leg["opt_type"], new_strike
            )
            symbols.append(sym)

        # Batch fetch quotes
        quotes = get_quotes(symbols)

        bids = []
        asks = []
        ltps = []
        for sym in symbols:
            q = quotes.get(sym, {})
            bids.append(q.get("bid", 0))
            asks.append(q.get("ask", 0))
            ltps.append(q.get("ltp", 0))

        # Compute spread LTP for the row
        spread_ltp = 0.0
        for j, leg in enumerate(legs):
            sign = 1 if leg["buy_sell"] == "Buy" else -1
            spread_ltp += ltps[j] * leg["ratio"] * leg["lot_size"] * sign

        row_data["BID"] = round(min(bids) if bids else 0, 2)
        row_data["ASK"] = round(max(asks) if asks else 0, 2)
        row_data["LTP"] = round(spread_ltp, 2)

        table_rows.append(row_data)

    df = pd.DataFrame(table_rows)

    # Style: highlight base row (SERIES=0) in blue, interval row in orange
    def highlight_rows(row):
        if row["SERIES"] == 0:
            return [f"background-color: rgba(41,98,255,0.15); color: {C_TEXT}"] * len(row)
        return [""] * len(row)

    styled = df.style.apply(highlight_rows, axis=1)
    styled = styled.format(precision=2)

    st.dataframe(df, use_container_width=True, height=400)

    # Export
    c1, c2 = st.columns(2)
    with c1:
        buf = io.BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        st.download_button(
            "📥 Export Excel",
            data=buf.getvalue(),
            file_name="safety_table.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="sp_safety_export_xlsx",
        )


def render_spread_chart():
    """Main render function for Spread Chart tab."""
    _SS = st.session_state

    st.markdown(
        '<div style="font-size:20px;font-weight:600;color:#d1d4dc;padding:4px 0;">📊 Spread Chart</div>',
        unsafe_allow_html=True,
    )

    # Top controls
    c1, c2, c3 = st.columns(3)
    with c1:
        _SS["sp_num_legs"] = st.selectbox(
            "Number of Legs", [2, 3, 4, 5, 6],
            index=[2, 3, 4, 5, 6].index(_SS.get("sp_num_legs", 2)),
            key="sp_num_legs_sel",
        )
    with c2:
        _SS["sp_chart_type"] = st.selectbox(
            "Chart Type", ["Line", "Candlestick"],
            index=["Line", "Candlestick"].index(_SS.get("sp_chart_type", "Line")),
            key="sp_chart_type_sel",
        )
    with c3:
        tf_options = ["1", "5", "15", "60"]
        tf_labels = ["1m", "5m", "15m", "1h"]
        tf_idx = tf_options.index(_SS.get("sp_timeframe", "1")) if _SS.get("sp_timeframe", "1") in tf_options else 0
        selected_tf = st.selectbox("Timeframe", tf_labels, index=tf_idx, key="sp_tf_sel")
        _SS["sp_timeframe"] = tf_options[tf_labels.index(selected_tf)]

    st.markdown(section_header("LEG CONFIGURATION"), unsafe_allow_html=True)

    # Build legs
    legs = _build_legs()

    # Chart mode tabs
    tab_live, tab_hist = st.tabs(["📡 Live Feed", "📜 Historical Candles"])
    with tab_live:
        _render_live_feed(legs)
    with tab_hist:
        _render_historical(legs)

    # Summary
    _render_summary(legs)

    # Greeks toggle
    _SS["sp_show_greeks"] = st.checkbox(
        "Show Greeks", value=_SS.get("sp_show_greeks", False), key="sp_greeks_chk"
    )
    _render_greeks(legs)

    # Safety Calculator
    st.markdown("<br>", unsafe_allow_html=True)
    _render_safety_calculator(legs)
