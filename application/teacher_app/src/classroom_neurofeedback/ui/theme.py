from __future__ import annotations

from pathlib import Path

import streamlit as st


_THEME_PATH = Path(__file__).resolve().parent / "assets" / "theme.css"


def inject_styles() -> None:
    css = _THEME_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

