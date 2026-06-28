"""
app.py — Entry point for Option Matrix.
Sidebar navigation, session state defaults, tab routing, persistence.
"""

import streamlit as st
import json
import os

st.set_page_config(
    page_title="Option Matrix",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

from styles import inject_css
from auth import show_login_page, has_access, init_db, TOOL_LABELS
from fyers_client import get_ist_now, market_status_html, refresh_token, is_market_open, render_fyers_login, is_fyers_connected

# ── Tab imports ──────────────────────────────────────────────────────────────
from spread_chart import render_spread_chart
from multiplier_chart import render_multiplier
from iv_calculator import render_iv_calculator
from spread_tracker import render_spread_tracker
from historical_backtest import render_backtest
from position_analysis import render_positions
from strategy_builder import render_strategy
from live_bhavcopy import render_bhavcopy
from quiz import render_quiz
from admin_panel import render_admin

# ── Constants ────────────────────────────────────────────────────────────────

STATE_FILE = "user_state.json"

TAB_CONFIG = [
    ("spread", "📊 Spread Chart"),
    ("multiplier", "✖️ Multiplier"),
    ("iv", "🌡️ IV Calculator"),
    ("tracker", "📋 Spread Tracker"),
    ("backtest", "🕰️ Historical Backtest"),
    ("positions", "📂 Position Analysis"),
    ("strategy", "🏗️ Strategy Builder"),
    ("bhavcopy", "📋 Live Bhavcopy"),
    ("quiz", "🎓 NISM Quiz"),
]

TAB_RENDERERS = {
    "spread": render_spread_chart,
    "multiplier": render_multiplier,
    "iv": render_iv_calculator,
    "tracker": render_spread_tracker,
    "backtest": render_backtest,
    "positions": render_positions,
    "strategy": render_strategy,
    "bhavcopy": render_bhavcopy,
    "quiz": render_quiz,
}


# ── Session State Defaults ───────────────────────────────────────────────────

def init_session_state():
    """Initialize all session state keys with defaults."""
    _SS = st.session_state
    defaults = {
        # Auth
        "logged_in": False,
        "username": "",
        "role": "",
        "access": [],
        "active_tab": "spread",
        # Spread Chart
        "sp_num_legs": 2,
        "sp_chart_type": "Line",
        "sp_timeframe": "1",
        "sp_live_on": False,
        "sp_live_hist": [],
        "sp_last_tick": 0,
        "sp_show_greeks": False,
        # Multiplier
        "mul_sensex_strike": 0,
        "mul_nifty_strike": 0,
        "mul_timeframe": "1",
        # IV Calculator
        "iv_index": "NIFTY",
        "iv_num_expiries": 2,
        # Spread Tracker
        "trk_num_spreads": 1,
        # Backtest
        "bt_num_legs": 2,
        "bt_timeframe": "1",
        # Position Analysis
        "pos_num_positions": 1,
        # Strategy Builder
        "strat_num_legs": 2,
        "strat_preset": "Custom",
        # Bhavcopy
        "bhav_mode": "OPTIDX",
        "bhav_index": "NIFTY",
    }
    for k, v in defaults.items():
        if k not in _SS:
            _SS[k] = v


# ── Persistence ──────────────────────────────────────────────────────────────

PERSIST_KEYS = [
    "active_tab", "sp_num_legs", "sp_chart_type", "sp_timeframe", "sp_show_greeks",
    "mul_sensex_strike", "mul_nifty_strike", "mul_timeframe",
    "iv_index", "iv_num_expiries", "trk_num_spreads",
    "bt_num_legs", "bt_timeframe", "pos_num_positions",
    "strat_num_legs", "strat_preset", "bhav_mode", "bhav_index",
]


def _make_serializable(obj):
    """Convert non-serializable types for JSON."""
    if isinstance(obj, set):
        return list(obj)
    if hasattr(obj, "to_dict"):
        return None  # skip DataFrames
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def save_user_state():
    """Save user inputs to JSON file keyed by username."""
    _SS = st.session_state
    username = _SS.get("username", "")
    if not username:
        return

    data = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}

    user_state = {}
    for key in PERSIST_KEYS:
        if key in _SS:
            val = _make_serializable(_SS[key])
            if val is not None:
                user_state[key] = val

    # Also save leg configs for spread chart
    for i in range(1, 7):
        for suffix in ["_index", "_expiry", "_strike", "_opt_type", "_buy_sell", "_ratio"]:
            k = f"sp_leg{i}{suffix}"
            if k in _SS:
                user_state[k] = _make_serializable(_SS[k])

    # Strategy leg configs
    for i in range(1, 11):
        for suffix in ["_index", "_expiry", "_strike", "_opt_type", "_buy_sell", "_lots"]:
            k = f"strat_leg{i}{suffix}"
            if k in _SS:
                user_state[k] = _make_serializable(_SS[k])

    data[username] = user_state
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def load_user_state():
    """Restore user inputs from JSON file."""
    _SS = st.session_state
    username = _SS.get("username", "")
    if not username:
        return

    if not os.path.exists(STATE_FILE):
        return

    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        user_state = data.get(username, {})
        for k, v in user_state.items():
            if k not in _SS or _SS[k] in (None, "", 0, [], False):
                _SS[k] = v
    except Exception:
        pass


