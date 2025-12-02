"""
Tests for embeddings service.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.embeddings import (
    EMBEDDING_DIM,
    _get_openai_client,
    _normalize_embedding,
    _truncate_for_openai,
    get_embeddings_batch,
)


@pytest.mark.service
class TestEmbeddings:
    """Tests for embedding generation."""

    def test_truncate_for_openai_short(self):
        """Test truncation with short text."""
        text = "Short text"
        result = _truncate_for_openai(text)
        assert result == text

    def test_truncate_for_openai_long(self):
        """Test truncation with long text."""
        with patch.dict("os.environ", {"OPENAI_MAX_INPUT_CHARS": "100"}):
            text = "Word " * 50  # ~250 characters
            result = _truncate_for_openai(text)
            assert len(result) <= 100

    def test_truncate_for_openai_empty(self):
        """Test truncation with empty text."""
        result = _truncate_for_openai("")
        assert result == ""

    def test_truncate_for_openai_none(self):
        """Test truncation with None."""
        result = _truncate_for_openai(None)
        assert result == ""

    @patch("app.services.embeddings._get_openai_client")
    def test_generate_embedding_success(self, mock_get_client):
        """Test generating a single embedding using batch function."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_embedding = [0.1] * EMBEDDING_DIM
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = mock_embedding
        mock_client.embeddings.create.return_value = mock_response

        # Use get_embeddings_batch with a single text
        results = get_embeddings_batch(["Test text"])

        assert results is not None
        assert len(results) == 1
        result = results[0]
        assert len(result) == EMBEDDING_DIM
        assert all(isinstance(x, float) for x in result)

    @patch("app.services.embeddings._get_openai_client")
    def test_generate_embedding_error(self, mock_get_client):
        """Test generating embedding with error."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.embeddings.create.side_effect = Exception("API Error")

        with pytest.raises(RuntimeError):
            get_embeddings_batch(["Test text"])

    @patch("app.services.embeddings._get_openai_client")
    def test_generate_embeddings_batch(self, mock_get_client):
        """Test generating embeddings in batch."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_embedding = [0.1] * EMBEDDING_DIM
        mock_response = MagicMock()
        mock_response.data = [MagicMock() for _ in range(3)]
        for item in mock_response.data:
            item.embedding = mock_embedding
        mock_client.embeddings.create.return_value = mock_response

        texts = ["Text 1", "Text 2", "Text 3"]
        results = get_embeddings_batch(texts)

        assert len(results) == 3
        assert all(result is not None for result in results)
        assert all(len(result) == EMBEDDING_DIM for result in results)

    @patch("app.services.embeddings._get_openai_client")
    def test_generate_embeddings_batch_empty(self, mock_get_client):
        """Test generating embeddings with empty batch."""
        results = get_embeddings_batch([])
        assert results == []

    def test_get_openai_client_with_key(self):
        """Test getting OpenAI client with API key."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("app.services.embeddings.OpenAI") as mock_openai:
                client = _get_openai_client()
                # Should attempt to create client
                assert client is not None or mock_openai.called

    def test_get_openai_client_without_key(self):
        """Test getting OpenAI client without API key."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError):
                _get_openai_client()

    def test_normalize_embedding_correct_size(self):
        """Test normalizing embedding with correct size."""
        embedding = [0.1] * EMBEDDING_DIM
        result = _normalize_embedding(embedding)
        assert len(result) == EMBEDDING_DIM
        # Use approximate comparison due to float32 precision
        import numpy as np

        assert np.allclose(result, embedding, rtol=1e-6)

    def test_normalize_embedding_too_small(self):
        """Test normalizing embedding that's too small."""
        embedding = [0.1] * 100
        result = _normalize_embedding(embedding)
        assert len(result) == EMBEDDING_DIM
        # Use approximate comparison due to float32 precision
        import numpy as np

        assert np.allclose(result[:100], embedding, rtol=1e-6)
        assert np.allclose(result[100:], [0.0] * (EMBEDDING_DIM - 100), rtol=1e-6)

    def test_normalize_embedding_too_large(self):
        """Test normalizing embedding that's too large."""
        embedding = [0.1] * (EMBEDDING_DIM + 100)
        result = _normalize_embedding(embedding)
        assert len(result) == EMBEDDING_DIM
        # Use approximate comparison due to float32 precision
        import numpy as np

        assert np.allclose(result, embedding[:EMBEDDING_DIM], rtol=1e-6)

    def test_normalize_embedding_not_list(self):
        """Test normalizing embedding that's not a list."""
        import numpy as np

        embedding = np.array([0.1] * EMBEDDING_DIM)
        result = _normalize_embedding(embedding)
        assert len(result) == EMBEDDING_DIM
        assert isinstance(result, list)
