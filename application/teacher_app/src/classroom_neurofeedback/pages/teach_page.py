from __future__ import annotations

import base64
import json
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from pylsl import local_clock

from classroom_neurofeedback.services.collector_service import get_collector
from classroom_neurofeedback.services.lesson_store import (
    get_material,
    list_materials,
    material_original_path,
    material_preview_path,
)
from classroom_neurofeedback.services.pdf_pages import pdf_page_count, render_pdf_page_from_path
from classroom_neurofeedback.services.report_store import save_report
from classroom_neurofeedback.ui.common import safe, section_head


def render_teach_page(data: dict[str, Any]) -> None:
    section_head("Teach Lesson")
    if st.session_state.pop("close_separate_presentation", False):
        _close_separate_presentation()

    materials = list_materials()
    if not materials:
        st.info("No materials saved yet. Upload one from Create Lesson first.")
        return

    options = {material["id"]: material for material in materials}
    selected_id = st.selectbox(
        "Choose material",
        options=list(options.keys()),
        format_func=lambda material_id: options[material_id]["title"],
    )
    selected_material = options[selected_id]
    original_path = material_original_path(selected_material)
    st.download_button(
        "Download Original Material",
        data=original_path.read_bytes(),
        file_name=selected_material["original_filename"],
        mime=selected_material["content_type"],
        width="stretch",
    )

    view_mode = st.selectbox("View Mode", ["Presenter view with notes", "Presentation only"])
    if view_mode == "Presenter view with notes":
        st.caption("Presenter view opens the normal presentation in a separate window automatically.")
        present_on = "Separate window"
    else:
        present_on = st.selectbox("Present On", ["This screen", "Separate window"])

    should_open_separate = present_on == "Separate window"
    present_clicked = (
        _render_present_lesson_launcher(should_open_separate)
        if should_open_separate
        else st.button("Present Lesson", type="primary", width="stretch")
    )

    if present_clicked:
        st.session_state["is_presenting"] = True
        st.session_state["presenting_material_id"] = selected_id
        st.session_state["present_on"] = "Separate window" if should_open_separate else "This screen"
        st.session_state["presentation_view_mode"] = view_mode
        st.session_state["presentation_page_index"] = 0
        st.session_state["open_separate_presentation"] = should_open_separate
        _start_report_capture(selected_material)

    if st.session_state.get("is_presenting"):
        material = get_material(st.session_state.get("presenting_material_id", selected_id))
        if material is not None:
            if st.session_state.get("open_separate_presentation"):
                _open_separate_presentation(material)
                st.session_state["open_separate_presentation"] = False
            _render_presentation_dialog(material)


def _clear_presentation_state() -> None:
    material_id = st.session_state.get("presenting_material_id")
    if st.session_state.get("active_report_capture") and material_id:
        material = get_material(material_id)
        if material is not None:
            _finish_report_capture(material)

    st.session_state["close_separate_presentation"] = True
    st.session_state["is_presenting"] = False
    st.session_state.pop("presenting_material_id", None)
    st.session_state.pop("present_on", None)
    st.session_state.pop("presentation_view_mode", None)
    st.session_state.pop("presentation_page_index", None)
    st.session_state.pop("open_separate_presentation", None)
    st.session_state.pop("active_report_capture", None)


@st.dialog("Presenting Lesson", width="large", on_dismiss=_clear_presentation_state)
def _render_presentation_dialog(material: dict[str, Any]) -> None:
    present_on = st.session_state.get("present_on", "This screen")
    view_mode = st.session_state.get("presentation_view_mode", "Presenter view with notes")
    st.caption(f"Engagement capture is running automatically. Output: {present_on}. Mode: {view_mode}.")
    st.markdown(f"### {safe(material['title'])}")

    if present_on == "Separate window" and view_mode == "Presentation only":
        _render_separate_window_controller(material)
    else:
        _render_current_page(material)

    if view_mode == "Presenter view with notes":
        _render_speaker_notes(material, _current_page_index())

    _render_presentation_controls(material)


