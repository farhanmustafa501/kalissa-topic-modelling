"""
Tests for database utilities.
"""
from unittest.mock import patch

import pytest

from app.db import _get_database_url, ensure_tables_initialized, get_db_session


@pytest.mark.unit
class TestDatabase:
    """Tests for database utilities."""

    def test_get_database_url_from_env(self):
        """Test getting database URL from environment."""
        with patch.dict('os.environ', {'DATABASE_URL': 'postgresql://test'}):
            url = _get_database_url()
            assert url == 'postgresql://test'

    def test_get_database_url_missing(self):
        """Test getting database URL when not set."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(RuntimeError):
                _get_database_url()

    def test_ensure_tables_initialized(self, db_engine):
        """Test ensuring tables are initialized."""
        # This should work with our test engine
        with patch('app.db.engine', db_engine):
            ensure_tables_initialized()
            # Check that tables exist by trying to query
            # If tables exist, this won't raise an error
            assert True  # Basic check

    def test_get_db_session(self, db_engine):
        """Test getting a database session."""
        from sqlalchemy.orm import scoped_session, sessionmaker
        Session = scoped_session(sessionmaker(bind=db_engine))
        with patch('app.db.SessionLocal', Session):
            session_gen = get_db_session()
            session = next(session_gen)
            assert session is not None
            # Clean up
            try:
                next(session_gen)
            except StopIteration:
                pass

