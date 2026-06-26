"""
quiz.py — Tab 9: NISM Derivatives Quiz
Multiple choice questions with scoring, review mode, and progress tracking.
"""

import streamlit as st
import random

from quiz_data import QUIZ_QUESTIONS
from styles import (
    section_header, render_stat_row, stat_chip,
    C_GREEN, C_RED, C_BLUE, C_ORANGE, C_MUTED, C_TEXT, C_PANEL, C_BORDER,
)


def _init_quiz_state():
    """Initialize quiz session state."""
    _SS = st.session_state
    if "quiz_started" not in _SS:
        _SS["quiz_started"] = False
    if "quiz_questions" not in _SS:
        _SS["quiz_questions"] = []
    if "quiz_answers" not in _SS:
        _SS["quiz_answers"] = {}
    if "quiz_submitted" not in _SS:
        _SS["quiz_submitted"] = False
    if "quiz_score" not in _SS:
        _SS["quiz_score"] = 0
    if "quiz_num_questions" not in _SS:
        _SS["quiz_num_questions"] = 10
    if "quiz_history" not in _SS:
        _SS["quiz_history"] = []


def render_quiz():
    """Main render function for NISM Quiz tab."""
    _SS = st.session_state
    _init_quiz_state()

    st.markdown(
        '<div style="font-size:20px;font-weight:600;color:#d1d4dc;padding:4px 0;">🎓 NISM Derivatives Quiz</div>',
        unsafe_allow_html=True,
    )

    if not _SS["quiz_started"]:
        _render_quiz_setup()
    elif not _SS["quiz_submitted"]:
        _render_quiz_active()
    else:
        _render_quiz_results()


