from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class LessonSegment:
    name: str
    start_ts: float
    end_ts: float | None = None


@dataclass
class LessonState:
    label: str = ""
    active: bool = False
    start_ts: float | None = None
    end_ts: float | None = None
    segments: List[LessonSegment] = field(default_factory=list)


def start_lesson(state: LessonState, now_ts: float, lesson_label: str, first_segment: str) -> None:
    state.label = lesson_label.strip() or "Class Session"
    state.active = True
    state.start_ts = now_ts
    state.end_ts = None
    state.segments = []
    start_segment(state, now_ts, first_segment)


def start_segment(state: LessonState, now_ts: float, segment_name: str) -> None:
    if not state.active:
        return

    clean_name = segment_name.strip() or f"Segment {len(state.segments) + 1}"

    if state.segments and state.segments[-1].end_ts is None:
        state.segments[-1].end_ts = now_ts

    state.segments.append(LessonSegment(name=clean_name, start_ts=now_ts))


def end_lesson(state: LessonState, now_ts: float) -> None:
    if not state.active:
        return

    state.active = False
    state.end_ts = now_ts

    if state.segments and state.segments[-1].end_ts is None:
        state.segments[-1].end_ts = now_ts


def segment_reports(state: LessonState, students: list[dict], now_ts: float) -> tuple[list[dict], list[dict]]:
    class_rows: list[dict] = []
    detail_rows: list[dict] = []

    for index, segment in enumerate(state.segments, start=1):
        seg_end = segment.end_ts if segment.end_ts is not None else now_ts
        duration_sec = max(0.0, seg_end - segment.start_ts)

        all_values: list[float] = []
        students_with_data = 0

        for student in students:
            values = [
                value
                for ts, value in student["attention_history"]
                if segment.start_ts <= ts < seg_end
            ]
            if not values:
                continue

            students_with_data += 1
            all_values.extend(values)

            detail_rows.append(
                {
                    "segment": f"{index}. {segment.name}",
                    "student_id": student["student_id"],
                    "stream_name": student["stream_name"],
                    "samples": len(values),
                    "avg_attention": round(sum(values) / len(values), 2),
                    "min_attention": round(min(values), 2),
                    "max_attention": round(max(values), 2),
                }
            )

        class_rows.append(
            {
                "segment": f"{index}. {segment.name}",
                "duration_min": round(duration_sec / 60.0, 2),
                "students_with_data": students_with_data,
                "samples_total": len(all_values),
                "class_avg_attention": round(sum(all_values) / len(all_values), 2) if all_values else None,
                "class_min_attention": round(min(all_values), 2) if all_values else None,
                "class_max_attention": round(max(all_values), 2) if all_values else None,
            }
        )

    return class_rows, detail_rows
