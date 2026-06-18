from __future__ import annotations

import re
import posixpath
import zipfile
from xml.etree import ElementTree
from pathlib import Path


_PARA_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}p"
_TEXT_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
_NOTES_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide"


def extract_speaker_notes(source_path: Path, extension: str) -> list[dict[str, str | int]]:
    if extension not in {"pptx", "pptm", "ppsx"}:
        return []
    try:
        return _extract_openxml_notes(source_path)
    except (KeyError, ElementTree.ParseError, zipfile.BadZipFile):
        return []


def _extract_openxml_notes(source_path: Path) -> list[dict[str, str | int]]:
    notes: list[dict[str, str | int]] = []
    with zipfile.ZipFile(source_path) as package:
        slide_names = sorted(
            (name for name in package.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=_slide_number,
        )
        for slide_name in slide_names:
            notes_path = _notes_path_for_slide(package, slide_name)
            if notes_path is None:
                continue
            text = _notes_text(package.read(notes_path))
            if text:
                notes.append({"slide": _slide_number(slide_name), "text": text})
    return notes


def _notes_path_for_slide(package: zipfile.ZipFile, slide_name: str) -> str | None:
    rels_name = slide_name.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
    if rels_name not in package.namelist():
        return None

    rels_root = ElementTree.fromstring(package.read(rels_name))
    for relationship in rels_root.findall(_REL_NS):
        if relationship.attrib.get("Type") != _NOTES_REL_TYPE:
            continue
        target = relationship.attrib.get("Target", "")
        return posixpath.normpath(posixpath.join(posixpath.dirname(slide_name), target))
    return None


def _notes_text(notes_xml: bytes) -> str:
    root = ElementTree.fromstring(notes_xml)
    ignored = {"slide number", "footer", "date"}
    paragraphs = []
    for para in root.iter(_PARA_NS):
        # Runs within a paragraph join with "" — they may be mid-word fragments.
        text = "".join(node.text for node in para.iter(_TEXT_NS) if node.text).strip()
        if text and text.lower() not in ignored:
            paragraphs.append(text)
    # Join paragraphs with spaces so PPTX files that store each word in its own
    # paragraph element don't produce one-word-per-line output.
    return re.sub(r" {2,}", " ", " ".join(paragraphs)).strip()


def _slide_number(slide_name: str) -> int:
    match = re.search(r"slide(\d+)\.xml", slide_name)
    return int(match.group(1)) if match else 0