def _render_current_page(material: dict[str, Any]) -> None:
    preview_path = material_preview_path(material)
    if preview_path is None:
        _render_missing_preview(material)
        return

    page_index = _bounded_page_index(preview_path)
    page_count = pdf_page_count(str(preview_path))
    show_notes = st.session_state.get("presentation_view_mode") == "Presenter view with notes"
    speaker_note = (_speaker_note_for_slide(material, page_index) or "") if show_notes else None
    encoded_pages = [
        base64.b64encode(render_pdf_page_from_path(preview_path, index)).decode("ascii")
        for index in range(page_count)
    ]
    speaker_notes = [
        (_speaker_note_for_slide(material, index) or "") if show_notes else None
        for index in range(page_count)
    ]
    _render_slide_view(encoded_pages, material["title"], page_index, page_count, speaker_note, speaker_notes)
    if material["extension"] != "pdf":
        st.caption(
            "Converted previews may look different if the original presentation uses fonts "
            "or PowerPoint features that LibreOffice cannot reproduce exactly."
        )


def _render_missing_preview(material: dict[str, Any]) -> None:
    st.markdown(
        f"""
        <article class='ui-card'>
            <div class='ui-card-title'>{safe(material['original_filename'])}</div>
            <div class='ui-card-meta'>{safe(material['preview_status'])}</div>
            <div class='ui-card-meta' style='margin-top:0.45rem;'>
                Use the download button on the lesson page to open the original file.
            </div>
        </article>
        """,
        unsafe_allow_html=True,
    )


def _render_separate_window_controller(material: dict[str, Any]) -> None:
    preview_path = material_preview_path(material)
    if preview_path is None:
        _render_missing_preview(material)
        return

    page_index = _bounded_page_index(preview_path)
    page_count = pdf_page_count(str(preview_path))
    st.markdown(
        f"""
        <article class='ui-card'>
            <div class='ui-card-title'>Presentation opened in separate window</div>
            <div class='ui-card-meta'>
                The audience sees the clean slide view in its own browser window.
                Use the controls below to advance or stop the lesson.
            </div>
            <div class='ui-card-meta' style='margin-top:0.45rem;'>
                Current page: {page_index + 1} / {page_count}
            </div>
        </article>
        """,
        unsafe_allow_html=True,
    )


def _render_present_lesson_launcher(should_open: bool) -> bool:
    clicked = st.button("Present Lesson", key="present_lesson_submit", type="primary", width="stretch")

    launcher_html = (
        """
        <button id="presentLessonLauncher" type="button">Present Lesson</button>
        <script>
        const parentWindow = window.parent;
        const parentDocument = parentWindow.document;

        function openAudienceWindow() {
            if (!__SHOULD_OPEN__) {
                return;
            }
            if (
                parentWindow.teacherStudioPresentationPopup &&
                !parentWindow.teacherStudioPresentationPopup.closed
            ) {
                parentWindow.teacherStudioPresentationPopup.focus();
                return;
            }

            const popup = parentWindow.open("", "teacherStudioPresentation", "popup=yes,width=1280,height=800");
            if (!popup) {
                return;
            }
            parentWindow.teacherStudioPresentationPopup = popup;
            popup.document.write(`
                <!doctype html>
                <html>
                    <head>
                        <title>Presentation</title>
                        <style>
                            html, body {
                                margin: 0;
                                width: 100%;
                                height: 100%;
                                background: #111827;
                                color: #e5e7eb;
                                display: grid;
                                place-items: center;
                                font: 16px system-ui, sans-serif;
                            }
                        </style>
                    </head>
                    <body>Opening presentation...</body>
                </html>
            `);
            popup.document.close();
            popup.focus();
        }

        function findStreamlitPresentButton() {
            const buttons = Array.from(parentDocument.querySelectorAll("button"));
            return buttons.find((button) => (
                button.textContent.includes("Present Lesson") &&
                button.id !== "presentLessonLauncher" &&
                !button.dataset.teacherStudioLauncher
            ));
        }

        function hideStreamlitPresentButton() {
            const button = findStreamlitPresentButton();
            if (button) {
                const wrapper = button.closest('[data-testid="stButton"]') || button.parentElement;
                if (wrapper) {
                    wrapper.style.position = "absolute";
                    wrapper.style.width = "1px";
                    wrapper.style.height = "1px";
                    wrapper.style.overflow = "hidden";
                    wrapper.style.opacity = "0";
                    wrapper.style.pointerEvents = "none";
                }
            }
            return button;
        }

        hideStreamlitPresentButton();
        const observer = new MutationObserver(hideStreamlitPresentButton);
        observer.observe(parentDocument.body, { childList: true, subtree: true });
        setTimeout(() => observer.disconnect(), 10000);

        const launcher = document.getElementById("presentLessonLauncher");
        launcher.dataset.teacherStudioLauncher = "true";
        launcher.addEventListener("click", () => {
            openAudienceWindow();
            const streamlitButton = hideStreamlitPresentButton();
            if (streamlitButton) {
                streamlitButton.click();
            }
        });
        </script>
        <style>
        #presentLessonLauncher {
            min-height: 2.5rem;
            width: 100%;
            border: 1px solid rgba(148, 163, 184, 0.38);
            border-radius: 12px;
            background: rgba(15, 23, 42, 0.9);
            color: #e2e8f0;
            font: 700 1rem system-ui, sans-serif;
            cursor: pointer;
            transition: border-color 0.18s ease, transform 0.16s ease, box-shadow 0.18s ease;
        }
        #presentLessonLauncher:hover,
        #presentLessonLauncher:focus-visible {
            border-color: #2dd4bf;
            background: rgba(15, 23, 42, 0.9);
            box-shadow: 0 0 0 0.16rem rgba(45, 212, 191, 0.14), 0 8px 16px rgba(15, 23, 42, 0.12);
            transform: translateY(-1px);
            outline: none;
        }
        </style>
        """.replace("__SHOULD_OPEN__", "true" if should_open else "false")
    )
    components.html(
        launcher_html,
        height=46,
    )
    return clicked


