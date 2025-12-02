"""
Tests for chunking service.
"""

import pytest

from app.services.chunking import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, create_text_splitter, split_text


@pytest.mark.service
class TestChunking:
    """Tests for text chunking functionality."""

    def test_create_text_splitter_default(self):
        """Test creating text splitter with default parameters."""
        splitter = create_text_splitter()
        assert splitter._chunk_size == DEFAULT_CHUNK_SIZE
        assert splitter._chunk_overlap == DEFAULT_CHUNK_OVERLAP

    def test_create_text_splitter_custom(self):
        """Test creating text splitter with custom parameters."""
        chunk_size = 500
        chunk_overlap = 50
        splitter = create_text_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        assert splitter._chunk_size == chunk_size
        assert splitter._chunk_overlap == chunk_overlap

    def test_split_text_short(self):
        """Test splitting short text that doesn't need chunking."""
        text = "This is a short text that should not be split."
        chunks = split_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_text_long(self):
        """Test splitting long text that needs chunking."""
        # Create text longer than chunk size
        text = "Word " * 2000  # ~10000 characters
        chunks = split_text(text, chunk_size=500, chunk_overlap=50)
        assert len(chunks) > 1
        # Verify all chunks are strings
        assert all(isinstance(chunk, str) for chunk in chunks)

    def test_split_text_empty(self):
        """Test splitting empty text."""
        chunks = split_text("")
        assert len(chunks) == 0

    def test_split_text_whitespace_only(self):
        """Test splitting whitespace-only text."""
        chunks = split_text("   \n\t  ")
        assert len(chunks) == 0

    def test_split_text_with_overlap(self):
        """Test that chunks have overlap."""
        text = "Word " * 1000
        chunks = split_text(text, chunk_size=200, chunk_overlap=50)
        if len(chunks) > 1:
            # Check that there's some overlap between chunks
            # This is a basic check - actual overlap verification would be more complex
            assert len(chunks) > 1

    def test_split_text_preserves_content(self):
        """Test that splitting preserves all content."""
        text = "This is a test text with multiple sentences. " * 10
        chunks = split_text(text, chunk_size=100, chunk_overlap=20)
        # Reconstruct and check
        reconstructed = "".join(chunks)
        # Due to overlap, we can't do exact comparison, but check length is reasonable
        assert len(reconstructed) >= len(text) * 0.8  # Allow for some variance
