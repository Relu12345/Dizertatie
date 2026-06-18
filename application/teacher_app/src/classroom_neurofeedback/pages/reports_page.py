from __future__ import annotations

from datetime import datetime
from io import StringIO
from typing import Any

import pandas as pd
import streamlit as st

from classroom_neurofeedback.services.lesson_store import get_material, material_preview_path
from classroom_neurofeedback.services.pdf_pages import render_pdf_page_from_path
from classroom_neurofeedback.services.report_store import list_reports, update_report_notes
from classroom_neurofeedback.ui.common import safe, section_head


def render_reports_page(data: dict[str, Any]) -> None:
    section_head("Lesson Reports")
    reports = list_reports()
    if not reports:
        st.info("No reports have been recorded yet. Teach a lesson and stop the presentation to create one.")
        return

    selected_id = st.selectbox(
        "Select report",
        options=[report["id"] for report in reports],
        format_func=lambda report_id: _report_label(next(report for report in reports if report["id"] == report_id)),
        key="selected_report_id",
    )
    report = next(report for report in reports if report["id"] == selected_id)
    material = get_material(report["material_id"])
    slide_rows = _slide_rows(report)
    student_rows = _student_rows(report, slide_rows)

    _render_report_header(report, material is not None)
    _render_overview_metrics(report, slide_rows, student_rows)

    main_tab, students_tab, notes_tab, export_tab = st.tabs(
        ["Main Report", "Per-Student Reports", "Notes", "Exports"]
    )

    with main_tab:
        _render_main_report(report, material, slide_rows)

    with students_tab:
        _render_student_reports(report, student_rows, slide_rows)

    with notes_tab:
        _render_notes(report, slide_rows)

    with export_tab:
        _render_exports(report, slide_rows, student_rows)


def _render_report_header(report: dict[str, Any], has_material: bool) -> None:
    material_status = "Slides available" if has_material else "Slides unavailable"
    st.markdown(
        f"""
        <article class="ui-card">
            <div class="ui-card-title">{safe(report["material_title"])}</div>
            <div class="ui-card-meta">
                {safe(_format_created_at(report))} | {safe(material_status)}
            </div>
        </article>
        """,
        unsafe_allow_html=True,
    )


def _render_overview_metrics(
    report: dict[str, Any],
    slide_rows: list[dict[str, Any]],
    student_rows: list[dict[str, Any]],
) -> None:
    overall_values = [
        value
        for student in report.get("students", [])
        for _, value in student.get("engagement_history", [])
    ]
    avg_engagement = _avg(overall_values)
    min_engagement = min(overall_values) if overall_values else None
    max_engagement = max(overall_values) if overall_values else None
    measured_slides = sum(1 for row in slide_rows if row["samples"] > 0)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Presentation Engagement", _percent(avg_engagement), _range_delta(min_engagement, max_engagement))
    with c2:
        st.metric("Slides With Data", f"{measured_slides}/{len(slide_rows)}", "recorded engagement samples")
    with c3:
        st.metric("Presentation Time", _duration(report.get("duration_sec", 0.0)), "from first to last slide")
    with c4:
        st.metric("Mini-Reports", str(len(student_rows)), "available downloads")


def _render_main_report(
    report: dict[str, Any],
    material: dict[str, Any] | None,
    slide_rows: list[dict[str, Any]],
) -> None:
    if not slide_rows:
        st.info("No slide preview was available when this report was recorded.")
        return

    # Ensure slide ordering is numeric (Slide 1,2,3...n), not lexicographic (Slide 1, Slide 10, ...).
    chart_rows = (
        pd.DataFrame(
            [
                {
                    "Slide": f"Slide {row['slide_number']}",
                    "SlideNumber": int(row["slide_number"]),
                    "Avg Engagement": row["avg_engagement"],
                    "Time Spent (min)": round(row["duration_sec"] / 60.0, 2),
                }
                for row in slide_rows
            ]
        )
        .sort_values("SlideNumber")
        .set_index("Slide")
        .drop(columns=["SlideNumber"])
    )

    section_head("Slide Overview")

    # st.bar_chart orders bars by the index labels. Since index labels are strings
    # like "Slide 1", we enforce numeric ordering by using numeric index as well.
    chart_rows_numeric_index = chart_rows.copy()
    chart_rows_numeric_index.index = [
        int(label.replace("Slide ", "")) for label in chart_rows.index
    ]
    chart_rows_numeric_index = chart_rows_numeric_index.sort_index()

    st.markdown("##### Average Engagement (%)")
    st.bar_chart(chart_rows_numeric_index[["Avg Engagement"]], width="stretch")

    st.markdown("##### Time Spent per Slide (minutes)")
    st.bar_chart(chart_rows_numeric_index[["Time Spent (min)"]], width="stretch")


    preview_path = material_preview_path(material) if material is not None else None
    slide_notes = report.get("slide_notes", {})
    for row in slide_rows:
        left, right = st.columns([1.1, 1])
        with left:
            if preview_path is not None:
                st.image(
                    render_pdf_page_from_path(preview_path, row["slide_index"], zoom=1.25),
                    caption=f"Slide {row['slide_number']}",
                    width="stretch",
                )
            else:
                st.markdown(
                    f"""
                    <article class="ui-card">
                        <div class="ui-card-title">Slide {row["slide_number"]}</div>
                        <div class="ui-card-meta">The original material is not available in storage.</div>
                    </article>
                    """,
                    unsafe_allow_html=True,
                )

        with right:
            _render_slide_summary(row, slide_notes.get(str(row["slide_index"]), ""))
            expanded = st.toggle(
                "Show per-student engagement",
                key=f"slide_{report['id']}_{row['slide_index']}_details",
                value=False,
            )
            if expanded:
                detail_df = pd.DataFrame(row["students"])
                if detail_df.empty:
                    st.info("No student engagement samples were captured for this slide.")
                else:
                    st.dataframe(detail_df, hide_index=True, width="stretch")