def _render_slide_view(
    encoded_pages: list[str],
    title: str,
    page_index: int,
    page_count: int,
    speaker_note: str | None = None,
    speaker_notes: list[str | None] | None = None,
) -> None:
    notes_markup = ""
    if speaker_note is not None:
        note_text = speaker_note or "No speaker notes were detected for this slide."
        notes_markup = f"""
            <aside class="notes-rail" aria-label="Speaker notes">
                <div class="notes-tab">Notes</div>
                <div class="notes-panel">
                    <div id="notesTitle" class="notes-title">Slide {page_index + 1}</div>
                    <div id="notesText" class="notes-text">{safe(note_text).replace(chr(10), '<br>')}</div>
                </div>
            </aside>
        """

    html = (
        """
        <section id="slideFrame" class="slide-frame">
            <button id="enterFullscreen" class="fullscreen-button" type="button">Fullscreen slide</button>
            <img id="currentSlide" src="data:image/png;base64,__CURRENT_IMAGE__" alt="__TITLE__">
            <div id="slideCounter" class="counter mouse-overlay">Page __CURRENT_PAGE__ / __PAGE_COUNT__</div>
            <div class="hint intro-overlay">Right arrow or Space: next</div>
            __NOTES_MARKUP__
        </section>
        <script>
        const parentDocument = window.parent.document;
        const frame = document.getElementById("slideFrame");
        const pages = __PAGES_JSON__;
        const speakerNotes = __NOTES_JSON__;
        let currentPage = __START_INDEX__;
        let initialPage = __START_INDEX__;
        // Keep mutable state on the parent so closures created once by
        // ensureExitButton() always read the current values across rerenders.
        window.parent.teacherStudioCurrentPage = currentPage;
        window.parent.teacherStudioInitialPage = initialPage;

        function isSlideFullscreen() {
            return document.fullscreenElement || parentDocument.fullscreenElement === window.frameElement;
        }

        function exitSlideFullscreen() {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else if (parentDocument.fullscreenElement) {
                parentDocument.exitFullscreen();
            }
        }

        function syncFullscreenClass() {
            const fullscreen = Boolean(isSlideFullscreen());
            document.body.classList.toggle("is-fullscreen", fullscreen);
            document.body.classList.toggle("controls-visible", !fullscreen);
            if (fullscreen) {
                showControls();
                showIntroHint();
            } else {
                document.body.classList.remove("intro-visible");
            }
        }

        function showControls() {
            document.body.classList.add("controls-visible");
            clearTimeout(window.teacherStudioControlsTimer);
            window.teacherStudioControlsTimer = setTimeout(() => {
                if (isSlideFullscreen()) {
                    document.body.classList.remove("controls-visible");
                }
            }, 1500);
        }

        function showIntroHint() {
            document.body.classList.add("intro-visible");
            clearTimeout(window.teacherStudioIntroTimer);
            window.teacherStudioIntroTimer = setTimeout(() => {
                document.body.classList.remove("intro-visible");
            }, 2600);
        }

        function ensureExitButton() {
            let exitButton = document.getElementById("teacherStudioExitFullscreen");
            if (exitButton) {
                return exitButton;
            }

            exitButton = document.createElement("button");
            exitButton.id = "teacherStudioExitFullscreen";
            exitButton.type = "button";
            exitButton.textContent = "Exit fullscreen";
            exitButton.style.position = "fixed";
            exitButton.style.top = "14px";
            exitButton.style.right = "14px";
            exitButton.style.zIndex = "2147483647";
            exitButton.style.border = "1px solid rgba(255, 255, 255, 0.28)";
            exitButton.style.borderRadius = "999px";
            exitButton.style.background = "rgba(17, 24, 39, 0.78)";
            exitButton.style.color = "#f9fafb";
            exitButton.style.padding = "8px 13px";
            exitButton.style.fontFamily = "system-ui, sans-serif";
            exitButton.style.fontSize = "13px";
            exitButton.style.cursor = "pointer";
            exitButton.style.opacity = "0";
            exitButton.style.transition = "opacity 0.16s ease";
            exitButton.addEventListener("click", () => {
                exitSlideFullscreen();
            });
            document.body.appendChild(exitButton);

            document.addEventListener("mousemove", () => {
                if (isSlideFullscreen()) {
                    showControls();
                    exitButton.style.opacity = "1";
                    clearTimeout(window.teacherStudioExitTimer);
                    window.teacherStudioExitTimer = setTimeout(() => {
                        exitButton.style.opacity = "0";
                    }, 1400);
                }
            });
            function onFullscreenExit() {
                if (isSlideFullscreen()) { return; }
                const cur = window.parent.teacherStudioCurrentPage;
                const ini = window.parent.teacherStudioInitialPage;
                if (typeof cur === "number" && typeof ini === "number" && cur > ini) {
                    window.parent.teacherStudioTargetPage = cur;
                    clickNextPage();
                }
            }
            document.addEventListener("fullscreenchange", () => {
                syncFullscreenClass();
                exitButton.style.display = isSlideFullscreen() ? "block" : "none";
                onFullscreenExit();
            });
            parentDocument.addEventListener("fullscreenchange", () => {
                syncFullscreenClass();
                exitButton.style.display = isSlideFullscreen() ? "block" : "none";
                onFullscreenExit();
            });
            document.addEventListener("keydown", (event) => {
                if (event.key === "Escape" && isSlideFullscreen()) {
                    exitSlideFullscreen();
                }
            });
            exitButton.style.display = "none";
            return exitButton;
        }

        function clickNextPage() {
            const buttons = Array.from(parentDocument.querySelectorAll("button"));
            const nextButton = buttons.find((button) => button.textContent.trim() === "Next Page");
            if (nextButton && !nextButton.disabled && nextButton.getAttribute("aria-disabled") !== "true") {
                nextButton.click();
            }
        }

        function renderLocalPage() {
            const image = document.getElementById("currentSlide");
            const counter = document.getElementById("slideCounter");
            const notesTitle = document.getElementById("notesTitle");
            const notesText = document.getElementById("notesText");
            image.src = "data:image/png;base64," + pages[currentPage];
            counter.textContent = `Page ${currentPage + 1} / ${pages.length}`;
            if (notesTitle && notesText) {
                notesTitle.textContent = `Slide ${currentPage + 1}`;
                notesText.textContent = speakerNotes[currentPage] || "No speaker notes were detected for this slide.";
            }
        }

        function nextLocalPage() {
            if (currentPage >= pages.length - 1) {
                return;
            }
            currentPage += 1;
            window.parent.teacherStudioCurrentPage = currentPage;
            renderLocalPage();
            if (
                window.parent.teacherStudioPresentationPopup &&
                !window.parent.teacherStudioPresentationPopup.closed &&
                typeof window.parent.teacherStudioPresentationPopup.goToPage === "function"
            ) {
                window.parent.teacherStudioPresentationPopup.goToPage(currentPage);
            }
        }

        function handleNavigationKey(event) {
            const tagName = event.target && event.target.tagName ? event.target.tagName.toLowerCase() : "";
            if (tagName === "input" || tagName === "textarea" || event.target?.isContentEditable) {
                return;
            }
            if (event.key === "ArrowRight" || event.key === " " || event.code === "Space") {
                event.preventDefault();
                if (isSlideFullscreen()) {
                    nextLocalPage();
                    showControls();
                } else {
                    clickNextPage();
                }
            }
        }

        ensureExitButton();
        syncFullscreenClass();

        // If a previous fullscreen session left a target page, keep advancing toward it.
        (function () {
            const target = window.parent.teacherStudioTargetPage;
            if (typeof target === "number") {
                if (target > __START_INDEX__) {
                    const buttons = Array.from(parentDocument.querySelectorAll("button"));
                    const nextBtn = buttons.find((b) => b.textContent.trim() === "Next Page");
                    if (nextBtn && !nextBtn.disabled && nextBtn.getAttribute("aria-disabled") !== "true") {
                        setTimeout(() => clickNextPage(), 200);
                    } else {
                        window.parent.teacherStudioTargetPage = undefined;
                    }
                } else {
                    window.parent.teacherStudioTargetPage = undefined;
                }
            }
        })();

        // Register reverse-sync callback on the popup so its navigation mirrors here.
        (function () {
            const popup = window.parent.teacherStudioPresentationPopup;
            if (popup && !popup.closed) {
                popup.onPageChange = function (newPage) {
                    if (newPage !== currentPage) {
                        currentPage = newPage;
                        renderLocalPage();
                    }
                    if (newPage > __START_INDEX__) {
                        window.parent.teacherStudioTargetPage = newPage;
                        clickNextPage();
                    }
                };
            }
        })();

        window.addEventListener("keydown", handleNavigationKey);
        if (window.parent.teacherStudioSlideKeyHandler) {
            parentDocument.removeEventListener("keydown", window.parent.teacherStudioSlideKeyHandler);
        }
        window.parent.teacherStudioSlideKeyHandler = handleNavigationKey;
        parentDocument.addEventListener("keydown", handleNavigationKey);

        document.getElementById("enterFullscreen").addEventListener("click", () => {
            const target = window.frameElement || frame;
            if (!isSlideFullscreen() && target.requestFullscreen) {
                target.requestFullscreen().catch(() => {
                    if (frame.requestFullscreen) {
                        frame.requestFullscreen().catch(() => undefined);
                    }
                });
            }
        });
        </script>
        <style>
        html, body {
            margin: 0;
            width: 100%;
            height: 100%;
            background: transparent;
            font-family: system-ui, sans-serif;
        }
        .slide-frame {
            position: relative;
            width: 100%;
            aspect-ratio: 16 / 9;
            background: #111827;
            overflow: hidden;
        }
        .slide-frame:fullscreen {
            width: 100vw;
            height: 100vh;
            aspect-ratio: auto;
        }
        body.is-fullscreen .slide-frame {
            width: 100vw;
            height: 100vh;
            aspect-ratio: auto;
        }
        #currentSlide {
            width: 100%;
            height: 100%;
            object-fit: contain;
            display: block;
        }
        .fullscreen-button {
            position: absolute;
            top: 12px;
            right: 12px;
            z-index: 2;
            border-radius: 10px;
            border: 1px solid rgba(148, 163, 184, 0.45);
            background: rgba(15, 23, 42, 0.9);
            color: #f8fafc;
            padding: 8px 12px;
            font: 700 0.95rem system-ui, sans-serif;
            cursor: pointer;
        }
        body.is-fullscreen .fullscreen-button,
        .slide-frame:fullscreen .fullscreen-button {
            display: none;
        }
        .counter,
        .hint {
            position: absolute;
            bottom: 12px;
            z-index: 2;
            color: #e5e7eb;
            background: rgba(17, 24, 39, 0.72);
            padding: 4px 9px;
            border-radius: 999px;
            font-size: 14px;
        }
        .mouse-overlay,
        .intro-overlay {
            opacity: 1;
            transition: opacity 0.16s ease;
        }
        body.is-fullscreen .mouse-overlay,
        body.is-fullscreen .intro-overlay {
            opacity: 0;
        }
        body.is-fullscreen.controls-visible .mouse-overlay,
        body.is-fullscreen.intro-visible .intro-overlay {
            opacity: 1;
        }
        .counter {
            right: 16px;
        }
        .hint {
            left: 16px;
            color: #d1d5db;
        }
        .notes-rail {
            display: none;
        }
        body.is-fullscreen .notes-rail,
        .slide-frame:fullscreen .notes-rail {
            display: block;
            position: absolute;
            inset: 0 auto 0 0;
            width: 4px;
            z-index: 3;
        }
        .notes-rail::before {
            content: "";
            position: absolute;
            inset: 0;
            background: rgba(15, 23, 42, 0.04);
        }
        .notes-tab {
            position: absolute;
            left: 0;
            top: 0;
            width: 4px;
            height: 100%;
            overflow: hidden;
            background: rgba(248, 250, 252, 0.2);
            color: transparent;
            font-size: 0;
        }
        .notes-panel {
            position: absolute;
            left: 0;
            top: 0;
            width: min(390px, 34vw);
            height: 100%;
            transform: translateX(calc(-100% + 4px));
            transition: transform 0.18s ease;
            background: rgba(15, 23, 42, 0.94);
            color: #f8fafc;
            border-right: 1px solid rgba(226, 232, 240, 0.18);
            box-shadow: 16px 0 32px rgba(15, 23, 42, 0.32);
            box-sizing: border-box;
            padding: 22px 24px 22px 28px;
            overflow-y: auto;
        }
        .notes-rail:hover .notes-panel,
        .notes-rail:focus-within .notes-panel {
            transform: translateX(0);
        }
        .notes-title {
            margin-bottom: 14px;
            color: #cbd5e1;
            font-size: 13px;
            font-weight: 800;
            text-transform: uppercase;
        }
        .notes-text {
            font-size: 20px;
            line-height: 1.5;
            overflow-wrap: anywhere;
            white-space: pre-wrap;
        }
        @media (max-width: 760px) {
            .notes-panel {
                width: min(340px, 82vw);
            }
            .notes-text {
                font-size: 16px;
            }
        }
        </style>
        """
        .replace("__CURRENT_IMAGE__", encoded_pages[page_index])
        .replace("__TITLE__", safe(title))
        .replace("__CURRENT_PAGE__", str(page_index + 1))
        .replace("__PAGE_COUNT__", str(page_count))
        .replace("__NOTES_MARKUP__", notes_markup)
        .replace("__PAGES_JSON__", json.dumps(encoded_pages))
        .replace("__NOTES_JSON__", json.dumps(speaker_notes or []))
        .replace("__START_INDEX__", str(page_index))
    )
    # Keep the embedded slide area within a size that fits the surrounding controls on the page.
    # Buttons are rendered by Streamlit below this component.
    components.html(html, height=600)