def _render_quiz_setup():
    """Render quiz configuration screen."""
    _SS = st.session_state

    st.markdown(
        f"""
        <div style="background:{C_PANEL};border:1px solid {C_BORDER};border-radius:8px;
                    padding:24px;text-align:center;margin:20px 0;">
            <div style="font-size:48px;">📝</div>
            <div style="font-size:18px;color:{C_TEXT};margin-top:8px;">NISM Certification Practice Quiz</div>
            <div style="font-size:13px;color:{C_MUTED};margin-top:4px;">
                Test your knowledge of derivatives, options strategies, Greeks, and Indian market regulations.
            </div>
            <div style="font-size:12px;color:{C_MUTED};margin-top:8px;">
                Total questions available: {len(QUIZ_QUESTIONS)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    num_q = st.slider(
        "Number of Questions",
        min_value=5, max_value=min(len(QUIZ_QUESTIONS), 33),
        value=min(10, len(QUIZ_QUESTIONS)),
        key="quiz_num_q_slider",
    )
    _SS["quiz_num_questions"] = num_q

    if st.button("🚀 Start Quiz", key="quiz_start_btn", use_container_width=True):
        questions = random.sample(QUIZ_QUESTIONS, min(num_q, len(QUIZ_QUESTIONS)))
        _SS["quiz_questions"] = questions
        _SS["quiz_answers"] = {}
        _SS["quiz_submitted"] = False
        _SS["quiz_score"] = 0
        _SS["quiz_started"] = True
        st.rerun()

    # Show history
    if _SS.get("quiz_history"):
        st.markdown(section_header("PAST RESULTS"), unsafe_allow_html=True)
        for i, result in enumerate(reversed(_SS["quiz_history"][-5:])):
            score = result["score"]
            total = result["total"]
            pct = (score / total * 100) if total > 0 else 0
            color = C_GREEN if pct >= 70 else C_ORANGE if pct >= 50 else C_RED
            st.markdown(
                f'<div style="background:{C_PANEL};border:1px solid {C_BORDER};border-radius:4px;'
                f'padding:8px 12px;margin:4px 0;font-size:13px;">'
                f'<span style="color:{color};font-weight:600;">{score}/{total}</span>'
                f' <span style="color:{C_MUTED};">({pct:.0f}%)</span></div>',
                unsafe_allow_html=True,
            )


def _render_quiz_active():
    """Render active quiz with questions."""
    _SS = st.session_state
    questions = _SS["quiz_questions"]

    # Progress
    answered = len(_SS["quiz_answers"])
    total = len(questions)
    st.progress(answered / total if total > 0 else 0)
    st.markdown(
        f'<div style="color:{C_MUTED};font-size:12px;text-align:right;">'
        f'Answered: {answered}/{total}</div>',
        unsafe_allow_html=True,
    )

    for i, q in enumerate(questions):
        q_num = i + 1
        is_answered = i in _SS["quiz_answers"]
        border_color = C_GREEN if is_answered else C_BORDER

        st.markdown(
            f"""
            <div style="background:{C_PANEL};border:1px solid {border_color};border-radius:6px;
                        padding:16px;margin:8px 0;">
                <div style="font-size:12px;color:{C_BLUE};font-weight:600;">QUESTION {q_num}</div>
                <div style="font-size:14px;color:{C_TEXT};margin-top:4px;">{q['question']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        selected = st.radio(
            f"Q{q_num}",
            q["options"],
            index=_SS["quiz_answers"].get(i),
            key=f"quiz_q_{i}",
            label_visibility="collapsed",
        )

        if selected:
            _SS["quiz_answers"][i] = q["options"].index(selected)

    st.markdown("<br>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("📤 Submit Quiz", key="quiz_submit", use_container_width=True):
            if len(_SS["quiz_answers"]) < total:
                st.warning(f"Please answer all questions. {total - len(_SS['quiz_answers'])} remaining.")
            else:
                # Calculate score
                score = 0
                for i, q in enumerate(questions):
                    if _SS["quiz_answers"].get(i) == q["answer"]:
                        score += 1
                _SS["quiz_score"] = score
                _SS["quiz_submitted"] = True
                _SS["quiz_history"].append({"score": score, "total": total})
                st.rerun()
    with c2:
        if st.button("🗑️ Reset", key="quiz_reset_active", use_container_width=True):
            _SS["quiz_started"] = False
            _SS["quiz_submitted"] = False
            _SS["quiz_answers"] = {}
            st.rerun()


def _render_quiz_results():
    """Render quiz results with review."""
    _SS = st.session_state
    questions = _SS["quiz_questions"]
    score = _SS["quiz_score"]
    total = len(questions)
    pct = (score / total * 100) if total > 0 else 0

    # Score card
    color = C_GREEN if pct >= 70 else C_ORANGE if pct >= 50 else C_RED
    grade = "PASS ✅" if pct >= 70 else "NEEDS IMPROVEMENT ⚠️" if pct >= 50 else "FAIL ❌"

    st.markdown(
        f"""
        <div style="background:{C_PANEL};border:2px solid {color};border-radius:10px;
                    padding:30px;text-align:center;margin:20px 0;">
            <div style="font-size:48px;font-weight:700;color:{color};">{score}/{total}</div>
            <div style="font-size:24px;color:{color};margin-top:4px;">{pct:.0f}%</div>
            <div style="font-size:14px;color:{C_MUTED};margin-top:8px;">{grade}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_stat_row([
        ("CORRECT", f"{score}", C_GREEN),
        ("WRONG", f"{total - score}", C_RED),
        ("ACCURACY", f"{pct:.0f}%", color),
    ])

    # Review
    st.markdown(section_header("REVIEW"), unsafe_allow_html=True)

    for i, q in enumerate(questions):
        user_ans = _SS["quiz_answers"].get(i, -1)
        correct = q["answer"]
        is_correct = user_ans == correct
        icon = "✅" if is_correct else "❌"
        border = C_GREEN if is_correct else C_RED

        with st.expander(f"{icon} Q{i+1}: {q['question'][:80]}...", expanded=not is_correct):
            for j, opt in enumerate(q["options"]):
                if j == correct:
                    st.markdown(f'✅ **{opt}**')
                elif j == user_ans and not is_correct:
                    st.markdown(f'❌ ~~{opt}~~')
                else:
                    st.markdown(f'○ {opt}')

            st.markdown(
                f'<div style="background:rgba(41,98,255,0.1);border-left:3px solid {C_BLUE};'
                f'padding:8px 12px;margin-top:8px;font-size:13px;color:{C_MUTED};">'
                f'💡 {q["explanation"]}</div>',
                unsafe_allow_html=True,
            )

    # Actions
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 New Quiz", key="quiz_new", use_container_width=True):
            _SS["quiz_started"] = False
            _SS["quiz_submitted"] = False
            _SS["quiz_answers"] = {}
            st.rerun()
    with c2:
        if st.button("📋 Retry Same", key="quiz_retry", use_container_width=True):
            _SS["quiz_submitted"] = False
            _SS["quiz_answers"] = {}
            st.rerun()
