from __future__ import annotations

import streamlit as st

from classroom_neurofeedback.core.collector import LSLAttentionCollector
from classroom_neurofeedback.services.collector_service import get_collector
from classroom_neurofeedback.ui.common import section_head
from classroom_neurofeedback.ui.stream_components import (
    render_selected_stream_header,
    render_stream_cards,
)


@st.fragment(run_every="5s")
def render_live_stream_cards(collector: LSLAttentionCollector) -> None:
    streams = collector.snapshot()
    if not streams:
        st.info(
            "No LSL streams detected yet. Start Unicorn acquisition on the Pi. "
            "This view refreshes automatically every 5 seconds."
        )
        st.session_state.pop("selected_stream_key", None)
        return

    st.caption("Detected streams refresh every 5 seconds.")
    selected = render_stream_cards(streams)
    if selected is None:
        st.info("Choose a student card to inspect attention and raw stream samples.")
        return

    section_head("Selected Student")
    render_selected_stream_header(selected)


def render_live_streams_page() -> None:
    section_head("Live Streams")
    collector = get_collector()
    render_live_stream_cards(collector)

