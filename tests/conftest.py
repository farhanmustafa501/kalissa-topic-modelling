"""
Pytest configuration and fixtures for testing.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool

# Set DATABASE_URL before importing app to avoid import-time errors
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app
from app.db import Base
from app.models import (
    Chunk,
    Collection,
    DiscoveryJob,
    Document,
    JobStatusEnum,
    Topic,
)


@pytest.fixture(scope="session")
def test_db_url():
    """Get test database URL or use in-memory SQLite."""
    db_url = os.getenv("TEST_DATABASE_URL")
    if db_url:
        return db_url
    # Use in-memory SQLite for testing (note: pgvector features won't work)
    return "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_engine(test_db_url):
    """Create a test database engine."""
    if test_db_url.startswith("sqlite"):
        engine = create_engine(test_db_url, connect_args={"check_same_thread": False}, poolclass=StaticPool, echo=False)
    else:
        engine = create_engine(test_db_url, echo=False)

    # Create all tables
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a test database session."""
    Session = scoped_session(sessionmaker(bind=db_engine, autoflush=False, autocommit=False))
    yield Session
    Session.remove()


@pytest.fixture(scope="function")
def app(db_session):
    """Create a Flask test app with test database."""
    # Mock the SessionLocal to use our test session
    with patch("app.db.SessionLocal", db_session):
        with patch("app.api.routes.SessionLocal", db_session):
            app = create_app()
            app.config["TESTING"] = True
            app.config["WTF_CSRF_ENABLED"] = False
            yield app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def sample_collection(db_session):
    """Create a sample collection for testing."""
    collection = Collection(name="Test Collection", description="Test description")
    db_session.add(collection)
    db_session.commit()
    db_session.refresh(collection)
    return collection


@pytest.fixture
def sample_document(db_session, sample_collection):
    """Create a sample document for testing."""
    document = Document(
        collection_id=sample_collection.id,
        title="Test Document",
        content="This is test content for the document.",
        preview="This is test content...",
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


@pytest.fixture
def sample_topic(db_session, sample_collection):
    """Create a sample topic for testing."""
    topic = Topic(collection_id=sample_collection.id, name="Test Topic", document_count=1, size_score=0.5)
    db_session.add(topic)
    db_session.commit()
    db_session.refresh(topic)
    return topic


@pytest.fixture
def sample_discovery_job(db_session, sample_collection):
    """Create a sample discovery job for testing."""
    job = DiscoveryJob(
        collection_id=sample_collection.id,
        status=JobStatusEnum.PENDING,
        mode="FULL",
        progress_step=0,
        progress_total_steps=10,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing."""
    with patch("app.services.ai._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Default mock responses
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = (
            '{"name": "Test Topic", "summary": "Test summary", "keywords": ["test"]}'
        )
        mock_client.chat.completions.create.return_value = mock_completion

        yield mock_client


@pytest.fixture
def mock_embedding_response():
    """Mock OpenAI embedding response."""
    return {"data": [{"embedding": [0.1] * 1536}]}  # Mock 1536-dimensional embedding


@pytest.fixture
def sample_chunks(db_session, sample_document):
    """Create sample chunks for testing."""
    chunks = []
    for i in range(3):
        chunk = Chunk(document_id=sample_document.id, chunk_index=i, text=f"Test chunk {i} content")
        db_session.add(chunk)
        chunks.append(chunk)
    db_session.commit()
    for chunk in chunks:
        db_session.refresh(chunk)
    return chunks
