"""
multiplier_chart.py — Tab 2: SENSEX/NIFTY Multiplier Chart
Formula: (SENSEX_strike + SENSEX_CE_ltp − SENSEX_PE_ltp) / (NIFTY_strike + NIFTY_CE_ltp − NIFTY_PE_ltp)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from fyers_client import (
    get_expiries, get_strikes, build_symbol_from_label,
    get_quotes, get_candles, dark_chart_layout, get_ist_now, is_market_open,
)
from styles import (
    section_header, render_stat_row, C_GREEN, C_RED, C_BLUE, C_ORANGE, C_MUTED, C_TEXT,
)


def render_multiplier():
    """Main render function for Multiplier Chart tab."""
    _SS = st.session_state

    st.markdown(
        '<div style="font-size:20px;font-weight:600;color:#d1d4dc;padding:4px 0;">✖️ SENSEX / NIFTY Multiplier</div>',
        unsafe_allow_html=True,
    )

    st.markdown(section_header("SENSEX LEG"), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        sensex_expiries = get_expiries("SENSEX")
        sensex_exp = st.selectbox(
            "SENSEX Expiry", sensex_expiries if sensex_expiries else ["Loading..."],
            key="mul_sensex_exp",
        )
    with c2:
        sensex_strikes = get_strikes("SENSEX", sensex_exp) if sensex_exp and sensex_exp != "Loading..." else []
        sensex_strike = st.selectbox(
            "SENSEX Strike", sensex_strikes if sensex_strikes else [0],
            key="mul_sensex_strike",
        )

    st.markdown(section_header("NIFTY LEG"), unsafe_allow_html=True)
    c3, c4 = st.columns(2)
    with c3:
        nifty_expiries = get_expiries("NIFTY")
        nifty_exp = st.selectbox(
            "NIFTY Expiry", nifty_expiries if nifty_expiries else ["Loading..."],
            key="mul_nifty_exp",
        )
    with c4:
        nifty_strikes = get_strikes("NIFTY", nifty_exp) if nifty_exp and nifty_exp != "Loading..." else []
        nifty_strike = st.selectbox(
            "NIFTY Strike", nifty_strikes if nifty_strikes else [0],
            key="mul_nifty_strike",
        )

    # Timeframe
    tf_options = ["1", "5", "15", "60"]
    tf_labels = ["1m", "5m", "15m", "1h"]
    tf_idx = tf_options.index(_SS.get("mul_timeframe", "1")) if _SS.get("mul_timeframe", "1") in tf_options else 0
    selected_tf = st.selectbox("Timeframe", tf_labels, index=tf_idx, key="mul_tf_sel")
    _SS["mul_timeframe"] = tf_options[tf_labels.index(selected_tf)]

    if st.button("📊 Calculate Multiplier", key="mul_calc", use_container_width=True):
        if (not sensex_exp or sensex_exp == "Loading..." or sensex_strike == 0 or
                not nifty_exp or nifty_exp == "Loading..." or nifty_strike == 0):
            st.warning("Select valid expiry and strike for both SENSEX and NIFTY.")
            return

        _calculate_multiplier(
            sensex_exp, sensex_strike, nifty_exp, nifty_strike, _SS["mul_timeframe"]
        )


def _calculate_multiplier(sensex_exp, sensex_strike, nifty_exp, nifty_strike, timeframe):
    """Calculate and plot the multiplier chart."""
    # Build symbols
    sensex_ce = build_symbol_from_label("SENSEX", sensex_exp, "CE", sensex_strike)
    sensex_pe = build_symbol_from_label("SENSEX", sensex_exp, "PE", sensex_strike)
    nifty_ce = build_symbol_from_label("NIFTY", nifty_exp, "CE", nifty_strike)
    nifty_pe = build_symbol_from_label("NIFTY", nifty_exp, "PE", nifty_strike)

    today = get_ist_now().strftime("%Y-%m-%d")
    multiplier_data = []

    with st.spinner("Fetching data..."):
        # Try historical candles first
        candles = {}
        for sym in [sensex_ce, sensex_pe, nifty_ce, nifty_pe]:
            df = get_candles(sym, resolution=timeframe, range_from=today, range_to=today)
            if not df.empty:
                candles[sym] = df

        if len(candles) == 4:
            # Merge on timestamps
            base_ts = candles[sensex_ce]["timestamp"].values
            for ts in base_ts:
                try:
                    sce = candles[sensex_ce][candles[sensex_ce]["timestamp"] == ts]["close"].values[0]
                    spe = candles[sensex_pe][candles[sensex_pe]["timestamp"] == ts]["close"].values[0]
                    nce = candles[nifty_ce][candles[nifty_ce]["timestamp"] == ts]["close"].values[0]
                    npe = candles[nifty_pe][candles[nifty_pe]["timestamp"] == ts]["close"].values[0]

                    sensex_synth = sensex_strike + sce - spe
                    nifty_synth = nifty_strike + nce - npe

                    if nifty_synth != 0:
                        mult = sensex_synth / nifty_synth
                        multiplier_data.append({"time": pd.Timestamp(ts), "multiplier": mult})
                except (IndexError, ZeroDivisionError):
                    continue
        else:
            # Fallback: single live quote point
            quotes = get_quotes([sensex_ce, sensex_pe, nifty_ce, nifty_pe])
            sce_ltp = quotes.get(sensex_ce, {}).get("ltp", 0)
            spe_ltp = quotes.get(sensex_pe, {}).get("ltp", 0)
            nce_ltp = quotes.get(nifty_ce, {}).get("ltp", 0)
            npe_ltp = quotes.get(nifty_pe, {}).get("ltp", 0)

            sensex_synth = sensex_strike + sce_ltp - spe_ltp
            nifty_synth = nifty_strike + nce_ltp - npe_ltp

            if nifty_synth != 0:
                mult = sensex_synth / nifty_synth
                multiplier_data.append({"time": get_ist_now(), "multiplier": mult})
            else:
                st.warning("NIFTY synthetic value is zero, cannot compute multiplier.")
                return

    if not multiplier_data:
        st.warning("No data available for multiplier calculation.")
        return

    df = pd.DataFrame(multiplier_data)

    # Stats
    current = df["multiplier"].iloc[-1]
    avg_val = df["multiplier"].mean()
    high_val = df["multiplier"].max()
    low_val = df["multiplier"].min()

    render_stat_row([
        ("CURRENT", f"{current:.4f}", C_BLUE),
        ("AVERAGE", f"{avg_val:.4f}", C_MUTED),
        ("HIGH", f"{high_val:.4f}", C_GREEN),
        ("LOW", f"{low_val:.4f}", C_RED),
    ])

    # Chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["time"], y=df["multiplier"],
        mode="lines",
        line=dict(color=C_BLUE, width=2),
        name="Multiplier",
        fill="tozeroy",
        fillcolor="rgba(41,98,255,0.08)",
    ))

    # Average line
    fig.add_hline(y=avg_val, line_dash="dash", line_color=C_ORANGE, line_width=1,
                  annotation_text=f"Avg: {avg_val:.4f}")

    layout = dark_chart_layout(
        title=f"SENSEX/NIFTY Multiplier ({sensex_strike}/{nifty_strike})",
        height=500,
        yaxis_title="Multiplier",
    )
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, key="mul_chart")

    # Quote details
    with st.expander("📋 Quote Details"):
        quotes = get_quotes([sensex_ce, sensex_pe, nifty_ce, nifty_pe])
        for sym in [sensex_ce, sensex_pe, nifty_ce, nifty_pe]:
            q = quotes.get(sym, {})
            st.markdown(f"**{sym}**: LTP=₹{q.get('ltp', 0):.2f}")
