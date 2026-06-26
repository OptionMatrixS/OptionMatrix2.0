"""
position_analysis.py — Tab 6: Position Analysis
Manual position entry with P&L breakdown, Greeks analysis, and risk metrics.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from fyers_client import (
    LOT_SIZES, get_expiries, get_strikes, build_symbol_from_label,
    get_quotes, get_spot_price, bs_greeks, implied_vol,
    time_to_expiry_years, dark_chart_layout, RISK_FREE_RATE,
)
from styles import (
    section_header, render_stat_row, leg_badge, format_currency,
    C_GREEN, C_RED, C_BLUE, C_ORANGE, C_MUTED, C_TEXT, C_PANEL, C_BORDER,
)


def _render_position_row(pos_num):
    """Render one position input row."""
    prefix = f"pos_{pos_num}"
    cols = st.columns([1.5, 1.5, 1, 1, 1, 1, 1])

    with cols[0]:
        index = st.selectbox("Index", ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY"],
                             key=f"{prefix}_index")
    with cols[1]:
        expiries = get_expiries(index)
        expiry = st.selectbox("Expiry", expiries if expiries else ["Loading..."],
                              key=f"{prefix}_expiry")
    with cols[2]:
        opt_type = st.selectbox("Type", ["CE", "PE"], key=f"{prefix}_opt_type")
    with cols[3]:
        buy_sell = st.selectbox("Side", ["Buy", "Sell"], key=f"{prefix}_buy_sell")
    with cols[4]:
        strikes = get_strikes(index, expiry) if expiry and expiry != "Loading..." else []
        strike = st.selectbox("Strike", strikes if strikes else [0], key=f"{prefix}_strike")
    with cols[5]:
        lots = st.number_input("Lots", min_value=1, max_value=100, value=1,
                               key=f"{prefix}_lots")
    with cols[6]:
        entry_price = st.number_input("Entry ₹", min_value=0.0, value=0.0,
                                      step=0.05, format="%.2f", key=f"{prefix}_entry")

    if expiry and expiry != "Loading..." and strike and strike != 0:
        sym = build_symbol_from_label(index, expiry, opt_type, strike)
        lot_size = LOT_SIZES.get(index, 1)
        return {
            "pos_num": pos_num,
            "index": index,
            "expiry": expiry,
            "opt_type": opt_type,
            "buy_sell": buy_sell,
            "strike": strike,
            "lots": lots,
            "entry_price": entry_price,
            "symbol": sym,
            "lot_size": lot_size,
            "qty": lots * lot_size,
        }
    return None


def render_positions():
    """Main render function for Position Analysis tab."""
    _SS = st.session_state

    st.markdown(
        '<div style="font-size:20px;font-weight:600;color:#d1d4dc;padding:4px 0;">📂 Position Analysis</div>',
        unsafe_allow_html=True,
    )

    num_pos = st.number_input(
        "Number of Positions", min_value=1, max_value=20,
        value=_SS.get("pos_num_positions", 1),
        key="pos_num_inp",
    )
    _SS["pos_num_positions"] = num_pos

    st.markdown(section_header("POSITIONS"), unsafe_allow_html=True)

    positions = []
    for i in range(1, num_pos + 1):
        st.markdown(leg_badge(i, f"POSITION {i}"), unsafe_allow_html=True)
        pos = _render_position_row(i)
        if pos:
            positions.append(pos)

    if st.button("📊 Analyze Positions", key="pos_analyze", use_container_width=True):
        if not positions:
            st.warning("Add at least one valid position.")
            return
        _analyze_positions(positions)


def _analyze_positions(positions):
    """Analyze positions with live data."""
    # Fetch all current prices
    syms = [p["symbol"] for p in positions]
    quotes = get_quotes(syms)

    # P&L breakdown
    st.markdown(section_header("P&L BREAKDOWN"), unsafe_allow_html=True)

    total_pnl = 0.0
    total_investment = 0.0
    rows = []

    net_delta = 0.0
    net_gamma = 0.0
    net_vega = 0.0
    net_theta = 0.0

    for pos in positions:
        q = quotes.get(pos["symbol"], {})
        ltp = q.get("ltp", 0)
        entry = pos["entry_price"]
        qty = pos["qty"]
        sign = 1 if pos["buy_sell"] == "Buy" else -1

        pnl = (ltp - entry) * qty * sign
        total_pnl += pnl
        total_investment += entry * qty

        # Greeks
        spot = get_spot_price(pos["index"])
        T = time_to_expiry_years(pos["expiry"])
        iv_val = 0.0
        delta = gamma = vega = theta = 0.0

        if spot > 0 and ltp > 0 and T > 0:
            iv_val = implied_vol(ltp, spot, pos["strike"], T, RISK_FREE_RATE, pos["opt_type"])
            sigma = iv_val / 100.0
            g = bs_greeks(spot, pos["strike"], T, RISK_FREE_RATE, sigma, pos["opt_type"])
            delta = g["delta"] * qty * sign
            gamma = g["gamma"] * qty * sign
            vega = g["vega"] * qty * sign
            theta = g["theta"] * qty * sign

        net_delta += delta
        net_gamma += gamma
        net_vega += vega
        net_theta += theta

        rows.append({
            "Position": f"P{pos['pos_num']}",
            "Symbol": pos["symbol"],
            "Side": pos["buy_sell"],
            "Qty": qty,
            "Entry": f"₹{entry:.2f}",
            "LTP": f"₹{ltp:.2f}",
            "P&L": round(pnl, 2),
            "IV%": f"{iv_val:.1f}",
            "Delta": round(delta, 2),
            "Theta": round(theta, 2),
        })

    # Summary stats
    pnl_pct = (total_pnl / total_investment * 100) if total_investment > 0 else 0
    render_stat_row([
        ("TOTAL P&L", f"₹{total_pnl:,.2f}", C_GREEN if total_pnl >= 0 else C_RED),
        ("P&L %", f"{pnl_pct:+.2f}%", C_GREEN if pnl_pct >= 0 else C_RED),
        ("INVESTMENT", f"₹{total_investment:,.2f}", C_MUTED),
    ])

    # Position table
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    # Net Greeks
    st.markdown(section_header("NET GREEKS"), unsafe_allow_html=True)
    render_stat_row([
        ("NET DELTA", f"{net_delta:,.2f}", C_BLUE),
        ("NET GAMMA", f"{net_gamma:,.4f}", C_GREEN),
        ("NET VEGA", f"{net_vega:,.2f}", "#9c27b0"),
        ("NET THETA", f"{net_theta:,.2f}", C_RED),
    ])

    # P&L by position bar chart
    st.markdown(section_header("P&L DISTRIBUTION"), unsafe_allow_html=True)
    pnl_vals = [r["P&L"] for r in rows]
    labels = [r["Position"] for r in rows]
    colors = [C_GREEN if v >= 0 else C_RED for v in pnl_vals]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=pnl_vals,
        marker_color=colors,
        text=[f"₹{v:,.0f}" for v in pnl_vals],
        textposition="outside",
        textfont=dict(color=C_TEXT),
    ))

    layout = dark_chart_layout(title="P&L by Position", height=350, yaxis_title="₹")
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, key="pos_pnl_chart")
