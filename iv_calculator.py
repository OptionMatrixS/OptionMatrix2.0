"""
iv_calculator.py — Tab 3: IV Calculator
Up to 5 expiries simultaneously, multi-line IV% chart, Black-Scholes bisection.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from fyers_client import (
    get_expiries, get_strikes, build_symbol_from_label, get_candles,
    get_quotes, get_spot_price, implied_vol, time_to_expiry_years,
    dark_chart_layout, get_ist_now, is_market_open, RISK_FREE_RATE,
    INDEX_SYMBOLS, LEG_COLORS,
)
from styles import (
    section_header, render_stat_row, stat_chip_small,
    C_GREEN, C_RED, C_BLUE, C_ORANGE, C_MUTED, C_TEXT,
)

EXPIRY_COLORS = ["#2962ff", "#26a69a", "#ff9800", "#ef5350", "#9c27b0"]


def render_iv_calculator():
    """Main render function for IV Calculator tab."""
    _SS = st.session_state

    st.markdown(
        '<div style="font-size:20px;font-weight:600;color:#d1d4dc;padding:4px 0;">🌡️ IV Calculator</div>',
        unsafe_allow_html=True,
    )

    # Controls
    c1, c2, c3 = st.columns(3)
    with c1:
        index = st.selectbox(
            "Index", ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY"],
            key="iv_index_sel",
        )
        _SS["iv_index"] = index
    with c2:
        opt_type = st.selectbox("Option Type", ["CE", "PE"], key="iv_opt_type")
    with c3:
        num_exp = st.number_input(
            "Number of Expiries", min_value=1, max_value=5, value=2,
            key="iv_num_exp",
        )
        _SS["iv_num_expiries"] = num_exp

    # Strike selection
    all_expiries = get_expiries(index)
    if not all_expiries:
        st.warning(f"No expiries available for {index}. Check API connection.")
        return

    first_exp = all_expiries[0] if all_expiries else ""
    strikes = get_strikes(index, first_exp) if first_exp else []
    strike = st.selectbox("Strike Price", strikes if strikes else [0], key="iv_strike")

    st.markdown(section_header("EXPIRY SELECTION"), unsafe_allow_html=True)

    # Expiry selectors
    selected_expiries = []
    cols = st.columns(num_exp)
    for i in range(num_exp):
        with cols[i]:
            color = EXPIRY_COLORS[i % len(EXPIRY_COLORS)]
            st.markdown(
                f'<span style="color:{color};font-weight:600;">Expiry {i+1}</span>',
                unsafe_allow_html=True,
            )
            exp = st.selectbox(
                f"Expiry {i+1}",
                all_expiries,
                index=min(i, len(all_expiries) - 1),
                key=f"iv_exp_{i}",
                label_visibility="collapsed",
            )
            selected_expiries.append(exp)

    # Timeframe
    tf_options = ["1", "5", "15", "60"]
    tf_labels = ["1m", "5m", "15m", "1h"]
    selected_tf = st.selectbox("Timeframe", tf_labels, key="iv_tf")
    timeframe = tf_options[tf_labels.index(selected_tf)]

    if st.button("📊 Calculate IV", key="iv_calc", use_container_width=True):
        if strike == 0:
            st.warning("Select a valid strike price.")
            return
        _calculate_iv(index, selected_expiries, strike, opt_type, timeframe)


def _calculate_iv(index, expiries, strike, opt_type, timeframe):
    """Calculate and plot IV for multiple expiries."""
    spot = get_spot_price(index)
    if spot <= 0:
        st.warning("Could not fetch spot price. Check API connection.")
        return

    today = get_ist_now().strftime("%Y-%m-%d")
    iv_series = {}

    with st.spinner("Calculating IV across expiries..."):
        for i, exp in enumerate(expiries):
            sym = build_symbol_from_label(index, exp, opt_type, strike)
            T = time_to_expiry_years(exp)
            if T <= 0:
                continue

            # Try historical candles
            df = get_candles(sym, resolution=timeframe, range_from=today, range_to=today)
            if not df.empty:
                ivs = []
                for _, row in df.iterrows():
                    price = row["close"]
                    if price > 0:
                        iv_val = implied_vol(price, spot, strike, T, RISK_FREE_RATE, opt_type)
                        ivs.append({"time": row["timestamp"], "iv": iv_val})
                if ivs:
                    iv_series[exp] = pd.DataFrame(ivs)
            else:
                # Fallback: single live quote point
                q = get_quotes([sym])
                ltp = q.get(sym, {}).get("ltp", 0)
                if ltp > 0:
                    iv_val = implied_vol(ltp, spot, strike, T, RISK_FREE_RATE, opt_type)
                    iv_series[exp] = pd.DataFrame([
                        {"time": get_ist_now(), "iv": iv_val}
                    ])

    if not iv_series:
        st.warning("No IV data could be computed. Market may be closed or strike has no data.")
        return

    # Stat chips per expiry
    st.markdown(section_header("IV SUMMARY"), unsafe_allow_html=True)
    stat_cols = st.columns(len(iv_series))
    for idx, (exp, df) in enumerate(iv_series.items()):
        with stat_cols[idx]:
            color = EXPIRY_COLORS[idx % len(EXPIRY_COLORS)]
            current_iv = df["iv"].iloc[-1]
            high_iv = df["iv"].max()
            low_iv = df["iv"].min()
            st.markdown(
                f'<div style="font-size:11px;color:{color};font-weight:600;">{exp}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(stat_chip_small("CURRENT IV", f"{current_iv:.1f}%", color), unsafe_allow_html=True)
            st.markdown(stat_chip_small("HIGH", f"{high_iv:.1f}%", C_GREEN), unsafe_allow_html=True)
            st.markdown(stat_chip_small("LOW", f"{low_iv:.1f}%", C_RED), unsafe_allow_html=True)

    # Multi-line chart
    fig = go.Figure()
    for idx, (exp, df) in enumerate(iv_series.items()):
        color = EXPIRY_COLORS[idx % len(EXPIRY_COLORS)]
        fig.add_trace(go.Scatter(
            x=df["time"], y=df["iv"],
            mode="lines",
            line=dict(color=color, width=2),
            name=exp,
        ))

    layout = dark_chart_layout(
        title=f"IV% — {index} {strike} {opt_type}",
        height=500,
        yaxis_title="IV (%)",
    )
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, key="iv_chart")

    # Spot info
    st.markdown(
        f'<div style="color:{C_MUTED};font-size:12px;">Spot: ₹{spot:,.2f} | '
        f'Strike: {strike} | Risk-Free Rate: {RISK_FREE_RATE*100:.1f}%</div>',
        unsafe_allow_html=True,
    )
