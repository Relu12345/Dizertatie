from __future__ import annotations

from typing import Any

import streamlit as st

from classroom_neurofeedback.ui.common import safe, section_head


def render_reports_page(data: dict[str, Any]) -> None:
    section_head("Lesson Reports")
    lesson_names = [lesson["name"] for lesson in data["lessons"]]
    selected_lesson = st.selectbox("Select lesson report", lesson_names, key="report_lesson")

    st.markdown(
        f"""
        <article class='ui-card'>
            <div class='ui-card-title'>{safe(selected_lesson)}</div>
            <div class='ui-card-meta'>
                Report generated automatically from engagement signals.
            </div>
        </article>
        """,
        unsafe_allow_html=True,
    )

    section_head("Engagement by Lesson Part")
    st.bar_chart(data["slide_report"].set_index("Slide"), width='stretch')
    st.dataframe(data["slide_report"], hide_index=True, width='stretch')
    st.button("Export Report (Mock)", width='stretch')

