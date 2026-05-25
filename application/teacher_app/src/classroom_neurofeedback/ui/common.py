from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st


def safe(value: Any) -> str:
    return escape(str(value))


def render_hero() -> None:
    st.markdown(
        """
        <section class="hero-shell">
            <h1 class="hero-title">Teacher Studio</h1>
            <p class="hero-subtitle">
                Plan lessons, teach them, and review class engagement so the next version
                of the lesson can be clearer and better paced.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def section_head(title: str) -> None:
    st.markdown(f"<div class='section-head'>{safe(title)}</div>", unsafe_allow_html=True)


def render_simple_card(title: str, meta: str) -> None:
    st.markdown(
        f"""
        <article class='ui-card'>
            <div class='ui-card-title'>{safe(title)}</div>
            <div class='ui-card-meta'>{safe(meta)}</div>
        </article>
        """,
        unsafe_allow_html=True,
    )


def status_label(age_sec: float) -> tuple[str, str]:
    if age_sec < 2.0:
        return "Live", "chip-success"
    if age_sec < 8.0:
        return "Quiet", "chip-warning"
    return "Stale", "chip-danger"


def attention_value(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, numeric))

