from __future__ import annotations

import streamlit as st

from classroom_neurofeedback.core.collector import LSLAttentionCollector


def get_collector() -> LSLAttentionCollector:
    collector = st.session_state.get("_collector")
    if collector is None:
        collector = LSLAttentionCollector(stream_name_filter="")
        collector.start()
        st.session_state["_collector"] = collector
    return collector

