"""
PDF and document parsing service.

This module handles extraction of text content from various file formats.
Uses pdfplumber for PDF parsing as recommended for better text extraction.
"""

from __future__ import annotations

import io
import logging
import os

import pdfplumber
from docx import Document as DocxDocument

logger = logging.getLogger(__name__)


def _safe_decode(data: bytes) -> str:
    """
    Safely decode bytes to string, trying UTF-8 first, then latin-1 as fallback.

    Args:
            data: Bytes to decode

    Returns:
            Decoded string, or empty string if decoding fails
    """
    try:
        return data.decode("utf-8")
    except Exception:
        try:
            return data.decode("latin-1")
        except Exception:
            logger.warning("Failed to decode file bytes with UTF-8 and latin-1")
            return ""


def extract_text_from_upload(filename: str, file_bytes: bytes) -> tuple[str, str]:
    """
    Extract text content from uploaded file bytes.

    This function parses various file formats and extracts raw text content.
    Supported formats: .txt, .md, .pdf, .docx

    Args:
            filename: Original filename (used to determine file type)
            file_bytes: Raw file content as bytes

    Returns:
            Tuple of (title, text) where:
            - title: Basename of the file
            - text: Extracted text content
    """
    # Extract title from filename (remove extension)
    full_name = os.path.basename(filename or "").strip() or "Untitled"
    # Remove file extension for cleaner title
    if "." in full_name:
        title = os.path.splitext(full_name)[0]
    else:
        title = full_name
    lower = full_name.lower()
    logger.info(
        "Extracting text from uploaded file",
        extra={
            "upload_filename": title,
            "file_size_bytes": len(file_bytes),
            "extension": lower.split(".")[-1] if "." in lower else "unknown",
        },
    )

    # PDF parsing using pdfplumber (recommended for better text extraction)
    if lower.endswith(".pdf"):
        text_parts = []
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    try:
                        page_text = page.extract_text() or ""
                        if page_text.strip():
                            text_parts.append(page_text)
                    except Exception as e:
                        logger.warning(
                            "Failed to extract text from PDF page", extra={"page_num": page_num, "error": str(e)}
                        )
                        continue
            extracted_text = "\n".join(text_parts).strip()
            logger.info(
                "PDF extraction completed",
                extra={"upload_filename": title, "pages": len(pdf.pages), "text_length": len(extracted_text)},
            )
            return title, extracted_text
        except Exception as e:
            logger.exception("PDF parsing failed", extra={"upload_filename": title, "error": str(e)})
            # Return empty text on failure rather than crashing
            return title, ""

    # DOCX parsing
    if lower.endswith(".docx"):
        text_parts = []
        try:
            doc = DocxDocument(io.BytesIO(file_bytes))
            for paragraph in doc.paragraphs:
                text = (paragraph.text or "").strip()
                if text:
                    text_parts.append(text)
            extracted_text = "\n".join(text_parts).strip()
            logger.info(
                "DOCX extraction completed",
                extra={"upload_filename": title, "paragraphs": len(text_parts), "text_length": len(extracted_text)},
            )
            return title, extracted_text
        except Exception as e:
            logger.exception("DOCX parsing failed", extra={"upload_filename": title, "error": str(e)})
            return title, ""

    # Fallback: treat as plain text (txt/md/unknown)
    decoded_text = _safe_decode(file_bytes).strip()
    logger.info("Plain text extraction completed", extra={"upload_filename": title, "text_length": len(decoded_text)})
    return title, decoded_text