def _render_speaker_notes(material: dict[str, Any], page_index: int) -> None:
    notes = material.get("speaker_notes") or []
    st.markdown("#### Speaker Notes")
    if not notes:
        st.info("No speaker notes were detected in this material.")
        return

    current_slide = page_index + 1
    speaker_note = _speaker_note_for_slide(material, page_index)
    if speaker_note is None:
        st.info(f"No speaker notes were detected for slide {current_slide}.")
        return

    st.markdown(
        f"""
        <article class='ui-card'>
            <div class='ui-card-title'>Slide {current_slide}</div>
            <div class='ui-card-meta'>{safe(speaker_note).replace(chr(10), '<br>')}</div>
        </article>
        """,
        unsafe_allow_html=True,
    )


def _speaker_note_for_slide(material: dict[str, Any], page_index: int) -> str | None:
    current_slide = page_index + 1
    notes = material.get("speaker_notes") or []
    current_note = next((note for note in notes if int(note["slide"]) == current_slide), None)
    if current_note is None:
        return None
    return str(current_note["text"])


def _render_presentation_controls(material: dict[str, Any]) -> None:
    preview_path = material_preview_path(material)
    page_index = _bounded_page_index(preview_path) if preview_path is not None else 0
    total_pages = pdf_page_count(str(preview_path)) if preview_path is not None else 1

    next_col, stop_col = st.columns(2)
    with next_col:
        if st.button("Next Page", disabled=page_index >= total_pages - 1, type="primary", width="stretch"):
            _advance_report_capture(page_index + 1)
            st.session_state["presentation_page_index"] = page_index + 1
            st.session_state["open_separate_presentation"] = (
                st.session_state.get("present_on") == "Separate window"
                or
                st.session_state.get("presentation_view_mode") == "Presenter view with notes"
            )
            st.rerun()
    with stop_col:
        if st.button("Stop Presenting", width='stretch'):
            _finish_report_capture(material)
            _clear_presentation_state()
            st.rerun()


