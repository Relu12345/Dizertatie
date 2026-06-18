from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from classroom_neurofeedback.services.lesson_store import LESSON_MATERIALS_DIR


REPORTS_PATH = LESSON_MATERIALS_DIR / "reports.json"


def list_reports() -> list[dict[str, Any]]:
    reports = _read_reports()
    return sorted(reports, key=lambda report: report.get("created_at", ""), reverse=True)


def get_report(report_id: str) -> dict[str, Any] | None:
    return next((report for report in list_reports() if report.get("id") == report_id), None)


def save_report(report: dict[str, Any]) -> dict[str, Any]:
    reports = _read_reports()
    report = {
        **report,
        "id": report.get("id") or uuid4().hex,
        "created_at": report.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "notes": report.get("notes", ""),
        "slide_notes": report.get("slide_notes", {}),
    }
    reports = [existing for existing in reports if existing.get("id") != report["id"]]
    reports.append(report)
    _write_reports(reports)
    return report


def update_report_notes(report_id: str, notes: str, slide_notes: dict[str, str]) -> None:
    reports = _read_reports()
    for report in reports:
        if report.get("id") == report_id:
            report["notes"] = notes
            report["slide_notes"] = slide_notes
            break
    _write_reports(reports)


def _read_reports() -> list[dict[str, Any]]:
    LESSON_MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
    if not REPORTS_PATH.exists():
        return []
    try:
        data = json.loads(REPORTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _write_reports(reports: list[dict[str, Any]]) -> None:
    LESSON_MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_PATH.write_text(json.dumps(reports, indent=2), encoding="utf-8")