def _render_slide_summary(row: dict[str, Any], note: str) -> None:
    note_markup = ""
    if note.strip():
        note_markup = f"<div class='ui-card-meta' style='margin-top:0.55rem;'>{safe(note)}</div>"
    st.markdown(
        f"""
        <article class="ui-card">
            <div class="ui-card-title">Slide {row["slide_number"]}</div>
            <div class="ui-card-meta">Average engagement: {safe(_percent(row["avg_engagement"]))}</div>
            <div class="ui-card-meta">Range: {safe(_range_text(row["min_engagement"], row["max_engagement"]))}</div>
            <div class="ui-card-meta">Time spent: {safe(_duration(row["duration_sec"]))}</div>
            <div class="ui-card-meta">Samples: {row["samples"]}</div>
            {note_markup}
        </article>
        """,
        unsafe_allow_html=True,
    )


def _render_student_reports(
    report: dict[str, Any],
    student_rows: list[dict[str, Any]],
    slide_rows: list[dict[str, Any]],
) -> None:
    section_head("Per-Student Assessment")
    if not student_rows:
        st.info("No student engagement histories were captured for this report.")
        return

    st.dataframe(pd.DataFrame(student_rows), hide_index=True, width="stretch")
    for row in student_rows:
        st.download_button(
            f"Download {row['Student']} Mini-Report",
            data=_student_report_csv(report, row["Student"], slide_rows),
            file_name=f"{_slug(report['material_title'])}-{_slug(row['Student'])}.csv",
            mime="text/csv",
            width="stretch",
            key=f"student_export_{report['id']}_{row['Student']}",
        )


def _render_notes(report: dict[str, Any], slide_rows: list[dict[str, Any]]) -> None:
    section_head("Report Notes")
    notes = st.text_area(
        "Notes for improving the presentation",
        value=report.get("notes", ""),
        height=150,
        key=f"report_notes_{report['id']}",
    )
    slide_notes: dict[str, str] = {}
    for row in slide_rows:
        slide_key = str(row["slide_index"])
        slide_notes[slide_key] = st.text_area(
            f"Slide {row['slide_number']} notes",
            value=report.get("slide_notes", {}).get(slide_key, ""),
            height=90,
            key=f"slide_notes_{report['id']}_{slide_key}",
        )

    if st.button("Save Notes", type="primary", width="stretch"):
        update_report_notes(report["id"], notes, slide_notes)
        st.success("Notes saved.")


def _render_exports(
    report: dict[str, Any],
    slide_rows: list[dict[str, Any]],
    student_rows: list[dict[str, Any]],
) -> None:
    section_head("Exports")
    st.download_button(
        "Download General Report",
        data=_general_report_csv(report, slide_rows, student_rows),
        file_name=f"{_slug(report['material_title'])}-general-report.csv",
        mime="text/csv",
        width="stretch",
    )
    for row in slide_rows:
        st.download_button(
            f"Download Slide {row['slide_number']} Report",
            data=_slide_report_csv(report, row),
            file_name=f"{_slug(report['material_title'])}-slide-{row['slide_number']}.csv",
            mime="text/csv",
            width="stretch",
            key=f"slide_export_{report['id']}_{row['slide_index']}",
        )


def _slide_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    page_count = int(report.get("page_count", 0))
    visits = report.get("slide_visits", [])
    rows = []
    for slide_index in range(page_count):
        slide_visits = [visit for visit in visits if int(visit["slide_index"]) == slide_index]
        intervals = [(float(visit["start_ts"]), float(visit["end_ts"])) for visit in slide_visits]
        student_rows = []
        all_values = []
        for student in report.get("students", []):
            values = _values_in_intervals(student.get("engagement_history", []), intervals)
            if not values:
                continue
            all_values.extend(values)
            student_rows.append(
                {
                    "Student": student.get("student_name") or student.get("student_id"),
                    "Avg Engagement": round(_avg(values), 2),
                    "Min": round(min(values), 2),
                    "Max": round(max(values), 2),
                    "Samples": len(values),
                }
            )
        duration_sec = sum(float(visit.get("duration_sec", 0.0)) for visit in slide_visits)
        rows.append(
            {
                "slide_index": slide_index,
                "slide_number": slide_index + 1,
                "duration_sec": duration_sec,
                "avg_engagement": round(_avg(all_values), 2) if all_values else None,
                "min_engagement": round(min(all_values), 2) if all_values else None,
                "max_engagement": round(max(all_values), 2) if all_values else None,
                "samples": len(all_values),
                "students": student_rows,
            }
        )
    return rows


