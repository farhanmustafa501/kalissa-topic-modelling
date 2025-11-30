from __future__ import annotations

import io
import os
import logging
from typing import Tuple

from pypdf import PdfReader
from docx import Document as DocxDocument

logger = logging.getLogger(__name__)


def _safe_decode(data: bytes) -> str:
	try:
		return data.decode("utf-8")
	except Exception:
		try:
			return data.decode("latin-1")
		except Exception:
			return ""


def extract_text_from_upload(filename: str, file_bytes: bytes) -> Tuple[str, str]:
	"""
	Extract text content from uploaded file bytes.
	Returns (title, text).
	Supported: .txt, .md, .pdf, .docx
	"""
	title = os.path.basename(filename or "").strip() or "Untitled"
	lower = title.lower()
	logger.info("extract_text_from_upload", extra={"upload_filename": title, "upload_size": len(file_bytes)})

	if lower.endswith(".pdf"):
		text_parts = []
		reader = PdfReader(io.BytesIO(file_bytes))
		for page in reader.pages:
			try:
				chunk = page.extract_text() or ""
			except Exception:
				logger.exception("pdf extract failed for page")
				chunk = ""
			if chunk:
				text_parts.append(chunk)
		return title, "\n".join(text_parts).strip()

	if lower.endswith(".docx"):
		text_parts = []
		doc = DocxDocument(io.BytesIO(file_bytes))
		for p in doc.paragraphs:
			t = (p.text or "").strip()
			if t:
				text_parts.append(t)
		return title, "\n".join(text_parts).strip()

	# Fallback: treat as plain text (txt/md/unknown)
	return title, _safe_decode(file_bytes).strip()


