"""Operational limits for resume ingestion (Phases 1/2)."""

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_DOCX_UNCOMPRESSED_BYTES = 40 * 1024 * 1024
MAX_DOCX_MEMBERS = 500
SUPPORTED_EXTENSIONS = {".pdf", ".docx"}
