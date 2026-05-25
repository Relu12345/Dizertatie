from __future__ import annotations

from typing import Any

import pandas as pd


def get_mock_data() -> dict[str, Any]:
    return {
        "classes": [
            {"name": "Class 10A", "students": 28, "next_lesson": "Friday 09:00"},
            {"name": "Class 11B", "students": 24, "next_lesson": "Friday 12:00"},
            {"name": "Design Studio", "students": 18, "next_lesson": "Monday 14:30"},
        ],
        "materials": [
            {"name": "Impressionism Intro.pdf", "type": "PDF", "slides": 24},
            {"name": "Color Theory Masterclass.pptx", "type": "PPTX", "slides": 31},
            {"name": "Cubism Key Works.odp", "type": "ODP", "slides": 18},
        ],
        "lessons": [
            {
                "name": "Baroque Foundations",
                "class_name": "Class 10A",
                "date": "2026-03-12",
                "engagement": 76,
            },
            {
                "name": "Renaissance Portraits",
                "class_name": "Class 11B",
                "date": "2026-03-10",
                "engagement": 81,
            },
            {
                "name": "Modern Composition",
                "class_name": "Design Studio",
                "date": "2026-03-08",
                "engagement": 69,
            },
        ],
        "students_live": [
            {"name": "Student-01", "status": "Connected", "attention": 82},
            {"name": "Student-02", "status": "Connected", "attention": 74},
            {"name": "Student-03", "status": "Connected", "attention": 63},
            {"name": "Student-04", "status": "Syncing", "attention": 0},
        ],
        "slide_report": pd.DataFrame(
            [
                {"Slide": "1. Lesson Goal", "Avg Engagement": 72},
                {"Slide": "2. Historical Context", "Avg Engagement": 78},
                {"Slide": "3. Visual Analysis", "Avg Engagement": 84},
                {"Slide": "4. Comparison Exercise", "Avg Engagement": 67},
                {"Slide": "5. Reflection Prompt", "Avg Engagement": 74},
            ]
        ),
    }

