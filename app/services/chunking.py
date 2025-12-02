"""
Text chunking service using RecursiveCharacterTextSplitter.

This module handles splitting documents into smaller chunks suitable for embedding.
Chunks are sized at 800-1200 tokens with 100-200 token overlap to maintain context.
"""

import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# Default chunking parameters (can be overridden via environment variables)
DEFAULT_CHUNK_SIZE = 1200  # ~800-1200 tokens (assuming ~4 chars per token)
DEFAULT_CHUNK_OVERLAP = 150  # ~100-200 tokens overlap


def create_text_splitter(chunk_size: int = None, chunk_overlap: int = None) -> RecursiveCharacterTextSplitter:
    """
    Create a RecursiveCharacterTextSplitter with configured parameters.

    Args:
            chunk_size: Maximum size of each chunk in characters (default: 1200)
            chunk_overlap: Overlap between chunks in characters (default: 150)

    Returns:
            Configured RecursiveCharacterTextSplitter instance
    """
    if chunk_size is None:
        chunk_size = DEFAULT_CHUNK_SIZE
    if chunk_overlap is None:
        chunk_overlap = DEFAULT_CHUNK_OVERLAP

    logger.debug("Creating text splitter", extra={"chunk_size": chunk_size, "chunk_overlap": chunk_overlap})

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False,
    )


def split_text(text: str, chunk_size: int = None, chunk_overlap: int = None) -> list[str]:
    """
    Split text into chunks using RecursiveCharacterTextSplitter.

    This function takes a document's text content and splits it into smaller chunks
    that are suitable for embedding. Each chunk is identified with a format like "D1-C1", "D1-C2".

    Args:
            text: The full text content to split
            chunk_size: Maximum size of each chunk in characters (default: 1200)
            chunk_overlap: Overlap between chunks in characters (default: 150)

    Returns:
            List of text chunks
    """
    if not text or not text.strip():
        logger.warning("Attempted to split empty text")
        return []

    splitter = create_text_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_text(text)

    logger.info(
        "Text split into chunks",
        extra={
            "original_length": len(text),
            "num_chunks": len(chunks),
            "avg_chunk_size": sum(len(c) for c in chunks) / len(chunks) if chunks else 0,
        },
    )

    return chunks