def _start_report_capture(material: dict[str, Any]) -> None:
    collector = get_collector()
    preview_path = material_preview_path(material)
    page_count = pdf_page_count(str(preview_path)) if preview_path is not None else 0
    now_ts = float(local_clock())
    # Snapshot current history lengths so we can slice off pre-lesson data at the end,
    # bypassing any cross-machine clock-domain issues.
    history_offsets = {
        s["student_id"]: len(s["attention_history"])
        for s in collector.snapshot()
    }
    st.session_state["active_report_capture"] = {
        "material_id": material["id"],
        "material_title": material["title"],
        "original_filename": material["original_filename"],
        "started_at_ts": now_ts,
        "page_count": page_count,
        "current_slide_index": 0,
        "current_slide_started_at_ts": now_ts,
        "slide_visits": [],
        "history_offsets": history_offsets,
    }


def _advance_report_capture(next_slide_index: int) -> None:
    capture = st.session_state.get("active_report_capture")
    if not capture:
        return

    now_ts = float(local_clock())
    _append_slide_visit(capture, now_ts)
    capture["current_slide_index"] = next_slide_index
    capture["current_slide_started_at_ts"] = now_ts
    st.session_state["active_report_capture"] = capture


def _finish_report_capture(material: dict[str, Any]) -> None:
    capture = st.session_state.get("active_report_capture")
    if not capture:
        return

    now_ts = float(local_clock())
    _append_slide_visit(capture, now_ts)
    students = _session_students(capture)
    save_report(
        {
            "material_id": material["id"],
            "material_title": material["title"],
            "original_filename": material["original_filename"],
            "started_at_ts": capture["started_at_ts"],
            "ended_at_ts": now_ts,
            "duration_sec": round(now_ts - capture["started_at_ts"], 2),
            "page_count": capture["page_count"],
            "slide_visits": capture["slide_visits"],
            "students": students,
        }
    )
    st.session_state.pop("active_report_capture", None)


