"""Extract readable text from PDF/DOCX without retaining original files."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import pymupdf
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.core.config import (
    MAX_DOCX_MEMBERS,
    MAX_DOCX_UNCOMPRESSED_BYTES,
    MAX_PDF_PAGES,
    MAX_UPLOAD_BYTES,
    SUPPORTED_EXTENSIONS,
)
from app.schemas.resume import ResumeParseResponse


@dataclass
class ResumeParseError(Exception):
    detail: str
    status_code: int = 422

    def __str__(self) -> str:
        return self.detail


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    # Preserve separate lines so subsequent agents can recover section headings.
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _read_pdf(blob: bytes) -> tuple[str, int]:
    if not blob[:1024].lstrip().startswith(b"%PDF-"):
        raise ResumeParseError("File contents are not a valid PDF.")
    try:
        with pymupdf.open(stream=blob, filetype="pdf") as document:
            if document.needs_pass:
                raise ResumeParseError("Password-protected PDFs are not supported.")
            page_count = len(document)
            if page_count > MAX_PDF_PAGES:
                raise ResumeParseError(
                    f"PDF exceeds the limit of {MAX_PDF_PAGES} pages.", status_code=413
                )
            pages = [page.get_text("text", sort=True) for page in document]
    except (pymupdf.FileDataError, pymupdf.EmptyFileError, RuntimeError, ValueError) as exc:
        raise ResumeParseError("PDF is corrupted or cannot be read.") from exc
    return _clean_text("\n".join(pages)), page_count


def _iter_docx_blocks(blocks: Iterable[Paragraph | Table]) -> Iterator[str]:
    """Keep document order, including tables and nested table cells."""
    for block in blocks:
        if isinstance(block, Paragraph):
            paragraph = block.text.strip()
            if paragraph:
                yield paragraph
        elif isinstance(block, Table):
            seen_cells: set[object] = set()
            for row in block.rows:
                row_values = []
                for cell in row.cells:
                    cell_id = cell._tc
                    if cell_id in seen_cells:  # Avoid repeating merged cells.
                        continue
                    seen_cells.add(cell_id)
                    value = " / ".join(_iter_docx_blocks(cell.iter_inner_content()))
                    if value:
                        row_values.append(value)
                if row_values:
                    yield " | ".join(row_values)


def _validate_docx(blob: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            items = archive.infolist()
            if len(items) > MAX_DOCX_MEMBERS:
                raise ResumeParseError("DOCX contains too many internal files.", 413)
            if sum(item.file_size for item in items) > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ResumeParseError("DOCX expanded content is too large.", 413)
            if "word/document.xml" not in archive.namelist():
                raise ResumeParseError("This file is not a valid DOCX document.")
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ResumeParseError("DOCX is corrupted or is not a Word document.") from exc


def _read_docx(blob: bytes) -> tuple[str, None]:
    _validate_docx(blob)
    try:
        document = Document(io.BytesIO(blob))
        header_lines: list[str] = []
        footer_lines: list[str] = []
        for section in document.sections:
            header_lines.extend(_iter_docx_blocks(section.header.iter_inner_content()))
            footer_lines.extend(_iter_docx_blocks(section.footer.iter_inner_content()))
        # Usually documents have only one section; remove duplicate repeated headers/footers.
        header_lines = list(dict.fromkeys(header_lines))
        footer_lines = list(dict.fromkeys(footer_lines))
        body_lines = list(_iter_docx_blocks(document.iter_inner_content()))
    except (ValueError, KeyError, RuntimeError, TypeError, zipfile.BadZipFile) as exc:
        raise ResumeParseError("DOCX is corrupted or cannot be read.") from exc
    return _clean_text("\n".join(header_lines + body_lines + footer_lines)), None


def parse_resume(filename: str, blob: bytes) -> ResumeParseResponse:
    """Validate and parse a resume. The bytes are not persisted by this service."""
    safe_filename = Path((filename or "").replace("\\", "/")).name
    suffix = Path(safe_filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ResumeParseError("Upload a .pdf or .docx resume.", status_code=415)
    if not blob:
        raise ResumeParseError("The uploaded file is empty.", status_code=400)
    if len(blob) > MAX_UPLOAD_BYTES:
        raise ResumeParseError("Resume exceeds the 8 MB upload limit.", status_code=413)

    if suffix == ".pdf":
        raw_text, page_count = _read_pdf(blob)
    else:
        raw_text, page_count = _read_docx(blob)

    warnings: list[str] = []
    if not raw_text:
        warnings.append(
            "No selectable text was found. Image-only or scanned documents need OCR "
            "(not enabled in Phase 1)."
        )
    elif len(raw_text) < 150:
        warnings.append("Very little text was extracted; review the source file.")

    # Warning only: do not silently rewrite a user's resume.
    if re.search(
        r"(?i)(?:your current resume already documents|"
        r"the existing resume already includes|"
        r"the original resume already documents)", raw_text
    ):
        warnings.append("Possible resume-editing commentary detected; review the source document.")

    return ResumeParseResponse(
        file_name=safe_filename,
        file_type="pdf" if suffix == ".pdf" else "docx",
        page_count=page_count,
        characters=len(raw_text),
        word_count=len(re.findall(r"\S+", raw_text)),
        raw_text=raw_text,
        warnings=warnings,
    )
