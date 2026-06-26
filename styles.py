"""
styles.py — Global CSS and HTML helper functions for Bloomberg/TradingView dark theme.
"""

import streamlit as st

# ── Color Palette ────────────────────────────────────────────────────────────

C_BG = "#131722"
C_PANEL = "#1e222d"
C_BORDER = "#2a2e39"
C_TEXT = "#d1d4dc"
C_MUTED = "#787b86"
C_GREEN = "#26a69a"
C_RED = "#ef5350"
C_BLUE = "#2962ff"
C_ORANGE = "#ff9800"
C_PURPLE = "#9c27b0"
C_CYAN = "#00bcd4"

LEG_COLORS = {
    1: C_BLUE, 2: C_GREEN, 3: C_ORANGE,
    4: C_RED, 5: C_PURPLE, 6: C_CYAN,
    7: C_BLUE, 8: C_GREEN, 9: C_ORANGE, 10: C_RED,
}


def inject_css():
    """Inject global CSS for Bloomberg/TradingView dark theme."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        /* ── Global ─────────────────────────────────── */
        .stApp {{
            background-color: {C_BG};
            color: {C_TEXT};
            font-family: 'Inter', sans-serif;
        }}

        /* ── Sidebar ────────────────────────────────── */
        section[data-testid="stSidebar"] {{
            background-color: {C_PANEL};
            border-right: 1px solid {C_BORDER};
        }}
        section[data-testid="stSidebar"] .stMarkdown p,
        section[data-testid="stSidebar"] .stMarkdown div {{
            color: {C_TEXT};
        }}

        /* ── Inputs ─────────────────────────────────── */
        .stSelectbox > div > div,
        .stNumberInput > div > div > input,
        .stTextInput > div > div > input {{
            background-color: {C_PANEL} !important;
            color: {C_TEXT} !important;
            border: 1px solid {C_BORDER} !important;
            border-radius: 4px;
        }}
        .stSelectbox label, .stNumberInput label, .stTextInput label,
        .stCheckbox label, .stRadio label, .stSlider label,
        .stDateInput label, .stMultiSelect label {{
            color: {C_MUTED} !important;
            font-size: 11px !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        /* ── Buttons ────────────────────────────────── */
        .stButton > button {{
            background-color: {C_PANEL};
            color: {C_TEXT};
            border: 1px solid {C_BORDER};
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
            padding: 6px 16px;
            transition: all 0.2s ease;
        }}
        .stButton > button:hover {{
            background-color: {C_BLUE};
            border-color: {C_BLUE};
            color: white;
        }}

        /* ── Primary buttons ────────────────────────── */
        .stButton > button[kind="primary"] {{
            background-color: {C_BLUE};
            border-color: {C_BLUE};
            color: white;
        }}

        /* ── Tabs ───────────────────────────────────── */
        .stTabs [data-baseweb="tab-list"] {{
            background-color: {C_PANEL};
            border-radius: 6px;
            padding: 2px;
            gap: 2px;
        }}
        .stTabs [data-baseweb="tab"] {{
            background-color: transparent;
            color: {C_MUTED};
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
            padding: 8px 16px;
        }}
        .stTabs [aria-selected="true"] {{
            background-color: {C_BG} !important;
            color: {C_TEXT} !important;
        }}
        .stTabs [data-baseweb="tab-border"] {{
            display: none;
        }}
        .stTabs [data-baseweb="tab-highlight"] {{
            display: none;
        }}

        /* ── Dataframes / Tables ────────────────────── */
        .stDataFrame {{
            border: 1px solid {C_BORDER};
            border-radius: 6px;
        }}
        [data-testid="stDataFrame"] th {{
            background-color: {C_PANEL} !important;
            color: {C_MUTED} !important;
            font-size: 10px !important;
            text-transform: uppercase;
        }}

        /* ── Metric ─────────────────────────────────── */
        [data-testid="stMetric"] {{
            background-color: {C_PANEL};
            border: 1px solid {C_BORDER};
            border-radius: 6px;
            padding: 12px;
        }}
        [data-testid="stMetricLabel"] {{
            color: {C_MUTED} !important;
            font-size: 10px !important;
            text-transform: uppercase;
        }}
        [data-testid="stMetricValue"] {{
            color: {C_TEXT} !important;
        }}

        /* ── Expanders ──────────────────────────────── */
        .streamlit-expanderHeader {{
            background-color: {C_PANEL};
            border: 1px solid {C_BORDER};
            border-radius: 6px;
            color: {C_TEXT};
        }}

        /* ── Forms ──────────────────────────────────── */
        [data-testid="stForm"] {{
            background-color: {C_PANEL};
            border: 1px solid {C_BORDER};
            border-radius: 8px;
            padding: 20px;
        }}

        /* ── Divider ────────────────────────────────── */
        hr {{
            border-color: {C_BORDER};
        }}

        /* ── Scrollbar ──────────────────────────────── */
        ::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}
        ::-webkit-scrollbar-track {{
            background: {C_BG};
        }}
        ::-webkit-scrollbar-thumb {{
            background: {C_BORDER};
            border-radius: 3px;
        }}

        /* ── Toast/Alert ────────────────────────────── */
        .stAlert {{
            background-color: {C_PANEL};
            border: 1px solid {C_BORDER};
            color: {C_TEXT};
        }}

        /* ── Progress bar ───────────────────────────── */
        .stProgress > div > div {{
            background-color: {C_BLUE};
        }}

        /* ── Hide Streamlit branding ────────────────── */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        header {{visibility: hidden;}}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── HTML Helpers ─────────────────────────────────────────────────────────────

def stat_chip(label, value, color=C_TEXT):
    """Return HTML for a stat chip (label + value card)."""
    return f"""
    <div style="background:{C_PANEL};border:1px solid {C_BORDER};border-radius:6px;padding:10px 14px;text-align:center;">
        <div style="font-size:10px;color:{C_MUTED};text-transform:uppercase;letter-spacing:0.05em;">{label}</div>
        <div style="font-size:18px;font-weight:600;color:{color};margin-top:2px;">{value}</div>
    </div>
    """


def stat_chip_small(label, value, color=C_TEXT):
    """Smaller variant of stat chip."""
    return f"""
    <div style="background:{C_PANEL};border:1px solid {C_BORDER};border-radius:4px;padding:6px 10px;text-align:center;">
        <div style="font-size:9px;color:{C_MUTED};text-transform:uppercase;">{label}</div>
        <div style="font-size:14px;font-weight:600;color:{color};margin-top:1px;">{value}</div>
    </div>
    """


def section_header(text):
    """Return HTML for a section header with bottom border."""
    return f"""
    <div style="font-size:11px;color:{C_MUTED};text-transform:uppercase;letter-spacing:0.08em;
                border-bottom:1px solid {C_BORDER};padding-bottom:4px;margin:12px 0 8px;">
        {text}
    </div>
    """


def leg_badge(leg_num, text=""):
    """Return colored badge HTML for a leg number."""
    color = LEG_COLORS.get(leg_num, C_BLUE)
    label = text or f"LEG {leg_num}"
    return f"""
    <span style="background:{color};color:white;padding:2px 8px;border-radius:3px;
                 font-size:10px;font-weight:600;letter-spacing:0.05em;">{label}</span>
    """


def value_color(val):
    """Return green for positive, red for negative, muted for zero."""
    if val > 0:
        return C_GREEN
    elif val < 0:
        return C_RED
    return C_MUTED


def format_currency(val, prefix="₹"):
    """Format number as currency string with sign and color."""
    color = value_color(val)
    sign = "+" if val > 0 else ""
    return f'<span style="color:{color};font-weight:600;">{sign}{prefix}{val:,.2f}</span>'


def render_stat_row(chips_data):
    """
    Render a row of stat chips.
    chips_data: list of (label, value, color) tuples.
    """
    n = len(chips_data)
    if n == 0:
        return
    cols = st.columns(n)
    for i, (label, value, color) in enumerate(chips_data):
        with cols[i]:
            st.markdown(stat_chip(label, value, color), unsafe_allow_html=True)


def render_stat_row_small(chips_data):
    """Render a row of small stat chips."""
    n = len(chips_data)
    if n == 0:
        return
    cols = st.columns(n)
    for i, (label, value, color) in enumerate(chips_data):
        with cols[i]:
            st.markdown(stat_chip_small(label, value, color), unsafe_allow_html=True)
