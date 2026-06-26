"""
admin_panel.py — Admin Panel for user management and access control.
"""

import streamlit as st
import json

from auth import (
    get_all_users, update_user_role, update_user_access,
    delete_user, update_password, TOOL_KEYS, TOOL_LABELS,
)
from styles import (
    section_header, render_stat_row,
    C_GREEN, C_RED, C_BLUE, C_ORANGE, C_MUTED, C_TEXT, C_PANEL, C_BORDER,
)


def render_admin():
    """Main render function for Admin Panel."""
    _SS = st.session_state

    if _SS.get("role") != "admin":
        st.error("Access denied. Admin only.")
        return

    st.markdown(
        '<div style="font-size:20px;font-weight:600;color:#d1d4dc;padding:4px 0;">⚙️ Admin Panel</div>',
        unsafe_allow_html=True,
    )

    users = get_all_users()

    # Stats
    total = len(users)
    admins = len([u for u in users if u["role"] == "admin"])
    members = len([u for u in users if u["role"] == "member"])
    pending = len([u for u in users if u["role"] == "pending"])

    render_stat_row([
        ("TOTAL USERS", str(total), C_BLUE),
        ("ADMINS", str(admins), C_GREEN),
        ("MEMBERS", str(members), C_TEXT),
        ("PENDING", str(pending), C_ORANGE),
    ])

    # Pending approvals
    pending_users = [u for u in users if u["role"] == "pending"]
    if pending_users:
        st.markdown(section_header("PENDING APPROVALS"), unsafe_allow_html=True)
        for user in pending_users:
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                st.markdown(
                    f'<div style="color:{C_TEXT};font-size:14px;padding:8px 0;">'
                    f'👤 {user["username"]}'
                    f'<span style="color:{C_MUTED};font-size:11px;margin-left:8px;">'
                    f'{user.get("created_at", "")}</span></div>',
                    unsafe_allow_html=True,
                )
            with c2:
                if st.button("✅ Approve", key=f"approve_{user['username']}", use_container_width=True):
                    update_user_role(user["username"], "member")
                    update_user_access(user["username"], TOOL_KEYS)  # Grant all by default
                    st.success(f"Approved {user['username']}")
                    st.rerun()
            with c3:
                if st.button("❌ Reject", key=f"reject_{user['username']}", use_container_width=True):
                    delete_user(user["username"])
                    st.success(f"Deleted {user['username']}")
                    st.rerun()

    # All users management
    st.markdown(section_header("USER MANAGEMENT"), unsafe_allow_html=True)

    for user in users:
        if user["username"] == "admin":
            continue  # Don't modify the default admin

        with st.expander(
            f"👤 {user['username']} — {user['role'].upper()}",
            expanded=False,
        ):
            c1, c2 = st.columns(2)

            with c1:
                # Role selector
                roles = ["pending", "member", "admin"]
                current_role_idx = roles.index(user["role"]) if user["role"] in roles else 0
                new_role = st.selectbox(
                    "Role",
                    roles,
                    index=current_role_idx,
                    key=f"admin_role_{user['username']}",
                )

                if st.button("Update Role", key=f"admin_uprole_{user['username']}"):
                    update_user_role(user["username"], new_role)
                    st.success(f"Updated {user['username']} to {new_role}")
                    st.rerun()

            with c2:
                # Password reset
                new_pw = st.text_input(
                    "New Password", type="password",
                    key=f"admin_pw_{user['username']}",
                )
                if st.button("Reset Password", key=f"admin_resetpw_{user['username']}"):
                    if new_pw and len(new_pw) >= 4:
                        update_password(user["username"], new_pw)
                        st.success(f"Password reset for {user['username']}")
                    else:
                        st.error("Password must be at least 4 characters.")

            # Tool access
            st.markdown(
                f'<div style="font-size:11px;color:{C_MUTED};text-transform:uppercase;'
                f'margin:8px 0 4px;">Tool Access</div>',
                unsafe_allow_html=True,
            )

            current_access = user.get("access", [])
            new_access = []

            # Create checkboxes in a grid
            tool_cols = st.columns(3)
            for j, tool_key in enumerate(TOOL_KEYS):
                with tool_cols[j % 3]:
                    checked = st.checkbox(
                        TOOL_LABELS.get(tool_key, tool_key),
                        value=tool_key in current_access,
                        key=f"admin_tool_{user['username']}_{tool_key}",
                    )
                    if checked:
                        new_access.append(tool_key)

            c3, c4 = st.columns(2)
            with c3:
                if st.button("💾 Save Access", key=f"admin_saveaccess_{user['username']}",
                             use_container_width=True):
                    update_user_access(user["username"], new_access)
                    st.success(f"Updated access for {user['username']}")
                    st.rerun()
            with c4:
                if st.button(
                    "🗑️ Delete User", key=f"admin_delete_{user['username']}",
                    use_container_width=True,
                ):
                    delete_user(user["username"])
                    st.success(f"Deleted {user['username']}")
                    st.rerun()

    # System info
    st.markdown(section_header("SYSTEM INFO"), unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="background:{C_PANEL};border:1px solid {C_BORDER};border-radius:6px;padding:16px;">
            <div style="font-size:11px;color:{C_MUTED};line-height:1.8;">
                PLATFORM: Option Matrix v2.0<br>
                API: Fyers API v3<br>
                DATABASE: SQLite (option_matrix.db)<br>
                TOOLS: {len(TOOL_KEYS)} tabs configured<br>
                USERS: {total} registered
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
