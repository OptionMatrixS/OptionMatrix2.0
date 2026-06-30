"""
auth.py — SQLite authentication system for Option Matrix
Roles: admin, member, pending. Per-tab access control.
"""

import sqlite3
import hashlib
import json
import os
import streamlit as st

DB_FILE = "option_matrix.db"

TOOL_KEYS = [
    "spread", "multiplier", "iv", "tracker",
    "backtest", "positions", "strategy", "bhavcopy", "quiz",
]

TOOL_LABELS = {
    "spread": "📊 Spread Chart",
    "multiplier": "✖️ Multiplier",
    "iv": "🌡️ IV Calculator",
    "tracker": "📋 Spread Tracker",
    "backtest": "🕰️ Historical Backtest",
    "positions": "📂 Position Analysis",
    "strategy": "🏗️ Strategy Builder",
    "bhavcopy": "📋 Live Bhavcopy",
    "quiz": "🎓 NISM Quiz",
}


def _get_conn():
    """Get SQLite connection."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database and create default admin user if needed."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'pending',
            access TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Create default admin if not exists
    c.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not c.fetchone():
        pw_hash = _hash_password("admin123")
        all_tools = json.dumps(TOOL_KEYS)
        c.execute(
            "INSERT INTO users (username, password_hash, role, access) VALUES (?, ?, ?, ?)",
            ("admin", pw_hash, "admin", all_tools),
        )
        conn.commit()
    conn.close()


def _hash_password(password):
    """SHA-256 password hash."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def register_user(username, password):
    """Register a new user with 'pending' role. Returns (success, message)."""
    if not username or not password:
        return False, "Username and password are required."
    if len(password) < 4:
        return False, "Password must be at least 4 characters."

    conn = _get_conn()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (username, password_hash, role, access) VALUES (?, ?, ?, ?)",
            (username.lower().strip(), _hash_password(password), "pending", "[]"),
        )
        conn.commit()
        return True, "Registration successful. Waiting for admin approval."
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    finally:
        conn.close()


def login_user(username, password):
    """Validate credentials. Returns (success, user_dict or error_message)."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM users WHERE username = ? AND password_hash = ?",
        (username.lower().strip(), _hash_password(password)),
    )
    row = c.fetchone()
    conn.close()

    if not row:
        return False, "Invalid username or password."

    user = dict(row)
    user["access"] = json.loads(user.get("access", "[]"))
    return True, user


def get_user(username):
    """Get user dict by username."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username.lower().strip(),))
    row = c.fetchone()
    conn.close()
    if row:
        user = dict(row)
        user["access"] = json.loads(user.get("access", "[]"))
        return user
    return None


def get_all_users():
    """Get all users for admin panel."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    users = []
    for row in rows:
        u = dict(row)
        u["access"] = json.loads(u.get("access", "[]"))
        users.append(u)
    return users


def update_user_role(username, role):
    """Update user role (admin/member/pending)."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET role = ? WHERE username = ?",
        (role, username.lower().strip()),
    )
    conn.commit()
    conn.close()


def update_user_access(username, tools):
    """Update user's tool access list."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET access = ? WHERE username = ?",
        (json.dumps(tools), username.lower().strip()),
    )
    conn.commit()
    conn.close()


def delete_user(username):
    """Delete a user."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE username = ?", (username.lower().strip(),))
    conn.commit()
    conn.close()


def update_password(username, new_password):
    """Update user's password."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (_hash_password(new_password), username.lower().strip()),
    )
    conn.commit()
    conn.close()


def has_access(username, tool_key):
    """Check if user has access to a specific tool/tab."""
    user = get_user(username)
    if not user:
        return False
    if user["role"] == "admin":
        return True
    return tool_key in user.get("access", [])


def show_login_page():
    """Render login/register page. Returns True if logged in."""
    _SS = st.session_state
    if _SS.get("logged_in"):
        return True

    init_db()

    st.markdown(
        """
        <div style="text-align:center;padding:40px 0 20px;">
            <div style="font-size:42px;font-weight:700;color:#d1d4dc;">⚡ Option Matrix</div>
            <div style="font-size:14px;color:#787b86;margin-top:4px;">
                Multi-Tab Options Analytics Platform · Fyers API v3
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab1, tab2 = st.tabs(["🔑 Login", "📝 Register"])

    with tab1:
        with st.form("login_form"):
            lu = st.text_input("Username", key="login_user")
            lp = st.text_input("Password", type="password", key="login_pass")
            submitted = st.form_submit_button("Login", use_container_width=True)
            if submitted:
                ok, result = login_user(lu, lp)
                if ok:
                    if result["role"] == "pending":
                        st.warning("⏳ Your account is pending admin approval.")
                    else:
                        _SS["logged_in"] = True
                        _SS["username"] = result["username"]
                        _SS["role"] = result["role"]
                        _SS["access"] = result["access"]
                        st.rerun()
                else:
                    st.error(result)

    with tab2:
        with st.form("register_form"):
            ru = st.text_input("Username", key="reg_user")
            rp = st.text_input("Password", type="password", key="reg_pass")
            rp2 = st.text_input("Confirm Password", type="password", key="reg_pass2")
            submitted = st.form_submit_button("Register", use_container_width=True)
            if submitted:
                if rp != rp2:
                    st.error("Passwords do not match.")
                else:
                    ok, msg = register_user(ru, rp)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

    return False
