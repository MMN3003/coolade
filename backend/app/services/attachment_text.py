"""Best-effort text sidecars for chat attachments.

The headless CLI can Read text, images and PDFs itself, but it has no Bash and
cannot open Office/zip-style binaries. For those we write ``<file>.txt`` next to
the upload (tables as TSV, one sheet/section per block) so the model can still
work with the content. Everything here is best-effort: any failure is logged and
the original file is kept untouched.
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

logger = logging.getLogger("coolade.attachment_text")

SIDECAR_SUFFIX = ".txt"
# Only formats the CLI cannot read on its own get a sidecar.
_SIDECAR_EXTS = {".xlsx", ".xlsm", ".docx", ".pptx"}
_MAX_SIDECAR_CHARS = 400_000  # ~100k tokens; beyond that the head is enough


def sidecar_for(path: Path) -> Path | None:
    if path.suffix.lower() not in _SIDECAR_EXTS:
        return None
    return path.with_name(path.name + SIDECAR_SUFFIX)


def sidecar_path(storage_relpath: str) -> str | None:
    """Relative sidecar path for the prompt note, or None when no sidecar applies."""
    p = Path(storage_relpath)
    return f"{storage_relpath}{SIDECAR_SUFFIX}" if p.suffix.lower() in _SIDECAR_EXTS else None


def _xlsx_text(path: Path) -> str:
    from openpyxl import load_workbook  # lazy: optional dependency

    wb = load_workbook(path, read_only=True, data_only=True)
    out = io.StringIO()
    for ws in wb.worksheets:
        out.write(f"### sheet: {ws.title}\n")
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        for row in ws.iter_rows(values_only=True):
            if row is None or all(c is None for c in row):
                continue
            writer.writerow(["" if c is None else str(c) for c in row])
        out.write("\n")
        if out.tell() > _MAX_SIDECAR_CHARS:
            out.write("… (truncated)\n")
            break
    return out.getvalue()


def _docx_text(path: Path) -> str:
    from docx import Document  # lazy: optional dependency

    doc = Document(str(path))
    parts: list[str] = [p.text for p in doc.paragraphs]
    for ti, table in enumerate(doc.tables, 1):
        parts.append(f"\n### table {ti}")
        for row in table.rows:
            parts.append("\t".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts)


def _pptx_text(path: Path) -> str:
    from pptx import Presentation  # lazy: optional dependency

    prs = Presentation(str(path))
    parts: list[str] = []
    for i, slide in enumerate(prs.slides, 1):
        parts.append(f"### slide {i}")
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text)
        parts.append("")
    return "\n".join(parts)


_EXTRACTORS = {
    ".xlsx": _xlsx_text,
    ".xlsm": _xlsx_text,
    ".docx": _docx_text,
    ".pptx": _pptx_text,
}


def write_sidecar(path: Path) -> Path | None:
    """Write the text sidecar for `path` if its format has an extractor. Never raises."""
    target = sidecar_for(path)
    if target is None:
        return None
    try:
        text = _EXTRACTORS[path.suffix.lower()](path)
        if len(text) > _MAX_SIDECAR_CHARS:
            text = text[:_MAX_SIDECAR_CHARS] + "\n… (truncated)\n"
        target.write_text(text, encoding="utf-8")
        return target
    except Exception:  # noqa: BLE001 — best-effort by design
        logger.warning("sidecar extraction failed for %s", path.name, exc_info=True)
        return None