# ── Sidebar ──────────────────────────────────────────────────────────────────

def render_sidebar():
    """Render the sidebar with navigation, market status, and controls."""
    _SS = st.session_state

    with st.sidebar:
        # Title
        st.markdown(
            """
            <div style="text-align:center;padding:8px 0;">
                <div style="font-size:24px;font-weight:700;color:#d1d4dc;">⚡ Option Matrix</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            '<hr style="border-color:#2a2e39;margin:4px 0;">',
            unsafe_allow_html=True,
        )

        # User info
        role_icon = "🔑" if _SS["role"] == "admin" else "🔓"
        role_label = _SS["role"].title()
        st.markdown(
            f"""
            <div style="padding:4px 0;">
                <span style="color:#d1d4dc;">👤 {_SS['username']}</span>
                <span style="color:#787b86;margin-left:8px;">{role_icon} {role_label}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Market status + Fyers connection status
        fyers_status = (
            '<span style="color:#26a69a;">🟢 Connected</span>'
            if is_fyers_connected()
            else '<span style="color:#ef5350;">🔴 Not Connected</span>'
        )
        st.markdown(
            f"""
            <div style="background:#1e222d;border:1px solid #2a2e39;border-radius:6px;
                        padding:8px 12px;margin:8px 0;">
                <span style="font-size:11px;color:#787b86;">MARKET: </span>
                {market_status_html()}
                <br/>
                <span style="font-size:11px;color:#787b86;">FYERS: </span>
                {fyers_status}
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Fyers login UI (only shows if not connected)
        if not is_fyers_connected():
            render_fyers_login()

        st.markdown(
            '<hr style="border-color:#2a2e39;margin:8px 0;">',
            unsafe_allow_html=True,
        )

        # Navigation buttons
        for tool_key, label in TAB_CONFIG:
            if has_access(_SS["username"], tool_key):
                is_active = _SS["active_tab"] == tool_key
                btn_style = "primary" if is_active else "secondary"
                if st.button(
                    label,
                    key=f"nav_{tool_key}",
                    use_container_width=True,
                    type=btn_style,
                ):
                    save_user_state()
                    _SS["active_tab"] = tool_key
                    st.rerun()

        # Admin panel (admin only)
        if _SS["role"] == "admin":
            if st.button(
                "⚙️ Admin Panel",
                key="nav_admin",
                use_container_width=True,
                type="primary" if _SS["active_tab"] == "admin" else "secondary",
            ):
                save_user_state()
                _SS["active_tab"] = "admin"
                st.rerun()

        st.markdown(
            '<hr style="border-color:#2a2e39;margin:8px 0;">',
            unsafe_allow_html=True,
        )

        # Control buttons
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 Reconnect", use_container_width=True, key="btn_refresh_token"):
                refresh_token()
                st.rerun()
        with c2:
            if st.button("💾 Save", use_container_width=True, key="btn_save_inputs"):
                save_user_state()
                st.success("Saved!")

        if st.button("🚪 Logout", use_container_width=True, key="btn_logout"):
            save_user_state()
            for key in list(_SS.keys()):
                del _SS[key]
            st.rerun()

        st.markdown(
            '<hr style="border-color:#2a2e39;margin:8px 0;">',
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div style="text-align:center;padding:4px;color:#787b86;font-size:10px;">
                Option Matrix v2.0 · Fyers API v3
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    """Main application entry point."""
    inject_css()
    init_db()
    init_session_state()

    _SS = st.session_state

    # Show login page if not logged in
    if not _SS.get("logged_in"):
        show_login_page()
        return

    # Load saved state on first run after login
    if not _SS.get("_state_loaded"):
        load_user_state()
        _SS["_state_loaded"] = True

    # Render sidebar
    render_sidebar()

    # Route to active tab
    active = _SS.get("active_tab", "spread")

    if active == "admin" and _SS["role"] == "admin":
        render_admin()
    elif active in TAB_RENDERERS:
        if has_access(_SS["username"], active):
            TAB_RENDERERS[active]()
        else:
            st.markdown(
                """
                <div style="text-align:center;padding:80px 0;">
                    <div style="font-size:48px;">🔒</div>
                    <div style="font-size:18px;color:#787b86;margin-top:12px;">
                        You don't have access to this tool.
                    </div>
                    <div style="font-size:14px;color:#787b86;margin-top:8px;">
                        Contact your admin to request access.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("Select a tab from the sidebar.")


if __name__ == "__main__":
    main()
