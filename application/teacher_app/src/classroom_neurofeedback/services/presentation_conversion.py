from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


LIBREOFFICE_PATH_ENV = "LIBREOFFICE_PATH"
CONVERTIBLE_EXTENSIONS = {"ppt", "pptx", "pptm", "pps", "ppsx", "odp"}


def convert_to_pdf(source_path: Path, output_path: Path, input_format: str) -> str:
    if input_format not in CONVERTIBLE_EXTENSIONS:
        return "Saved. Preview conversion is not available for this file type."

    executable = _find_libreoffice()
    if executable is None:
        return (
            "Saved. Install LibreOffice or set LIBREOFFICE_PATH to enable local PDF preview conversion."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="teacher-studio-lo-") as profile_dir:
        command = [
            str(executable),
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            f"-env:UserInstallation={Path(profile_dir).as_uri()}",
            "--convert-to",
            "pdf:impress_pdf_Export",
            "--outdir",
            str(output_path.parent),
            str(source_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)

    produced_path = output_path.parent / f"{source_path.stem}.pdf"
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Unknown LibreOffice error.").strip()
        return f"Saved, but local PDF conversion failed: {message}"
    if not produced_path.exists():
        return "Saved, but LibreOffice did not create a PDF preview."

    if produced_path != output_path:
        produced_path.replace(output_path)
    return "Converted locally to PDF preview."


def _find_libreoffice() -> Path | None:
    configured_path = os.getenv(LIBREOFFICE_PATH_ENV)
    if configured_path:
        path = Path(configured_path)
        if path.exists():
            return path

    for executable in ("soffice", "libreoffice"):
        found = shutil.which(executable)
        if found:
            return Path(found)

    common_paths = [
        Path("C:/Program Files/LibreOffice/program/soffice.exe"),
        Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
        Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
        Path("/usr/bin/libreoffice"),
        Path("/usr/local/bin/libreoffice"),
        Path("/snap/bin/libreoffice"),
    ]
    return next((path for path in common_paths if path.exists()), None)
