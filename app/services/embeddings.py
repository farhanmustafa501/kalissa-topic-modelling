from __future__ import annotations

import hashlib
import os
import logging
from typing import List

import numpy as np


EMBEDDING_DIM = 1536
logger = logging.getLogger(__name__)


def _seed_from_text(text: str) -> int:
	h = hashlib.sha256((text or "").encode("utf-8")).digest()
	return int.from_bytes(h[:8], byteorder="big", signed=False) & 0x7FFFFFFF


def _truncate_for_openai(text: str) -> str:
	max_chars = int(os.getenv("OPENAI_MAX_INPUT_CHARS") or "8000")
	text = text or ""
	return text if len(text) <= max_chars else text[:max_chars]


def get_embedding_for_text(text: str) -> List[float]:
	"""
	Generate embeddings using OpenAI Embeddings API.
	Requires OPENAI_API_KEY and OPENAI_EMBEDDING_MODEL; raises on failure.
	"""
	from openai import OpenAI
	import httpx

	api_key = os.getenv("OPENAI_API_KEY") or ""
	if not api_key:
		raise RuntimeError("OPENAI_API_KEY is not set")
	model = os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"

	# Provide explicit httpx client to avoid proxies kw issues in certain environments
	http_client = httpx.Client(timeout=30.0)
	client = OpenAI(api_key=api_key, http_client=http_client)

	prepared = _truncate_for_openai(text)
	resp = client.embeddings.create(model=model, input=prepared)
	vec = (resp.data[0].embedding or [])
	if not isinstance(vec, list):
		vec = list(vec)
	# Ensure correct dimensionality
	arr = np.array(vec, dtype=np.float32).ravel()
	if arr.size < EMBEDDING_DIM:
		arr = np.pad(arr, (0, EMBEDDING_DIM - arr.size))
	elif arr.size > EMBEDDING_DIM:
		arr = arr[:EMBEDDING_DIM]
	return arr.tolist()


