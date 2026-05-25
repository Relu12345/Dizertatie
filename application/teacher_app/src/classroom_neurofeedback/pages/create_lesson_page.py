from __future__ import annotations

from typing import Any

import streamlit as st

from classroom_neurofeedback.services.lesson_store import (
    SUPPORTED_UPLOAD_EXTENSIONS,
    list_materials,
    save_uploaded_material,
)
from classroom_neurofeedback.ui.common import section_head


def render_create_lesson_page(data: dict[str, Any]) -> None:
    section_head("Create Lesson")
    st.caption("PDF files can be presented directly. Presentation files are converted locally with LibreOffice when available.")

    flash = st.session_state.pop("create_lesson_flash", None)
    if flash:
        level, message = flash
        getattr(st, level)(message)

    form_id = st.session_state.get("create_lesson_form_id", 0)
    with st.form(f"create_lesson_form_{form_id}", clear_on_submit=True):
        title = st.text_input("Material Title", value="")
        uploaded_file = st.file_uploader(
            "Upload material (PPT, PPTX, PDF, ODP, Keynote export)",
            type=SUPPORTED_UPLOAD_EXTENSIONS,
        )
        submitted = st.form_submit_button("Save Lesson", type="primary", width="stretch")

    if submitted:
        if uploaded_file is None:
            st.error("Upload a material before saving.")
            return
        with st.status("Saving lesson material...", expanded=True) as status:
            st.write("Saving uploaded file.")
            try:
                material = save_uploaded_material(title, uploaded_file)
            except ValueError as exc:
                status.update(label="Could not save material.", state="error", expanded=True)
                st.error(str(exc))
            else:
                if material.get("already_saved"):
                    status.update(label="Material already exists.", state="complete", expanded=False)
                    st.session_state["create_lesson_flash"] = (
                        "info",
                        f"{material['title']} is already saved. The existing material was left unchanged.",
                    )
                else:
                    st.write("Preparing presentation preview.")
                    status.update(label="Material saved.", state="complete", expanded=False)
                    st.session_state["create_lesson_flash"] = (
                        "success",
                        f"Saved {material['title']}. {material['preview_status']}",
                    )
                st.session_state["create_lesson_form_id"] = form_id + 1
                st.rerun()

    stored_materials = list_materials()
    if stored_materials:
        section_head("Saved Materials")
        st.dataframe(
            [
                {
                    "Title": material["title"],
                    "Type": material["extension"].upper(),
                    "Original File": material["original_filename"],
                    "Preview": material["preview_status"],
                }
                for material in stored_materials
            ],
            hide_index=True,
            width='stretch',
        )
