"""
spread_tracker.py — Tab 4: Spread Tracker
Monitor 1–10 spreads simultaneously with safety tables.
"""

import streamlit as st
import pandas as pd
import io

from fyers_client import (
    LOT_SIZES, get_expiries, get_strikes, build_symbol_from_label,
    get_quotes, bs_greeks, implied_vol, time_to_expiry_years,
    get_spot_price, get_ist_now, RISK_FREE_RATE,
)
from styles import (
    section_header, render_stat_row, leg_badge,
    C_GREEN, C_RED, C_BLUE, C_ORANGE, C_MUTED, C_TEXT, C_PANEL, C_BORDER,
)


def _render_spread_config(spread_num):
    """Render configuration inputs for one spread."""
    prefix = f"trk_s{spread_num}"

    st.markdown(
        f'<div style="font-size:13px;font-weight:600;color:{C_BLUE};padding:4px 0;">'
        f'Spread #{spread_num}</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        index = st.selectbox(
            "Index", ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY"],
            key=f"{prefix}_index",
        )
    with c2:
        opt_type = st.selectbox("Type", ["CE", "PE"], key=f"{prefix}_opt_type")
    with c3:
        interval = st.number_input(
            "Strike Interval",
            min_value=1, value=500 if index == "SENSEX" else 100,
            key=f"{prefix}_interval",
        )

    expiries = get_expiries(index)
    c4, c5 = st.columns(2)
    with c4:
        buy_exp = st.selectbox(
            "Buy Expiry", expiries if expiries else ["Loading..."],
            key=f"{prefix}_buy_exp",
        )
    with c5:
        sell_exp = st.selectbox(
            "Sell Expiry", expiries if expiries else ["Loading..."],
            index=min(1, len(expiries) - 1) if len(expiries) > 1 else 0,
            key=f"{prefix}_sell_exp",
        )

    strikes_list = get_strikes(index, buy_exp) if buy_exp and buy_exp != "Loading..." else []
    c6, c7 = st.columns(2)
    with c6:
        strike1 = st.selectbox(
            "Strike 1 (Buy)", strikes_list if strikes_list else [0],
            key=f"{prefix}_strike1",
        )
    with c7:
        strike2 = st.selectbox(
            "Strike 2 (Sell)", strikes_list if strikes_list else [0],
            key=f"{prefix}_strike2",
        )

    safety_rows = st.number_input(
        "Safety Rows", min_value=1, max_value=5, value=3,
        key=f"{prefix}_safety_rows",
    )

    return {
        "index": index,
        "opt_type": opt_type,
        "interval": interval,
        "buy_exp": buy_exp,
        "sell_exp": sell_exp,
        "strike1": strike1,
        "strike2": strike2,
        "safety_rows": safety_rows,
    }


