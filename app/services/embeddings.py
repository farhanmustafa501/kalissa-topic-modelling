"""
Embedding service using OpenAI's text-embedding-3-small model.

This module handles generating embeddings for text chunks using OpenAI's API.
Supports both single and batch embedding generation for efficiency.
"""

from __future__ import annotations

import logging
import os

import httpx
import numpy as np
from openai import OpenAI

logger = logging.getLogger(__name__)

# Embedding dimension for text-embedding-3-small
EMBEDDING_DIM = 1536


def _truncate_for_openai(text: str) -> str:
	"""
	Truncate text to maximum input length for OpenAI API.
	
	Args:
		text: Text to truncate
		
	Returns:
		Truncated text
	"""
	max_chars = int(os.getenv("OPENAI_MAX_INPUT_CHARS") or "8000")
	text = text or ""
	if len(text) > max_chars:
		logger.warning(
			"Truncating text for embedding",
			extra={"original_length": len(text), "truncated_length": max_chars}
		)
		return text[:max_chars]
	return text


def _get_openai_client() -> OpenAI:
	"""
	Get configured OpenAI client.
	
	Returns:
		OpenAI client instance
		
	Raises:
		RuntimeError: If OPENAI_API_KEY is not set
	"""
	api_key = os.getenv("OPENAI_API_KEY") or ""
	if not api_key:
		raise RuntimeError("OPENAI_API_KEY is not set")

	model = os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"

	# Provide explicit httpx client to avoid proxy issues in certain environments
	http_client = httpx.Client(timeout=60.0)  # Increased timeout for batch requests
	client = OpenAI(api_key=api_key, http_client=http_client)

	return client


def _normalize_embedding(embedding: list[float]) -> list[float]:
	"""
	Normalize embedding vector to ensure correct dimensionality.
	
	Args:
		embedding: Raw embedding vector
		
	Returns:
		Normalized embedding vector of length EMBEDDING_DIM
	"""
	if not isinstance(embedding, list):
		embedding = list(embedding)

	arr = np.array(embedding, dtype=np.float32).ravel()

	# Pad or truncate to correct dimension
	if arr.size < EMBEDDING_DIM:
		arr = np.pad(arr, (0, EMBEDDING_DIM - arr.size), mode="constant")
	elif arr.size > EMBEDDING_DIM:
		logger.warning(
			"Embedding dimension larger than expected, truncating",
			extra={"original_dim": arr.size, "expected_dim": EMBEDDING_DIM}
		)
		arr = arr[:EMBEDDING_DIM]

	return arr.tolist()


def get_embeddings_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
	"""
	Generate embeddings for multiple texts in batches.
	
	This function processes texts in batches to efficiently generate embeddings
	for large numbers of chunks. Uses OpenAI's batch API when possible.
	
	Args:
		texts: List of texts to embed
		batch_size: Number of texts to process in each batch (default: 100)
		
	Returns:
		List of embedding vectors, one per input text
		
	Raises:
		RuntimeError: If OPENAI_API_KEY is not set or API call fails
	"""
	if not texts:
		logger.warning("Attempted to embed empty text list")
		return []

	client = _get_openai_client()
	model = os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"

	# Prepare texts (truncate and filter empty)
	prepared_texts = []
	original_indices = []
	for i, text in enumerate(texts):
		if text and text.strip():
			prepared_texts.append(_truncate_for_openai(text))
			original_indices.append(i)

	if not prepared_texts:
		logger.warning("No valid texts to embed after filtering")
		return [[] for _ in texts]

	all_embeddings = []

	try:
		# Process in batches
		for batch_start in range(0, len(prepared_texts), batch_size):
			batch = prepared_texts[batch_start:batch_start + batch_size]
			logger.info(
				"Generating embeddings batch",
				extra={"batch_num": (batch_start // batch_size) + 1, "batch_size": len(batch), "total_texts": len(prepared_texts)}
			)

			resp = client.embeddings.create(model=model, input=batch)

			# Extract embeddings in order
			batch_embeddings = []
			for item in resp.data:
				vec = item.embedding or []
				batch_embeddings.append(_normalize_embedding(vec))

			all_embeddings.extend(batch_embeddings)

		# Map back to original indices (fill empty texts with zero vectors)
		result = []
		embedding_idx = 0
		for i in range(len(texts)):
			if i in original_indices:
				result.append(all_embeddings[embedding_idx])
				embedding_idx += 1
			else:
				result.append([0.0] * EMBEDDING_DIM)

		logger.info(
			"Batch embedding generation completed",
			extra={"total_texts": len(texts), "valid_texts": len(prepared_texts), "embeddings_generated": len(all_embeddings)}
		)

		return result
	except Exception as e:
		logger.exception("Failed to generate batch embeddings", extra={"error": str(e), "num_texts": len(texts)})
		raise RuntimeError(f"Failed to generate batch embeddings: {e!s}") from e