def _append_slide_visit(capture: dict[str, Any], end_ts: float) -> None:
    start_ts = float(capture.get("current_slide_started_at_ts", end_ts))
    if end_ts <= start_ts:
        return
    capture["slide_visits"].append(
        {
            "slide_index": int(capture.get("current_slide_index", 0)),
            "start_ts": start_ts,
            "end_ts": end_ts,
            "duration_sec": round(end_ts - start_ts, 2),
        }
    )


def _session_students(capture: dict[str, Any]) -> list[dict[str, Any]]:
    offsets = capture.get("history_offsets", {})
    rows = []
    for student in get_collector().snapshot():
        full_history = student.get("attention_history", [])
        offset = offsets.get(student["student_id"], 0)
        history = [
            [float(ts), round(float(value), 2)]
            for ts, value in full_history[offset:]
        ]
        if not history:
            continue
        rows.append(
            {
                "student_id": student["student_id"],
                "student_name": student["student_name"],
                "stream_name": student["stream_name"],
                "engagement_history": history,
            }
        )
    return rows


def _current_page_index() -> int:
    return int(st.session_state.get("presentation_page_index", 0))


def _bounded_page_index(preview_path: Any) -> int:
    page_count = pdf_page_count(str(preview_path))
    page_index = max(0, min(_current_page_index(), page_count - 1))
    st.session_state["presentation_page_index"] = page_index
    return page_index


