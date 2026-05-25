from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Tuple

from pylsl import StreamInlet, local_clock, resolve_streams

from classroom_neurofeedback.processing.attention_metric import AttentionMetric


@dataclass
class StudentStreamState:
    stream_key: str
    stream_name: str
    student_id: str
    student_name: str
    device_name: str
    channel_count: int
    sample_rate: float
    attention_engine: AttentionMetric
    last_seen_ts: float = 0.0
    last_fz: float = 0.0
    last_attention: float = 50.0
    packet_count: int = 0
    # Keep full in-session history while the dashboard is running so the
    # selected visualization can show everything since monitoring started.
    raw_fz_history: Deque[Tuple[float, float]] = field(default_factory=deque)
    attention_history: Deque[Tuple[float, float]] = field(default_factory=deque)


class LSLAttentionCollector:
    """Background LSL collector used by the Streamlit dashboard."""

    def __init__(
        self,
        *,
        min_channels: int = 1,
        stream_name_filter: str = "",
        attention_scale: float = 2.0,
        attention_offset: float = 0.0,
        attention_clamp_max: float = 100.0,
        discovery_interval_sec: float = 3.0,
        poll_interval_sec: float = 0.02,
    ) -> None:
        self.min_channels = min_channels
        self.stream_name_filter = stream_name_filter.strip().lower()
        self.attention_scale = attention_scale
        self.attention_offset = attention_offset
        self.attention_clamp_max = attention_clamp_max
        self.discovery_interval_sec = discovery_interval_sec
        self.poll_interval_sec = poll_interval_sec

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._force_discovery = threading.Event()

        self._inlets: Dict[str, StreamInlet] = {}
        self._states: Dict[str, StudentStreamState] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="lsl-attention-collector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        with self._lock:
            for inlet in self._inlets.values():
                try:
                    inlet.close_stream()
                except Exception:
                    pass
            self._inlets.clear()

    def force_discovery(self) -> None:
        self._force_discovery.set()

    def snapshot(self) -> List[dict]:
        now = local_clock()
        with self._lock:
            rows = []
            for state in self._states.values():
                age = now - state.last_seen_ts if state.last_seen_ts > 0 else float("inf")
                rows.append(
                    {
                        "stream_key": state.stream_key,
                        "stream_name": state.stream_name,
                        "student_id": state.student_id,
                        "student_name": state.student_name,
                        "device_name": state.device_name,
                        "channel_count": state.channel_count,
                        "sample_rate": state.sample_rate,
                        "last_seen_age_sec": age,
                        "last_fz": state.last_fz,
                        "last_attention": state.last_attention,
                        "packet_count": state.packet_count,
                        "raw_fz_history": list(state.raw_fz_history),
                        "attention_history": list(state.attention_history),
                    }
                )

        rows.sort(key=lambda row: row["student_id"])
        return rows

    def _run(self) -> None:
        next_discovery = 0.0
        while not self._stop_event.is_set():
            now = time.monotonic()
            if now >= next_discovery or self._force_discovery.is_set():
                self._discover_streams()
                self._force_discovery.clear()
                next_discovery = now + self.discovery_interval_sec

            self._poll_inlets()
            time.sleep(self.poll_interval_sec)

    def _discover_streams(self) -> None:
        try:
            streams = resolve_streams(wait_time=0.4)
        except Exception:
            return

        for stream_info in streams:
            try:
                channel_count = int(stream_info.channel_count())
                stream_name = stream_info.name()
            except Exception:
                continue

            if channel_count < self.min_channels:
                continue
            if self.stream_name_filter and self.stream_name_filter not in stream_name.lower():
                continue

            stream_key = self._stream_key(stream_info)
            with self._lock:
                if stream_key in self._inlets:
                    state = self._states.get(stream_key)
                    if state is not None:
                        state.stream_name = stream_name
                        state.channel_count = channel_count
                        state.sample_rate = float(stream_info.nominal_srate())
                    continue

            try:
                inlet = StreamInlet(stream_info, max_buflen=8, recover=True)
            except Exception:
                continue

            try:
                metadata_info = inlet.info(timeout=0.5)
            except Exception:
                metadata_info = stream_info

            student_id = self._extract_student_id(metadata_info)
            student_name = self._extract_student_name(metadata_info)
            device_name = self._extract_device_name(metadata_info)
            sample_rate = float(metadata_info.nominal_srate())

            state = StudentStreamState(
                stream_key=stream_key,
                stream_name=stream_name,
                student_id=student_id,
                student_name=student_name,
                device_name=device_name,
                channel_count=channel_count,
                sample_rate=sample_rate,
                attention_engine=AttentionMetric(
                    fs=250,
                    window_size=256,
                    attention_scale=self.attention_scale,
                    attention_offset=self.attention_offset,
                    attention_clamp_max=self.attention_clamp_max,
                ),
            )

            with self._lock:
                self._inlets[stream_key] = inlet
                self._states[stream_key] = state

    def _poll_inlets(self) -> None:
        with self._lock:
            inlets = list(self._inlets.items())

        for stream_key, inlet in inlets:
            try:
                samples, timestamps = inlet.pull_chunk(timeout=0.0, max_samples=64)
            except Exception:
                self._drop_inlet(stream_key)
                continue

            if not samples:
                continue

            with self._lock:
                state = self._states.get(stream_key)
                if state is None:
                    continue

                for idx, sample in enumerate(samples):
                    fz = self._extract_fz(sample)
                    if fz is None:
                        continue

                    received_ts = float(local_clock())
                    ts = (
                        float(timestamps[idx])
                        if idx < len(timestamps) and timestamps[idx]
                        else received_ts
                    )

                    state.packet_count += 1
                    # Freshness in the dashboard should reflect when this machine
                    # last received data, not the sender's LSL clock domain.
                    state.last_seen_ts = received_ts
                    state.last_fz = fz
                    state.raw_fz_history.append((ts, fz))

                    attention_updates = state.attention_engine.add_sample(fz)
                    for attention in attention_updates:
                        state.last_attention = attention
                        state.attention_history.append((ts, attention))

    def _drop_inlet(self, stream_key: str) -> None:
        inlet = None
        with self._lock:
            inlet = self._inlets.pop(stream_key, None)
        if inlet is not None:
            try:
                inlet.close_stream()
            except Exception:
                pass

    @staticmethod
    def _extract_fz(sample: List[float] | Tuple[float, ...]) -> float | None:
        if not sample:
            return None
        try:
            return float(sample[0])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _stream_key(stream_info) -> str:
        parts = []
        for getter in ("source_id", "uid", "hostname", "name"):
            try:
                value = getattr(stream_info, getter)()
                if value:
                    parts.append(str(value))
            except Exception:
                continue
        return "::".join(parts) if parts else f"stream::{id(stream_info)}"

    @staticmethod
    def _extract_student_id(stream_info) -> str:
        try:
            student_id = stream_info.desc().child_value("student_id")
            if student_id:
                return student_id
        except Exception:
            pass

        name = stream_info.name()
        direct_match = re.search(r"student[_\-\s]*(\d+)", name, re.IGNORECASE)
        if direct_match:
            return f"Student-{int(direct_match.group(1)):02d}"

        any_number = re.search(r"(\d+)", name)
        if any_number:
            return f"Student-{int(any_number.group(1)):02d}"

        return name

    @staticmethod
    def _extract_student_name(stream_info) -> str:
        try:
            student_name = stream_info.desc().child_value("student_name")
            if student_name:
                return student_name
        except Exception:
            pass

        try:
            student_id = stream_info.desc().child_value("student_id")
            if student_id:
                return student_id
        except Exception:
            pass

        try:
            return stream_info.name()
        except Exception:
            return "Unknown student"

    @staticmethod
    def _extract_device_name(stream_info) -> str:
        try:
            device_name = stream_info.desc().child_value("device_name")
            if device_name:
                return device_name
        except Exception:
            pass

        for getter in ("source_id", "hostname"):
            try:
                value = getattr(stream_info, getter)()
                if value:
                    return str(value)
            except Exception:
                continue

        try:
            return stream_info.name()
        except Exception:
            return "Unknown device"
