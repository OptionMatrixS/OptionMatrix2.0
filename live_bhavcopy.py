"""
live_bhavcopy.py — Tab 8: Live Bhavcopy
OPTIDX (index options) or OPTSTK (stock options) with filters and export.
"""

import streamlit as st
import pandas as pd
import io

from fyers_client import (
    INDEX_SYMBOLS, get_expiries, get_option_chain, get_ist_now,
)
from styles import (
    section_header, render_stat_row, C_GREEN, C_RED, C_BLUE, C_ORANGE, C_MUTED, C_TEXT,
)

# F&O stocks list (top 80)
FNO_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR",
    "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "ITC", "AXISBANK",
    "BAJFINANCE", "MARUTI", "HCLTECH", "ASIANPAINT", "SUNPHARMA",
    "TITAN", "ULTRACEMCO", "WIPRO", "NESTLEIND", "TATAMOTORS",
    "M&M", "NTPC", "POWERGRID", "ONGC", "JSWSTEEL", "TATASTEEL",
    "ADANIENT", "ADANIPORTS", "BAJAJFINSV", "TECHM", "INDUSINDBK",
    "DRREDDY", "CIPLA", "GRASIM", "APOLLOHOSP", "HEROMOTOCO",
    "EICHERMOT", "DIVISLAB", "BPCL", "COALINDIA", "BRITANNIA",
    "UPL", "SHREECEM", "SBILIFE", "HDFCLIFE", "TATACONSUM",
    "DABUR", "PIDILITIND", "GODREJCP", "HAVELLS", "SIEMENS",
    "BIOCON", "AMBUJACEM", "ACC", "DLF", "INDIGO", "PAGEIND",
    "BERGEPAINT", "MUTHOOTFIN", "CHOLAFIN", "IDFCFIRSTB",
    "BANDHANBNK", "VOLTAS", "TRENT", "JUBLFOOD", "LUPIN",
    "ATUL", "TORNTPHARM", "AUROPHARMA", "BALKRISIND", "MFSL",
    "MRF", "COFORGE", "LALPATHLAB", "METROPOLIS", "LTIM",
    "PERSISTENT", "POLYCAB", "PIIND", "ASTRAL",
]


def render_bhavcopy():
    """Main render function for Live Bhavcopy tab."""
    _SS = st.session_state

    st.markdown(
        '<div style="font-size:20px;font-weight:600;color:#d1d4dc;padding:4px 0;">📋 Live Bhavcopy</div>',
        unsafe_allow_html=True,
    )

    # Mode selection
    c1, c2 = st.columns(2)
    with c1:
        mode = st.radio("Mode", ["OPTIDX", "OPTSTK"], horizontal=True, key="bhav_mode_sel")
        _SS["bhav_mode"] = mode
    with c2:
        ce_pe_filter = st.radio("Option Type", ["All", "CE", "PE"], horizontal=True, key="bhav_ce_pe")

    if mode == "OPTIDX":
        # Index selection
        indices = st.multiselect(
            "Select Indices",
            ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY"],
            default=["NIFTY"],
            key="bhav_indices",
        )
    else:
        # Stock selection with Select All
        select_all = st.checkbox("Select All Stocks", key="bhav_select_all")
        if select_all:
            stocks = FNO_STOCKS
        else:
            stocks = st.multiselect(
                "Select Stocks", FNO_STOCKS,
                default=["RELIANCE", "TCS", "HDFCBANK"],
                key="bhav_stocks",
            )
        indices = stocks  # will be treated as symbols

    # Filters
    c3, c4 = st.columns(2)
    with c3:
        vol_filter = st.number_input("Volume >", min_value=0, value=0, step=100, key="bhav_vol")
    with c4:
        new_oi_only = st.checkbox("New OI Only (OI Change > 0)", key="bhav_new_oi")

    if st.button("🔄 Fetch Bhavcopy", key="bhav_fetch", use_container_width=True):
        targets = indices if mode == "OPTIDX" else stocks
        if not targets:
            st.warning("Select at least one index or stock.")
            return
        _fetch_bhavcopy(targets, mode, ce_pe_filter, vol_filter, new_oi_only)


def _fetch_bhavcopy(targets, mode, ce_pe_filter, vol_filter, new_oi_only):
    """Fetch and display bhavcopy data."""
    all_rows = []

    with st.spinner("Fetching option chain data..."):
        for target in targets:
            try:
                if mode == "OPTIDX":
                    resp = get_option_chain(target)
                else:
                    # Stock options
                    sym = f"NSE:{target}-EQ"
                    from fyers_client import get_fyers_client
                    fyers = get_fyers_client()
                    resp = fyers.optionchain(
                        data={"symbol": sym, "strikecount": 0, "timestamp": ""}
                    )
                    if isinstance(resp, dict) and resp.get("code") != 200:
                        continue

                chain = resp.get("data", {}).get("optionsChain", [])

                for opt in chain:
                    strike = opt.get("strikePrice", 0)
                    if isinstance(strike, str):
                        strike = float(strike.replace(",", ""))

                    opt_type = opt.get("option_type", opt.get("optionType", ""))
                    if opt_type == "call" or opt_type == "CE":
                        opt_type = "CE"
                    elif opt_type == "put" or opt_type == "PE":
                        opt_type = "PE"

                    # Apply CE/PE filter
                    if ce_pe_filter != "All" and opt_type != ce_pe_filter:
                        continue

                    ltp = opt.get("ltp", 0)
                    if ltp == 0:
                        ltp = opt.get("prev_close_price", 0)

                    volume = opt.get("volume", 0)
                    oi = opt.get("oi", opt.get("open_interest", 0))
                    oi_change = opt.get("oiChange", opt.get("oi_change", 0))
                    expiry = opt.get("expiryDate", opt.get("expiry", ""))

                    # Apply filters
                    if volume < vol_filter:
                        continue
                    if new_oi_only and oi_change <= 0:
                        continue

                    all_rows.append({
                        "Particular": target,
                        "Expiry": expiry,
                        "Strike": int(strike),
                        "Type": opt_type,
                        "Volume": volume,
                        "OI": oi,
                        "OI Change": oi_change,
                        "LTP": round(ltp, 2),
                    })
            except Exception as e:
                st.warning(f"Error fetching {target}: {e}")

    if not all_rows:
        st.warning("No data found with current filters.")
        return

    df = pd.DataFrame(all_rows)
    df = df.sort_values("Volume", ascending=False).reset_index(drop=True)

    # Stats
    total_volume = df["Volume"].sum()
    total_oi = df["OI"].sum()
    num_records = len(df)

    render_stat_row([
        ("RECORDS", f"{num_records:,}", C_BLUE),
        ("TOTAL VOLUME", f"{total_volume:,.0f}", C_GREEN),
        ("TOTAL OI", f"{total_oi:,.0f}", C_ORANGE),
    ])

    # Table
    st.dataframe(df, use_container_width=True, height=500)

    # Export
    st.markdown(section_header("EXPORT"), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        buf = io.BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        st.download_button(
            "📥 Export Excel",
            data=buf.getvalue(),
            file_name=f"bhavcopy_{get_ist_now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="bhav_export_xlsx",
        )
    with c2:
        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Export CSV",
            data=csv,
            file_name=f"bhavcopy_{get_ist_now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            key="bhav_export_csv",
        )
