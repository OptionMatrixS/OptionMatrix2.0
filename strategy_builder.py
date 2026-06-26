"""
strategy_builder.py — Tab 7: Strategy Builder
2–10 legs with independent Index/Expiry, strategy presets, payoff chart, P&L simulation.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from fyers_client import (
    LOT_SIZES, get_expiries, get_strikes, build_symbol_from_label,
    get_quotes, get_spot_price, bs_price, bs_greeks, implied_vol,
    time_to_expiry_years, dark_chart_layout, RISK_FREE_RATE, LEG_COLORS,
)
from styles import (
    section_header, render_stat_row, render_stat_row_small, leg_badge,
    C_GREEN, C_RED, C_BLUE, C_ORANGE, C_MUTED, C_TEXT, C_PANEL, C_BORDER,
)

PRESETS = [
    "Custom",
    "Bull Call Spread",
    "Bear Put Spread",
    "Long Straddle",
    "Short Straddle",
    "Long Strangle",
    "Short Strangle",
    "Iron Condor",
    "Bull Put Spread",
    "Bear Call Spread",
    "Long Butterfly",
]


def _apply_preset(preset, num_legs):
    """Apply strategy preset to session state."""
    _SS = st.session_state
    if preset == "Custom":
        return

    configs = {
        "Bull Call Spread": [
            {"buy_sell": "Buy", "opt_type": "CE"},
            {"buy_sell": "Sell", "opt_type": "CE"},
        ],
        "Bear Put Spread": [
            {"buy_sell": "Buy", "opt_type": "PE"},
            {"buy_sell": "Sell", "opt_type": "PE"},
        ],
        "Long Straddle": [
            {"buy_sell": "Buy", "opt_type": "CE"},
            {"buy_sell": "Buy", "opt_type": "PE"},
        ],
        "Short Straddle": [
            {"buy_sell": "Sell", "opt_type": "CE"},
            {"buy_sell": "Sell", "opt_type": "PE"},
        ],
        "Long Strangle": [
            {"buy_sell": "Buy", "opt_type": "CE"},
            {"buy_sell": "Buy", "opt_type": "PE"},
        ],
        "Short Strangle": [
            {"buy_sell": "Sell", "opt_type": "CE"},
            {"buy_sell": "Sell", "opt_type": "PE"},
        ],
        "Iron Condor": [
            {"buy_sell": "Buy", "opt_type": "PE"},
            {"buy_sell": "Sell", "opt_type": "PE"},
            {"buy_sell": "Sell", "opt_type": "CE"},
            {"buy_sell": "Buy", "opt_type": "CE"},
        ],
        "Bull Put Spread": [
            {"buy_sell": "Sell", "opt_type": "PE"},
            {"buy_sell": "Buy", "opt_type": "PE"},
        ],
        "Bear Call Spread": [
            {"buy_sell": "Sell", "opt_type": "CE"},
            {"buy_sell": "Buy", "opt_type": "CE"},
        ],
        "Long Butterfly": [
            {"buy_sell": "Buy", "opt_type": "CE"},
            {"buy_sell": "Sell", "opt_type": "CE"},
            {"buy_sell": "Sell", "opt_type": "CE"},
            {"buy_sell": "Buy", "opt_type": "CE"},
        ],
    }

    template = configs.get(preset, [])
    for i, cfg in enumerate(template):
        leg_num = i + 1
        for k, v in cfg.items():
            _SS[f"strat_leg{leg_num}_{k}"] = v


def _build_strat_legs():
    """Build strategy leg inputs. Each leg has independent Index & Expiry."""
    _SS = st.session_state
    num_legs = _SS.get("strat_num_legs", 2)
    legs = []

    for i in range(num_legs):
        leg_num = i + 1
        st.markdown(leg_badge(leg_num), unsafe_allow_html=True)
        c1, c2, c3, c4, c5, c6 = st.columns([1.2, 1.5, 1, 1, 1, 0.8])

        with c1:
            idx = st.selectbox("Index", ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY"],
                               key=f"strat_leg{leg_num}_index")
        with c2:
            expiries = get_expiries(idx)
            exp = st.selectbox("Expiry", expiries if expiries else ["Loading..."],
                               key=f"strat_leg{leg_num}_expiry")
        with c3:
            buy_sell = st.selectbox("Side", ["Buy", "Sell"],
                                    key=f"strat_leg{leg_num}_buy_sell")
        with c4:
            opt_type = st.selectbox("Type", ["CE", "PE"],
                                    key=f"strat_leg{leg_num}_opt_type")
        with c5:
            strikes = get_strikes(idx, exp) if exp and exp != "Loading..." else []
            strike = st.selectbox("Strike", strikes if strikes else [0],
                                  key=f"strat_leg{leg_num}_strike")
        with c6:
            lots = st.number_input("Lots", min_value=1, max_value=100, value=1,
                                   key=f"strat_leg{leg_num}_lots")

        if exp and exp != "Loading..." and strike and strike != 0:
            sym = build_symbol_from_label(idx, exp, opt_type, strike)
            lot_size = LOT_SIZES.get(idx, 1)
            qty = lots * lot_size

            # Fetch premium
            q = get_quotes([sym])
            ltp = q.get(sym, {}).get("ltp", 0)

            # Editable premium
            premium = st.number_input(
                f"L{leg_num} Premium", value=float(ltp), step=0.05,
                format="%.2f", key=f"strat_leg{leg_num}_premium",
                label_visibility="collapsed",
            )

            # Compute IV and Delta inline
            spot = get_spot_price(idx)
            T = time_to_expiry_years(exp)
            iv_val = 0.0
            delta = 0.0
            if spot > 0 and premium > 0 and T > 0:
                iv_val = implied_vol(premium, spot, strike, T, RISK_FREE_RATE, opt_type)
                sigma = iv_val / 100.0
                g = bs_greeks(spot, strike, T, RISK_FREE_RATE, sigma, opt_type)
                delta = g["delta"]

            color = C_GREEN if buy_sell == "Buy" else C_RED
            st.markdown(
                f'<span style="font-size:11px;color:{color};">₹{premium:.2f} | '
                f'IV: {iv_val:.1f}% | Δ: {delta:.3f}</span>',
                unsafe_allow_html=True,
            )

            legs.append({
                "leg_num": leg_num,
                "index": idx,
                "expiry": exp,
                "opt_type": opt_type,
                "buy_sell": buy_sell,
                "strike": strike,
                "lots": lots,
                "lot_size": lot_size,
                "qty": qty,
                "premium": premium,
                "symbol": sym,
                "iv": iv_val,
                "delta": delta,
                "spot": spot,
                "T": T,
            })

    return legs


def _compute_payoff(legs, spot_range):
    """Compute payoff at expiry for a range of spot prices."""
    payoffs = np.zeros(len(spot_range))

    for leg in legs:
        strike = leg["strike"]
        premium = leg["premium"]
        qty = leg["qty"]
        sign = 1 if leg["buy_sell"] == "Buy" else -1
        opt_type = leg["opt_type"]

        for j, spot in enumerate(spot_range):
            if opt_type == "CE":
                intrinsic = max(0, spot - strike)
            else:
                intrinsic = max(0, strike - spot)

            leg_pnl = (intrinsic - premium) * qty * sign
            payoffs[j] += leg_pnl

    return payoffs


def render_strategy():
    """Main render function for Strategy Builder tab."""
    _SS = st.session_state

    st.markdown(
        '<div style="font-size:20px;font-weight:600;color:#d1d4dc;padding:4px 0;">🏗️ Strategy Builder</div>',
        unsafe_allow_html=True,
    )

    # Controls
    c1, c2 = st.columns(2)
    with c1:
        num_legs = st.selectbox(
            "Number of Legs", list(range(2, 11)),
            index=list(range(2, 11)).index(_SS.get("strat_num_legs", 2)),
            key="strat_num_legs_sel",
        )
        _SS["strat_num_legs"] = num_legs
    with c2:
        preset = st.selectbox("Strategy Preset", PRESETS, key="strat_preset_sel")
        if preset != "Custom" and preset != _SS.get("_last_preset"):
            _apply_preset(preset, num_legs)
            _SS["_last_preset"] = preset
            _SS["strat_num_legs"] = max(num_legs, len(_get_preset_legs(preset)))

    st.markdown(section_header("LEG CONFIGURATION"), unsafe_allow_html=True)
    legs = _build_strat_legs()

    if not legs:
        return

    if st.button("📊 Build Strategy", key="strat_build", use_container_width=True):
        _build_strategy(legs)


def _get_preset_legs(preset):
    """Get number of legs for a preset."""
    counts = {
        "Bull Call Spread": 2, "Bear Put Spread": 2,
        "Long Straddle": 2, "Short Straddle": 2,
        "Long Strangle": 2, "Short Strangle": 2,
        "Iron Condor": 4, "Bull Put Spread": 2,
        "Bear Call Spread": 2, "Long Butterfly": 4,
    }
    return [None] * counts.get(preset, 2)


def _build_strategy(legs):
    """Build and display strategy analysis."""
    # Reference spot (use first leg's index)
    ref_spot = legs[0].get("spot", 0)
    if ref_spot <= 0:
        ref_spot = get_spot_price(legs[0]["index"])

    if ref_spot <= 0:
        st.warning("Could not determine spot price.")
        return

    # Spot range ±20%
    spot_min = ref_spot * 0.80
    spot_max = ref_spot * 1.20
    spot_range = np.linspace(spot_min, spot_max, 500)

    payoffs = _compute_payoff(legs, spot_range)

    # Find breakevens
    breakevens = []
    for j in range(1, len(payoffs)):
        if payoffs[j - 1] * payoffs[j] < 0:
            # Linear interpolation
            x = spot_range[j - 1] + (0 - payoffs[j - 1]) * (spot_range[j] - spot_range[j - 1]) / (payoffs[j] - payoffs[j - 1])
            breakevens.append(round(x, 2))

    max_profit = payoffs.max()
    max_loss = payoffs.min()
    net_premium = sum(
        leg["premium"] * leg["qty"] * (1 if leg["buy_sell"] == "Buy" else -1)
        for leg in legs
    )

    # Summary chips
    st.markdown(section_header("STRATEGY SUMMARY"), unsafe_allow_html=True)
    max_profit_str = f"₹{max_profit:,.0f}" if max_profit < 1e8 else "Unlimited"
    max_loss_str = f"₹{max_loss:,.0f}" if abs(max_loss) < 1e8 else "Unlimited"
    be_str = " / ".join([f"{b:,.0f}" for b in breakevens]) if breakevens else "N/A"

    render_stat_row([
        ("NET PREMIUM", f"₹{net_premium:,.0f}", C_GREEN if net_premium >= 0 else C_RED),
        ("MAX PROFIT", max_profit_str, C_GREEN),
        ("MAX LOSS", max_loss_str, C_RED),
        ("BREAKEVENS", be_str, C_ORANGE),
    ])

    # Payoff chart
    st.markdown(section_header("PAYOFF DIAGRAM"), unsafe_allow_html=True)

    fig = go.Figure()

    # Positive fill (green)
    pos_y = np.where(payoffs >= 0, payoffs, 0)
    fig.add_trace(go.Scatter(
        x=spot_range, y=pos_y,
        fill="tozeroy", fillcolor="rgba(38,166,154,0.2)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))

    # Negative fill (red)
    neg_y = np.where(payoffs <= 0, payoffs, 0)
    fig.add_trace(go.Scatter(
        x=spot_range, y=neg_y,
        fill="tozeroy", fillcolor="rgba(239,83,80,0.2)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))

    # Payoff line
    fig.add_trace(go.Scatter(
        x=spot_range, y=payoffs,
        mode="lines",
        line=dict(color=C_TEXT, width=2),
        name="Payoff",
        hovertemplate="Spot: %{x:,.0f}<br>P&L: ₹%{y:,.0f}<extra></extra>",
    ))

    # Zero line
    fig.add_hline(y=0, line_dash="solid", line_color=C_MUTED, line_width=1)

    # Spot price marker
    fig.add_vline(x=ref_spot, line_dash="dash", line_color="#787b86", line_width=1,
                  annotation_text=f"Spot: {ref_spot:,.0f}")

    # Breakeven lines
    for be in breakevens:
        fig.add_vline(x=be, line_dash="dash", line_color=C_ORANGE, line_width=1,
                      annotation_text=f"BE: {be:,.0f}")

    layout = dark_chart_layout(title="Payoff at Expiry", height=500, yaxis_title="P&L (₹)")
    layout["xaxis"]["title"] = "Spot Price"
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, key="strat_payoff_chart")

    # Net Greeks
    st.markdown(section_header("NET GREEKS"), unsafe_allow_html=True)
    net_d = sum(leg["delta"] * leg["qty"] * (1 if leg["buy_sell"] == "Buy" else -1) for leg in legs)
    net_g = 0.0
    net_v = 0.0
    net_t = 0.0
    for leg in legs:
        spot = leg.get("spot", ref_spot)
        T = leg.get("T", 0)
        if spot > 0 and T > 0 and leg["iv"] > 0:
            sigma = leg["iv"] / 100.0
            g = bs_greeks(spot, leg["strike"], T, RISK_FREE_RATE, sigma, leg["opt_type"])
            sign = 1 if leg["buy_sell"] == "Buy" else -1
            net_g += g["gamma"] * leg["qty"] * sign
            net_v += g["vega"] * leg["qty"] * sign
            net_t += g["theta"] * leg["qty"] * sign

    render_stat_row([
        ("NET DELTA", f"{net_d:,.2f}", C_BLUE),
        ("NET GAMMA", f"{net_g:,.4f}", C_GREEN),
        ("NET VEGA", f"{net_v:,.2f}", "#9c27b0"),
        ("NET THETA", f"{net_t:,.2f}", C_RED),
    ])

    # P&L simulation table (−10% to +10%)
    st.markdown(section_header("P&L SIMULATION"), unsafe_allow_html=True)
    sim_moves = np.arange(-10, 11, 1)
    sim_spots = ref_spot * (1 + sim_moves / 100.0)
    sim_payoffs = _compute_payoff(legs, sim_spots)

    sim_df = pd.DataFrame({
        "Move %": [f"{m:+d}%" for m in sim_moves],
        "Spot": [f"{s:,.0f}" for s in sim_spots],
        "P&L": [round(p, 0) for p in sim_payoffs],
    })
    st.dataframe(sim_df, use_container_width=True, height=400)

    # Leg summary table
    st.markdown(section_header("LEG DETAILS"), unsafe_allow_html=True)
    leg_rows = []
    for leg in legs:
        sign = 1 if leg["buy_sell"] == "Buy" else -1
        leg_rows.append({
            "Leg": leg["leg_num"],
            "Index": leg["index"],
            "Strike": leg["strike"],
            "Type": leg["opt_type"],
            "Side": leg["buy_sell"],
            "Qty": leg["qty"],
            "Premium": f"₹{leg['premium']:.2f}",
            "IV%": f"{leg['iv']:.1f}",
            "Delta": f"{leg['delta']:.3f}",
            "Cost": f"₹{leg['premium'] * leg['qty'] * sign:,.0f}",
        })
    st.dataframe(pd.DataFrame(leg_rows), use_container_width=True)
