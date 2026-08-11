"""
Utilities for turning uploaded files (PDFs, images, memo docs, class lists)
into formats usable by the grading pipeline.
"""
from __future__ import annotations
import base64
import io
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd
from PIL import Image

MAX_IMAGE_DIMENSION = 2000  # keep payloads reasonable for the Vision API


def _resize_if_needed(img: Image.Image) -> Image.Image:
    if max(img.size) <= MAX_IMAGE_DIMENSION:
        return img
    ratio = MAX_IMAGE_DIMENSION / max(img.size)
    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
    return img.resize(new_size, Image.LANCZOS)


def image_to_base64_jpeg(img: Image.Image) -> str:
    if img.mode != "RGB":
        img = img.convert("RGB")
    img = _resize_if_needed(img)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def pdf_to_page_images_base64(pdf_path: str | Path) -> list[str]:
    """Render every page of a PDF to a base64 JPEG string."""
    images = []
    doc = fitz.open(str(pdf_path))
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for clarity
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            images.append(image_to_base64_jpeg(img))
    finally:
        doc.close()
    return images


def pdf_to_text(pdf_path: str | Path) -> str:
    """Extract raw text from a PDF (used for the memo when it's text-based)."""
    doc = fitz.open(str(pdf_path))
    try:
        text_parts = [page.get_text() for page in doc]
    finally:
        doc.close()
    return "\n".join(text_parts).strip()


def file_to_base64_images(file_path: str | Path) -> list[str]:
    """
    Convert an uploaded student paper (image or PDF, single or multi-page)
    into a list of base64-encoded JPEG page images.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return pdf_to_page_images_base64(path)
    elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"):
        img = Image.open(path)
        return [image_to_base64_jpeg(img)]
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def parse_memo(file_path: str | Path) -> str:
    """
    Parse a memo (marking guideline) PDF into text. If the PDF has no
    extractable text (i.e. it's a scan), fall back to noting that vision
    parsing will be needed and return page images marker instead.
    """
    path = Path(file_path)
    text = pdf_to_text(path)
    if len(text) > 50:
        return text
    # Scanned memo with no text layer - signal caller to use vision fallback
    return ""


def parse_class_list(file_path: str | Path) -> list[dict]:
    """
    Parse an Excel or CSV class list into a list of {name, student_number} dicts.
    Tries to intelligently detect the name column.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)

    df.columns = [str(c).strip().lower() for c in df.columns]

    name_col = None
    for candidate in ["name", "full name", "student name", "learner name", "surname"]:
        if candidate in df.columns:
            name_col = candidate
            break
    if name_col is None:
        # fall back to first column
        name_col = df.columns[0]

    number_col = None
    for candidate in ["student number", "learner number", "id", "admission number", "student no"]:
        if candidate in df.columns:
            number_col = candidate
            break

    students = []
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        if not name or name.lower() == "nan":
            continue
        number = None
        if number_col is not None:
            raw_number = row[number_col]
            if pd.notna(raw_number):
                number = str(raw_number).strip()
        students.append({"name": name, "student_number": number})

    return students