def _build_safety_table(config, show_greeks=False):
    """Build safety table for one spread."""
    index = config["index"]
    opt_type = config["opt_type"]
    interval = config["interval"]
    buy_exp = config["buy_exp"]
    sell_exp = config["sell_exp"]
    strike1 = config["strike1"]
    strike2 = config["strike2"]
    rows_n = config["safety_rows"]

    if not buy_exp or buy_exp == "Loading..." or strike1 == 0:
        return None

    table_rows = []
    for offset in range(-rows_n, rows_n + 1):
        s1 = strike1 + (offset * interval)
        s2 = strike2 + (offset * interval)

        sym1 = build_symbol_from_label(index, buy_exp, opt_type, s1)
        sym2 = build_symbol_from_label(index, sell_exp, opt_type, s2)

        quotes = get_quotes([sym1, sym2])
        q1 = quotes.get(sym1, {})
        q2 = quotes.get(sym2, {})

        ltp1 = q1.get("ltp", 0)
        ltp2 = q2.get("ltp", 0)
        spread_ltp = ltp1 - ltp2

        row = {
            "SERIES": offset,
            "LEG 1": s1,
            "LEG 2": s2,
            "BID": round(q1.get("bid", 0) - q2.get("ask", 0), 2),
            "ASK": round(q1.get("ask", 0) - q2.get("bid", 0), 2),
            "LTP": round(spread_ltp, 2),
            "PREV CLOSE": round(q1.get("prev_close", 0) - q2.get("prev_close", 0), 2),
            "HIGH": round(q1.get("high", 0), 2),
            "LOW": round(q1.get("low", 0), 2),
        }

        if show_greeks:
            spot = get_spot_price(index)
            T1 = time_to_expiry_years(buy_exp)
            T2 = time_to_expiry_years(sell_exp)
            if spot > 0 and ltp1 > 0 and T1 > 0:
                iv1 = implied_vol(ltp1, spot, s1, T1, RISK_FREE_RATE, opt_type) / 100
                g1 = bs_greeks(spot, s1, T1, RISK_FREE_RATE, iv1, opt_type)
                row["DELTA1"] = g1["delta"]
                row["THETA1"] = g1["theta"]
            if spot > 0 and ltp2 > 0 and T2 > 0:
                iv2 = implied_vol(ltp2, spot, s2, T2, RISK_FREE_RATE, opt_type) / 100
                g2 = bs_greeks(spot, s2, T2, RISK_FREE_RATE, iv2, opt_type)
                row["DELTA2"] = g2["delta"]
                row["THETA2"] = g2["theta"]

        table_rows.append(row)

    return pd.DataFrame(table_rows)


def render_spread_tracker():
    """Main render function for Spread Tracker tab."""
    _SS = st.session_state

    st.markdown(
        '<div style="font-size:20px;font-weight:600;color:#d1d4dc;padding:4px 0;">📋 Spread Tracker</div>',
        unsafe_allow_html=True,
    )

    num_spreads = st.number_input(
        "Number of Spreads", min_value=1, max_value=10, value=_SS.get("trk_num_spreads", 1),
        key="trk_num_spreads_inp",
    )
    _SS["trk_num_spreads"] = num_spreads

    show_greeks = st.checkbox("Show Greeks per row", key="trk_show_greeks")

    # Collect all spread configs
    configs = []
    for i in range(1, num_spreads + 1):
        with st.expander(f"📌 Spread #{i}", expanded=(i == 1)):
            config = _render_spread_config(i)
            configs.append(config)

    # Fetch All button
    if st.button("🔄 Fetch All", key="trk_fetch_all", use_container_width=True):
        with st.spinner("Fetching data for all spreads..."):
            for i, config in enumerate(configs):
                st.markdown(
                    f'<div style="font-size:14px;font-weight:600;color:{C_BLUE};padding:8px 0;">'
                    f'Spread #{i+1} — {config["index"]} {config["opt_type"]} '
                    f'{config["strike1"]}/{config["strike2"]}</div>',
                    unsafe_allow_html=True,
                )

                df = _build_safety_table(config, show_greeks)
                if df is not None and not df.empty:
                    # Highlight base row
                    def style_base(row):
                        if row["SERIES"] == 0:
                            return [f"background-color: rgba(41,98,255,0.15)"] * len(row)
                        return [""] * len(row)

                    st.dataframe(df, use_container_width=True, height=300)

                    # Quick stats
                    base = df[df["SERIES"] == 0]
                    if not base.empty:
                        base_ltp = base["LTP"].values[0]
                        render_stat_row([
                            ("BASE LTP", f"₹{base_ltp:.2f}", C_GREEN if base_ltp >= 0 else C_RED),
                            ("BID", f"₹{base['BID'].values[0]:.2f}", C_MUTED),
                            ("ASK", f"₹{base['ASK'].values[0]:.2f}", C_MUTED),
                        ])
                else:
                    st.info("No data available for this spread.")

                st.markdown('<hr style="border-color:#2a2e39;">', unsafe_allow_html=True)