def _open_separate_presentation(material: dict[str, Any]) -> None:
    preview_path = material_preview_path(material)
    if preview_path is None:
        st.warning("This material does not have a PDF preview yet, so it cannot open in a separate window.")
        return

    page_index = _bounded_page_index(preview_path)
    page_count = pdf_page_count(str(preview_path))
    encoded_pages = [
        base64.b64encode(render_pdf_page_from_path(preview_path, index)).decode("ascii")
        for index in range(page_count)
    ]
    title = material["title"]
    safe_title = safe(title)
    pages_json = json.dumps(encoded_pages)
    html = f"""
    <script>
    const pages = {pages_json};
    const startIndex = {page_index};
    const title = {json.dumps(title)};
    const popup = window.open("", "teacherStudioPresentation", "popup=yes,width=1280,height=800");
    if (popup) {{
        window.parent.teacherStudioPresentationPopup = popup;
        popup.document.write(`
            <!doctype html>
            <html>
                <head>
                    <title>{safe_title}</title>
                    <style>
                        html, body {{
                            margin: 0;
                            width: 100%;
                            height: 100%;
                            background: #111827;
                            overflow: hidden;
                        }}
                        img {{
                            width: 100%;
                            height: 100%;
                            object-fit: contain;
                            display: block;
                        }}
                        .counter {{
                            position: fixed;
                            right: 16px;
                            bottom: 12px;
                            color: #e5e7eb;
                            font-family: system-ui, sans-serif;
                            font-size: 14px;
                            background: rgba(17, 24, 39, 0.72);
                            padding: 4px 9px;
                            border-radius: 999px;
                        }}
                        .hint {{
                            position: fixed;
                            left: 16px;
                            bottom: 12px;
                            color: #d1d5db;
                            font-family: system-ui, sans-serif;
                            font-size: 13px;
                            background: rgba(17, 24, 39, 0.58);
                            padding: 4px 9px;
                            border-radius: 999px;
                            opacity: 0;
                            transition: opacity 0.16s ease;
                        }}
                        body:hover .hint {{
                            opacity: 1;
                        }}
                    </style>
                </head>
                <body>
                    <img id="slide" alt="${{title}}">
                    <div class="hint">Right arrow or Space: next</div>
                    <div class="counter" id="counter"></div>
                </body>
            </html>
        `);
        popup.document.close();
        popup.pages = pages;
        popup.currentPage = Math.max(0, Math.min(startIndex, pages.length - 1));
        popup.renderPage = function () {{
            const image = popup.document.getElementById("slide");
            const counter = popup.document.getElementById("counter");
            image.src = "data:image/png;base64," + popup.pages[popup.currentPage];
            counter.textContent = `Page ${{popup.currentPage + 1}} / ${{popup.pages.length}}`;
        }};
        popup.nextPage = function () {{
            if (popup.currentPage < popup.pages.length - 1) {{
                popup.currentPage += 1;
                popup.renderPage();
                if (typeof popup.onPageChange === 'function') {{
                    popup.onPageChange(popup.currentPage);
                }}
            }}
        }};
        popup.goToPage = function (pageIndex) {{
            popup.currentPage = Math.max(0, Math.min(pageIndex, popup.pages.length - 1));
            popup.renderPage();
        }};
        popup.document.addEventListener("keydown", function (event) {{
            if (event.key === "ArrowRight" || event.key === " ") {{
                event.preventDefault();
                popup.nextPage();
            }}
            if (event.key === "Escape") {{
                if (popup.document.fullscreenElement) {{
                    popup.document.exitFullscreen();
                }}
            }}
        }});
        popup.renderPage();
        popup.focus();
    }}
    </script>
    """
    components.html(html, height=0)


def _close_separate_presentation() -> None:
    html = """
    <script>
    const popup = window.open("", "teacherStudioPresentation");
    if (popup) {
        popup.close();
    }
    window.parent.teacherStudioPresentationPopup = null;
    </script>
    """
    components.html(html, height=0)
