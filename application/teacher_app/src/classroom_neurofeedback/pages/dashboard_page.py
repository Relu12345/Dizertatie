from __future__ import annotations

from typing import Any

import streamlit as st

from classroom_neurofeedback.ui.common import section_head, render_hero


def render_dashboard_page(data: dict[str, Any]) -> None:
    render_hero()

    section_head("Quick Access")
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        if st.button("Create Lesson", width='stretch', type="primary"):
            _go_to("Create Lesson")
    with q2:
        if st.button("Teach Lesson", width='stretch'):
            _go_to("Teach Lesson")
    with q3:
        if st.button("View Reports", width='stretch'):
            _go_to("Reports")
    with q4:
        if st.button("Admin Setup", width='stretch'):
            _go_to("Admin Setup")


def _go_to(page: str) -> None:
    st.session_state["pending_nav_page"] = page
    st.rerun()

