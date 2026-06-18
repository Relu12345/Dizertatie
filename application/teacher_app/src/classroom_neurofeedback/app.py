from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from classroom_neurofeedback.data.mock_data import get_mock_data
from classroom_neurofeedback.pages.admin_page import render_admin_page
from classroom_neurofeedback.pages.create_lesson_page import render_create_lesson_page
from classroom_neurofeedback.pages.dashboard_page import render_dashboard_page
from classroom_neurofeedback.pages.reports_page import render_reports_page
from classroom_neurofeedback.pages.teach_page import render_teach_page
from classroom_neurofeedback.ui.theme import inject_styles


PageRenderer = Callable[[dict[str, Any]], None]


def main() -> None:
    st.set_page_config(page_title="Teacher Studio", layout="wide")
    inject_styles()

    data = get_mock_data()
    page = render_sidebar()

    pages: dict[str, PageRenderer] = {
        "Dashboard": render_dashboard_page,
        "Create Lesson": render_create_lesson_page,
        "Teach Lesson": render_teach_page,
        "Reports": render_reports_page,
    }

    if page == "Admin Setup":
        render_admin_page()
    else:
        pages[page](data)


def render_sidebar() -> str:
    pages = [
        "Dashboard",
        "Create Lesson",
        "Teach Lesson",
        "Reports",
        "Admin Setup",
    ]
    active_page = st.session_state.pop("pending_nav_page", st.session_state.get("sidebar_page", "Dashboard"))
    if active_page not in pages:
        active_page = "Dashboard"
    st.session_state["sidebar_page"] = active_page

    with st.sidebar:
        st.markdown("### Navigation")
        page = st.radio(
            "Go to",
            options=pages,
            index=pages.index(active_page),
            key="sidebar_page",
            label_visibility="collapsed",
        )
        st.markdown("---")
        st.caption("Feasibility prototype")

    return page

