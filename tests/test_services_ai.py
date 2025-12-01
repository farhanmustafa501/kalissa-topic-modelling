"""
Tests for AI service.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.services.ai import _get_client, answer_question_with_citations, generate_topic_insights, generate_topic_name


@pytest.mark.service
class TestAIService:
    """Tests for AI service functions."""

    @patch('app.services.ai._get_client')
    def test_generate_topic_name_with_client(self, mock_get_client):
        """Test generating topic name with OpenAI client."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"name": "Test Topic", "summary": "Test summary", "keywords": ["test", "topic"]}'
        mock_client.chat.completions.create.return_value = mock_response

        chunks = ["Representative chunk 1", "Representative chunk 2"]
        result = generate_topic_name(chunks)

        assert result['name'] == "Test Topic"
        assert result['summary'] == "Test summary"
        assert 'keywords' in result

    def test_generate_topic_name_no_client(self):
        """Test generating topic name without OpenAI client."""
        with patch('app.services.ai._get_client', return_value=None):
            chunks = ["This is a test chunk with some content"]
            result = generate_topic_name(chunks)

            assert 'name' in result
            assert 'summary' in result
            assert 'keywords' in result
            assert result['name'] != ""

    @patch('app.services.ai._get_client')
    def test_generate_topic_insights_with_client(self, mock_get_client):
        """Test generating topic insights with OpenAI client."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"summary": "Test summary", "themes": ["theme1"], "questions": ["q1"], "related_concepts": ["concept1"]}'
        mock_client.chat.completions.create.return_value = mock_response

        chunks = ["Representative chunk 1"]
        result = generate_topic_insights(chunks, "Test Topic")

        assert 'summary' in result
        assert 'themes' in result
        assert 'questions' in result
        assert 'related_concepts' in result

    def test_generate_topic_insights_no_client(self):
        """Test generating topic insights without OpenAI client."""
        with patch('app.services.ai._get_client', return_value=None):
            chunks = ["Test chunk"]
            result = generate_topic_insights(chunks, "Test Topic")

            assert 'summary' in result
            assert 'themes' in result
            assert 'questions' in result

    @patch('app.services.ai._get_client')
    def test_answer_question_with_citations(self, mock_get_client):
        """Test answering question with citations."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is the answer [D1-C0]."
        mock_client.chat.completions.create.return_value = mock_response

        question = "What is this about?"
        chunks = [
            {
                "id": "D1-C0",
                "text": "Test chunk text",
                "document_id": 1,
                "title": "Test Document"
            }
        ]

        result = answer_question_with_citations(question, chunks)

        assert 'qa-answer' in result
        assert 'citation' in result
        assert 'data-doc-id' in result

    def test_answer_question_no_client(self):
        """Test answering question without OpenAI client."""
        with patch('app.services.ai._get_client', return_value=None):
            question = "Test question"
            chunks = []
            result = answer_question_with_citations(question, chunks)

            assert "unavailable" in result.lower() or "no relevant" in result.lower()

    def test_answer_question_empty_question(self):
        """Test answering with empty question."""
        result = answer_question_with_citations("", [])
        assert "provide a question" in result.lower()

    def test_answer_question_no_chunks(self):
        """Test answering with no chunks."""
        with patch('app.services.ai._get_client', return_value=MagicMock()):
            result = answer_question_with_citations("Test question", [])
            assert "no relevant" in result.lower() or "unavailable" in result.lower()

    def test_get_client_with_key(self):
        """Test getting OpenAI client with API key."""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('app.services.ai.OpenAI') as mock_openai:
                client = _get_client()
                # Should attempt to create client
                assert client is not None or mock_openai.called

    def test_get_client_without_key(self):
        """Test getting OpenAI client without API key."""
        with patch.dict('os.environ', {}, clear=True):
            client = _get_client()
            assert client is None

    @patch('app.services.ai._get_client')
    def test_generate_topic_name_exception(self, mock_get_client):
        """Test generate_topic_name with exception."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        chunks = ["Test chunk"]
        result = generate_topic_name(chunks)

        # Should return fallback result
        assert 'name' in result
        assert 'summary' in result
        assert 'keywords' in result

    @patch('app.services.ai._get_client')
    def test_generate_topic_insights_exception(self, mock_get_client):
        """Test generate_topic_insights with exception."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        chunks = ["Test chunk"]
        result = generate_topic_insights(chunks, "Test Topic")

        # Should return fallback result
        assert 'summary' in result
        assert 'themes' in result
        assert 'questions' in result
        assert 'related_concepts' in result

    @patch('app.services.ai._get_client')
    def test_answer_question_exception(self, mock_get_client):
        """Test answer_question_with_citations with exception."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        question = "Test question"
        chunks = [{"id": "D1-C0", "text": "Test", "document_id": 1, "title": "Test"}]
        result = answer_question_with_citations(question, chunks)

        # Should return error message
        assert 'qa-answer' in result
        assert 'Unable to generate' in result or 'error' in result.lower()

    @patch('app.services.ai._get_client')
    def test_answer_question_citation_no_doc_id(self, mock_get_client):
        """Test citation replacement when chunk has no document_id."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Answer [D1-C0]."
        mock_client.chat.completions.create.return_value = mock_response

        question = "Test"
        chunks = [{"id": "D1-C0", "text": "Test", "title": "Test"}]  # No document_id
        result = answer_question_with_citations(question, chunks)

        # Should still process but citation might not have doc-id
        assert 'qa-answer' in result

