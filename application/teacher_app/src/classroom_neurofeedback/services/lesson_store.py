from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from classroom_neurofeedback.services.presentation_conversion import convert_to_pdf
from classroom_neurofeedback.services.speaker_notes import extract_speaker_notes


SUPPORTED_UPLOAD_EXTENSIONS = ["pdf", "ppt", "pptx", "pptm", "pps", "ppsx", "odp", "key"]
_TEACHER_APP_DIR = Path(__file__).resolve().parents[3]
LESSON_MATERIALS_DIR = _TEACHER_APP_DIR / "lesson_materials"
ORIGINALS_DIR = LESSON_MATERIALS_DIR / "originals"
PREVIEWS_DIR = LESSON_MATERIALS_DIR / "previews"
MANIFEST_PATH = LESSON_MATERIALS_DIR / "materials.json"
PREVIEW_ENGINE_VERSION = 2


def list_materials() -> list[dict[str, Any]]:
    manifest = _read_manifest()
    valid_materials = []
    manifest_changed = False

    for material in manifest:
        stored_path = ORIGINALS_DIR / material["stored_filename"]
        if stored_path.exists():
            if "speaker_notes" not in material:
                material["speaker_notes"] = extract_speaker_notes(stored_path, material["extension"])
                manifest_changed = True
            if material["extension"] != "pdf" and material.get("preview_engine_version") != PREVIEW_ENGINE_VERSION:
                preview_filename = material.get("preview_filename") or f"{Path(material['stored_filename']).stem}.pdf"
                preview_path = PREVIEWS_DIR / preview_filename
                material["preview_status"] = _create_preview(stored_path, preview_path, material["extension"])
                material["preview_filename"] = preview_filename if preview_path.exists() else ""
                material["preview_engine_version"] = PREVIEW_ENGINE_VERSION
                manifest_changed = True
            valid_materials.append(material)
        else:
            manifest_changed = True

    if manifest_changed:
        _write_manifest(valid_materials)

    return sorted(valid_materials, key=lambda material: material["created_at"], reverse=True)


def save_uploaded_material(title: str, uploaded_file: Any) -> dict[str, Any]:
    _ensure_storage()
    original_name = Path(uploaded_file.name).name
    extension = Path(original_name).suffix.lower().lstrip(".")
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        supported = ", ".join(SUPPORTED_UPLOAD_EXTENSIONS)
        raise ValueError(f"Unsupported file type. Supported types: {supported}.")

    file_bytes = uploaded_file.getvalue()
    digest = hashlib.sha256(file_bytes).hexdigest()
    manifest = _read_manifest()
    existing = next((item for item in manifest if item["sha256"] == digest), None)
    if existing:
        return {**existing, "already_saved": True}

    material_id = digest[:16]
    safe_title = _slugify(title or Path(original_name).stem)
    stored_filename = f"{safe_title}-{material_id}.{extension}"
    stored_path = ORIGINALS_DIR / stored_filename
    stored_path.write_bytes(file_bytes)

    preview_filename = stored_filename if extension == "pdf" else f"{safe_title}-{material_id}.pdf"
    preview_status = _create_preview(stored_path, PREVIEWS_DIR / preview_filename, extension)
    preview_available = extension == "pdf" or (PREVIEWS_DIR / preview_filename).exists()

    material = {
        "id": material_id,
        "title": title.strip() or Path(original_name).stem,
        "original_filename": original_name,
        "stored_filename": stored_filename,
        "extension": extension,
        "content_type": uploaded_file.type or mimetypes.guess_type(original_name)[0] or "application/octet-stream",
        "size_bytes": len(file_bytes),
        "sha256": digest,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "preview_filename": preview_filename if preview_available else "",
        "preview_status": preview_status,
        "preview_engine_version": PREVIEW_ENGINE_VERSION,
        "speaker_notes": extract_speaker_notes(stored_path, extension),
    }
    manifest.append(material)
    _write_manifest(manifest)
    return material


def get_material(material_id: str) -> dict[str, Any] | None:
    return next((material for material in list_materials() if material["id"] == material_id), None)


def material_original_path(material: dict[str, Any]) -> Path:
    return ORIGINALS_DIR / material["stored_filename"]


def material_preview_path(material: dict[str, Any]) -> Path | None:
    preview_filename = material.get("preview_filename")
    if not preview_filename:
        return None
    if material["extension"] == "pdf":
        return material_original_path(material)
    preview_path = PREVIEWS_DIR / preview_filename
    return preview_path if preview_path.exists() else None


def _create_preview(source_path: Path, preview_path: Path, extension: str) -> str:
    if extension == "pdf":
        return "PDF preview available."
    try:
        return convert_to_pdf(source_path, preview_path, extension)
    except Exception as exc:
        return f"Saved, but conversion failed: {exc}"


def _read_manifest() -> list[dict[str, Any]]:
    _ensure_storage()
    if not MANIFEST_PATH.exists():
        return []
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _write_manifest(manifest: list[dict[str, Any]]) -> None:
    _ensure_storage()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _ensure_storage() -> None:
    ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "lesson-material"
