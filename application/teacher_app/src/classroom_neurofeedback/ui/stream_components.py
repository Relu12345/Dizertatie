from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from classroom_neurofeedback.ui.common import attention_value, safe, status_label


def render_stream_cards(streams: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not streams:
        st.session_state.pop("selected_stream_key", None)
        return None

    options = {row["stream_key"]: row for row in streams}
    selected_key = st.session_state.get("selected_stream_key")
    if selected_key not in options:
        selected_key = None
        st.session_state.pop("selected_stream_key", None)

    columns = st.columns(3, gap="large")
    for idx, row in enumerate(streams):
        age_sec = float(row["last_seen_age_sec"])
        label, chip_class = status_label(age_sec)
        is_selected = selected_key == row["stream_key"]
        student_name = row.get("student_name") or row["stream_name"]
        device_name = row.get("device_name") or "Unknown device"
        engagement = attention_value(row.get("last_attention"))

        with columns[idx % 3]:
            selected_class = "selected" if is_selected else ""
            st.markdown(
                f"""
                <article class='student-card {selected_class}'>
                    <div class='student-card-head'>
                        <div>
                            <p class='student-card-name'>{safe(student_name)}</p>
                            <p class='student-card-att'>Engagement {engagement:.1f}%</p>
                        </div>
                        <span class='status-chip {chip_class}'>{safe(label)}</span>
                    </div>
                    <div class='student-attention-bar'>
                        <div class='student-attention-fill' style='width:{engagement:.1f}%;'></div>
                    </div>
                    <div class='student-meta-line'><strong>Device:</strong> {safe(device_name)}</div>
                    <div class='student-meta-line'><strong>LSL Stream:</strong> {safe(row['stream_name'])}</div>
                    <div class='student-meta-line'><strong>Last packet:</strong> {age_sec:.2f}s ago</div>
                </article>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "Viewing Details" if is_selected else "View Student Details",
                key=f"select_{row['stream_key']}",
                width='stretch',
                disabled=is_selected,
            ):
                st.session_state["selected_stream_key"] = row["stream_key"]
                st.rerun()

    return options.get(st.session_state.get("selected_stream_key"))


def render_selected_stream_header(selected: dict[str, Any]) -> None:
    age_sec = float(selected["last_seen_age_sec"])
    label, chip_class = status_label(age_sec)
    student_name = selected.get("student_name") or selected["stream_name"]
    engagement = attention_value(selected.get("last_attention"))

    m1, m2, m3, m4 = st.columns([3.4, 1.2, 1.2, 0.85], gap="medium")
    with m1:
        st.markdown(
            f"""
            <div class='detail-metric'>
                <div class='detail-metric-label'>Student</div>
                <div class='detail-metric-value'>{safe(student_name)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m2:
        _render_detail_metric("Status", label)
    with m3:
        _render_detail_metric("Engagement", f"{engagement:.2f}")
    with m4:
        if st.button("Close", key="close_selected_stream", width='stretch'):
            st.session_state.pop("selected_stream_key", None)
            st.rerun()

    st.markdown(
        f"""
        <article class='stream-detail-card'>
            <div class='stream-title'>{safe(selected.get('device_name') or selected['stream_name'])}</div>
            <div class='stream-meta'>
                Channels: {selected['channel_count']} | Rate: {selected['sample_rate']:.2f} Hz
                | Packets: {selected['packet_count']} | Last seen: {age_sec:.2f}s ago
            </div>
            <div style='margin-top:0.55rem;'><span class='status-chip {chip_class}'>{safe(label)}</span></div>
        </article>
        """,
        unsafe_allow_html=True,
    )
    _render_attention_motion(engagement)
    _render_raw_stream_samples(selected["raw_fz_history"])


def _render_detail_metric(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div class='detail-metric'>
            <div class='detail-metric-label'>{safe(label)}</div>
            <div class='detail-metric-value'>{safe(value)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_attention_motion(attention: float) -> None:
    dot_bottom = 18 + (attention / 100.0) * 108
    anim_sec = max(1.8, 5.1 - (attention / 100.0) * 2.3)
    st.markdown(
        f"""
        <div class="attention-motion" style="--dot-bottom:{dot_bottom:.1f}px; --anim-sec:{anim_sec:.2f}s;">
            <div class="attention-caption">Engagement Signal</div>
            <div class="attention-value-large">{attention:.1f}</div>
            <div class="attention-track"></div>
            <div class="attention-dot"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_raw_stream_samples(raw_history: list[tuple[float, float]]) -> None:
    with st.expander("Raw Stream Samples", expanded=False):
        if not raw_history:
            st.info("No raw samples collected yet.")
            return

        recent = raw_history[-200:]
        base_ts = recent[0][0]
        raw_df = pd.DataFrame(
            {
                "time_sec": [round(ts - base_ts, 3) for ts, _ in recent],
                "fz": [value for _, value in recent],
            }
        )
        st.line_chart(raw_df.set_index("time_sec"), width='stretch')
        st.dataframe(raw_df, hide_index=True, width='stretch')

