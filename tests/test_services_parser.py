"""
Tests for parser service.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.services.parser import _safe_decode, extract_text_from_upload


@pytest.mark.service
class TestParser:
    """Tests for document parsing."""

    def test_extract_text_txt(self):
        """Test extracting text from .txt file."""
        content = b"This is a test text file content."
        filename = "test.txt"
        title, text = extract_text_from_upload(filename, content)
        assert title == "test"
        assert "test text file" in text

    def test_extract_text_md(self):
        """Test extracting text from .md file."""
        content = b"# Test Document\n\nThis is markdown content."
        filename = "test.md"
        title, text = extract_text_from_upload(filename, content)
        assert title == "test"
        assert "markdown" in text.lower()

    def test_extract_text_pdf(self):
        """Test extracting text from PDF file."""
        # Create a minimal PDF (this is a simplified test)
        # In real scenario, you'd use a proper PDF library
        filename = "test.pdf"
        # For testing, we'll mock or use a simple case
        # Note: pdfplumber requires actual PDF structure
        content = b"%PDF-1.4\n"  # Minimal PDF header
        # This will likely fail parsing but tests the code path
        title, text = extract_text_from_upload(filename, content)
        assert title == "test"

    def test_extract_text_docx(self):
        """Test extracting text from .docx file."""
        filename = "test.docx"
        # docx files are binary, so we need proper structure
        # This is a simplified test
        content = b"PK\x03\x04"  # ZIP header (docx is a ZIP)
        title, text = extract_text_from_upload(filename, content)
        assert title == "test"

    def test_extract_text_unknown_format(self):
        """Test extracting text from unknown format."""
        filename = "test.xyz"
        content = b"Some content"
        title, text = extract_text_from_upload(filename, content)
        assert title == "test"
        # Unknown format is treated as plain text, so it returns the decoded content
        assert "Some content" in text

    def test_safe_decode_utf8(self):
        """Test safe decoding with UTF-8."""
        content = b"Test content"
        result = _safe_decode(content)
        assert result == "Test content"

    def test_safe_decode_latin1(self):
        """Test safe decoding with latin-1 fallback."""
        content = "Test content".encode('latin-1')
        result = _safe_decode(content)
        assert result == "Test content"

    def test_safe_decode_invalid(self):
        """Test safe decoding with invalid bytes."""
        # Create invalid UTF-8 sequence
        content = b'\xff\xfe'
        result = _safe_decode(content)
        # Should return empty string or handle gracefully
        assert isinstance(result, str)

    def test_extract_text_pdf_error(self):
        """Test PDF extraction with invalid PDF."""
        filename = "test.pdf"
        content = b"Not a valid PDF"
        title, text = extract_text_from_upload(filename, content)
        assert title == "test"
        # Should return empty text on parsing failure
        assert text == ""

    def test_extract_text_docx_error(self):
        """Test DOCX extraction with invalid DOCX."""
        filename = "test.docx"
        content = b"Not a valid DOCX"
        title, text = extract_text_from_upload(filename, content)
        assert title == "test"
        # Should return empty text on parsing failure
        assert text == ""

    def test_extract_text_empty_filename(self):
        """Test extraction with empty filename."""
        content = b"Some content"
        title, text = extract_text_from_upload("", content)
        assert title == "Untitled"
        assert "Some content" in text

    def test_extract_text_no_extension(self):
        """Test extraction with filename without extension."""
        content = b"Some content"
        title, text = extract_text_from_upload("testfile", content)
        assert title == "testfile"
        assert "Some content" in text

    @patch('app.services.parser.pdfplumber')
    def test_extract_text_pdf_page_error(self, mock_pdfplumber):
        """Test PDF extraction with page extraction error."""
        # Mock pdfplumber to raise error on page extraction
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.side_effect = Exception("Page error")
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf

        filename = "test.pdf"
        content = b"%PDF-1.4\n"
        title, text = extract_text_from_upload(filename, content)
        assert title == "test"
        # Should continue despite page error
        assert isinstance(text, str)

    @patch('app.services.parser.DocxDocument')
    def test_extract_text_docx_paragraphs(self, mock_docx):
        """Test DOCX extraction with paragraphs."""
        mock_doc = MagicMock()
        mock_para1 = MagicMock()
        mock_para1.text = "First paragraph"
        mock_para2 = MagicMock()
        mock_para2.text = "Second paragraph"
        mock_doc.paragraphs = [mock_para1, mock_para2]
        mock_docx.return_value = mock_doc

        filename = "test.docx"
        content = b"PK\x03\x04"
        title, text = extract_text_from_upload(filename, content)
        assert title == "test"
        assert "First paragraph" in text
        assert "Second paragraph" in text

