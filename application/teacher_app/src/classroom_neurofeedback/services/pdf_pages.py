from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import fitz

fitz.TOOLS.mupdf_display_errors(False)


@lru_cache(maxsize=32)
def pdf_page_count(pdf_path: str) -> int:
    with fitz.open(pdf_path) as document:
        return document.page_count


@lru_cache(maxsize=128)
def render_pdf_page(pdf_path: str, page_index: int, zoom: float = 2.0) -> bytes:
    with fitz.open(pdf_path) as document:
        page = document.load_page(page_index)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pixmap.tobytes("png")


def render_pdf_page_from_path(pdf_path: Path, page_index: int, zoom: float = 2.0) -> bytes:
    return render_pdf_page(str(pdf_path), page_index, zoom)
