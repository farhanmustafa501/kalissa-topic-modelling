"""
Tests for configuration.
"""
from unittest.mock import patch

import pytest

from app.config import get_config


@pytest.mark.unit
class TestConfig:
    """Tests for configuration functions."""

    def test_get_config_defaults(self):
        """Test getting config with default values."""
        with patch.dict('os.environ', {}, clear=True):
            config = get_config()
            assert 'SECRET_KEY' in config
            assert 'DATABASE_URL' in config
            assert 'OPENAI_API_KEY' in config
            assert config['SECRET_KEY'] == "dev-secret-change-me"

    def test_get_config_from_env(self):
        """Test getting config from environment variables."""
        with patch.dict('os.environ', {
            'SECRET_KEY': 'test-secret',
            'DATABASE_URL': 'postgresql://test',
            'OPENAI_API_KEY': 'test-key',
            'OPENAI_EMBEDDING_MODEL': 'text-embedding-3-large',
            'OPENAI_EMBEDDING_DIM': '3072',
            'OPENAI_MAX_INPUT_CHARS': '16000'
        }):
            config = get_config()
            assert config['SECRET_KEY'] == 'test-secret'
            assert config['DATABASE_URL'] == 'postgresql://test'
            assert config['OPENAI_API_KEY'] == 'test-key'
            assert config['OPENAI_EMBEDDING_MODEL'] == 'text-embedding-3-large'
            assert config['OPENAI_EMBEDDING_DIM'] == 3072
            assert config['OPENAI_MAX_INPUT_CHARS'] == 16000

    def test_get_config_int_conversion(self):
        """Test that integer config values are converted."""
        with patch.dict('os.environ', {
            'OPENAI_EMBEDDING_DIM': '1536',
            'OPENAI_MAX_INPUT_CHARS': '8000'
        }):
            config = get_config()
            assert isinstance(config['OPENAI_EMBEDDING_DIM'], int)
            assert isinstance(config['OPENAI_MAX_INPUT_CHARS'], int)