def _student_rows(report: dict[str, Any], slide_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for student in report.get("students", []):
        name = student.get("student_name") or student.get("student_id")
        values = [float(value) for _, value in student.get("engagement_history", [])]
        if not values:
            continue
        slides_with_data = sum(
            1 for slide in slide_rows for row in slide["students"] if row["Student"] == name
        )
        rows.append(
            {
                "Student": name,
                "Avg Engagement": round(_avg(values), 2),
                "Min": round(min(values), 2),
                "Max": round(max(values), 2),
                "Slides With Data": slides_with_data,
                "Samples": len(values),
            }
        )
    return rows


def _values_in_intervals(history: list[list[float]], intervals: list[tuple[float, float]]) -> list[float]:
    values = []
    for ts, value in history:
        timestamp = float(ts)
        if any(start_ts <= timestamp <= end_ts for start_ts, end_ts in intervals):
            values.append(float(value))
    return values


def _general_report_csv(
    report: dict[str, Any],
    slide_rows: list[dict[str, Any]],
    student_rows: list[dict[str, Any]],
) -> str:
    output = StringIO()
    output.write(f"Presentation,{report['material_title']}\n")
    output.write(f"Recorded,{_format_created_at(report)}\n")
    output.write(f"Duration,{_duration(report.get('duration_sec', 0.0))}\n\n")
    pd.DataFrame(_flatten_slide_rows(slide_rows)).to_csv(output, index=False)
    output.write("\n[Per-Student Summary]\n")
    pd.DataFrame(student_rows).to_csv(output, index=False)
    output.write("\n[Notes]\n")
    output.write((report.get("notes") or "").replace("\n", " "))
    output.write("\n")
    return output.getvalue()


def _slide_report_csv(report: dict[str, Any], row: dict[str, Any]) -> str:
    output = StringIO()
    output.write(f"Presentation,{report['material_title']}\n")
    output.write(f"Slide,{row['slide_number']}\n")
    output.write(f"Average Engagement,{_empty_if_none(row['avg_engagement'])}\n")
    output.write(f"Minimum Engagement,{_empty_if_none(row['min_engagement'])}\n")
    output.write(f"Maximum Engagement,{_empty_if_none(row['max_engagement'])}\n")
    output.write(f"Time Spent,{_duration(row['duration_sec'])}\n\n")
    pd.DataFrame(row["students"]).to_csv(output, index=False)
    return output.getvalue()


def _student_report_csv(report: dict[str, Any], student_name: str, slide_rows: list[dict[str, Any]]) -> str:
    output = StringIO()
    output.write(f"Presentation,{report['material_title']}\n")
    output.write(f"Student,{student_name}\n\n")
    rows = []
    for slide in slide_rows:
        detail = next((row for row in slide["students"] if row["Student"] == student_name), None)
        rows.append(
            {
                "Slide": slide["slide_number"],
                "Time Spent": _duration(slide["duration_sec"]),
                "Avg Engagement": detail["Avg Engagement"] if detail else "",
                "Min": detail["Min"] if detail else "",
                "Max": detail["Max"] if detail else "",
                "Samples": detail["Samples"] if detail else 0,
            }
        )
    pd.DataFrame(rows).to_csv(output, index=False)
    return output.getvalue()


def _flatten_slide_rows(slide_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Slide": row["slide_number"],
            "Avg Engagement": _empty_if_none(row["avg_engagement"]),
            "Min Engagement": _empty_if_none(row["min_engagement"]),
            "Max Engagement": _empty_if_none(row["max_engagement"]),
            "Time Spent": _duration(row["duration_sec"]),
            "Samples": row["samples"],
        }
        for row in slide_rows
    ]


def _report_label(report: dict[str, Any]) -> str:
    return f"{report.get('material_title', 'Presentation')} - {_format_created_at(report)}"


def _format_created_at(report: dict[str, Any]) -> str:
    value = report.get("created_at")
    if not value:
        return "Unknown date"
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(value)


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percent(value: float | None) -> str:
    return "No data" if value is None else f"{value:.1f}%"


def _range_text(min_value: float | None, max_value: float | None) -> str:
    if min_value is None or max_value is None:
        return "No data"
    return f"{min_value:.1f}% - {max_value:.1f}%"


def _range_delta(min_value: float | None, max_value: float | None) -> str:
    if min_value is None or max_value is None:
        return "min/max unavailable"
    return f"{min_value:.0f}% min | {max_value:.0f}% max"


def _duration(seconds: Any) -> str:
    total_seconds = int(float(seconds or 0))
    minutes, remainder = divmod(total_seconds, 60)
    return f"{minutes}m {remainder:02d}s"


def _empty_if_none(value: Any) -> Any:
    return "" if value is None else value


def _slug(value: str) -> str:
    return "-".join(value.lower().split())
