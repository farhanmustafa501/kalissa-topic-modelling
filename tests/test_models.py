"""
Tests for database models.
"""

import pytest

from app.models import (
    Chunk,
    Collection,
    DiscoveryJob,
    Document,
    DocumentTopic,
    JobStatusEnum,
    Topic,
    TopicInsight,
    TopicRelationship,
)


@pytest.mark.unit
class TestCollection:
    """Tests for Collection model."""

    def test_create_collection(self, db_session):
        """Test creating a collection."""
        collection = Collection(name="Test Collection", description="Test description")
        db_session.add(collection)
        db_session.commit()

        assert collection.id is not None
        assert collection.name == "Test Collection"
        assert collection.description == "Test description"
        assert collection.created_at is not None

    def test_collection_relationships(self, db_session, sample_collection, sample_document, sample_topic):
        """Test collection relationships."""
        db_session.refresh(sample_collection)
        # Check that relationships are accessible
        assert hasattr(sample_collection, "documents")
        assert hasattr(sample_collection, "topics")
        assert hasattr(sample_collection, "discovery_jobs")


@pytest.mark.unit
class TestDocument:
    """Tests for Document model."""

    def test_create_document(self, db_session, sample_collection):
        """Test creating a document."""
        document = Document(
            collection_id=sample_collection.id, title="Test Document", content="Test content", preview="Test preview"
        )
        db_session.add(document)
        db_session.commit()

        assert document.id is not None
        assert document.title == "Test Document"
        assert document.collection_id == sample_collection.id

    def test_document_relationships(self, db_session, sample_document):
        """Test document relationships."""
        db_session.refresh(sample_document)
        assert hasattr(sample_document, "collection")
        assert hasattr(sample_document, "chunks")
        assert hasattr(sample_document, "document_topics")


@pytest.mark.unit
class TestChunk:
    """Tests for Chunk model."""

    def test_create_chunk(self, db_session, sample_document):
        """Test creating a chunk."""
        chunk = Chunk(document_id=sample_document.id, chunk_index=0, text="Test chunk text")
        db_session.add(chunk)
        db_session.commit()

        assert chunk.id is not None
        assert chunk.chunk_index == 0
        assert chunk.text == "Test chunk text"
        assert chunk.document_id == sample_document.id

    def test_chunk_relationship(self, db_session, sample_chunks):
        """Test chunk relationships."""
        chunk = sample_chunks[0]
        db_session.refresh(chunk)
        assert hasattr(chunk, "document")


@pytest.mark.unit
class TestTopic:
    """Tests for Topic model."""

    def test_create_topic(self, db_session, sample_collection):
        """Test creating a topic."""
        topic = Topic(collection_id=sample_collection.id, name="Test Topic", document_count=5, size_score=0.75)
        db_session.add(topic)
        db_session.commit()

        assert topic.id is not None
        assert topic.name == "Test Topic"
        assert topic.document_count == 5
        assert topic.size_score == 0.75

    def test_topic_relationships(self, db_session, sample_topic):
        """Test topic relationships."""
        db_session.refresh(sample_topic)
        assert hasattr(sample_topic, "collection")
        assert hasattr(sample_topic, "insight")
        assert hasattr(sample_topic, "document_topics")


@pytest.mark.unit
class TestDiscoveryJob:
    """Tests for DiscoveryJob model."""

    def test_create_discovery_job(self, db_session, sample_collection):
        """Test creating a discovery job."""
        job = DiscoveryJob(
            collection_id=sample_collection.id,
            status=JobStatusEnum.PENDING,
            mode="FULL",
            progress_step=0,
            progress_total_steps=10,
        )
        db_session.add(job)
        db_session.commit()

        assert job.id is not None
        assert job.status == JobStatusEnum.PENDING
        assert job.mode == "FULL"
        assert job.progress_step == 0

    def test_job_status_enum(self):
        """Test job status enum values."""
        assert JobStatusEnum.PENDING == "PENDING"
        assert JobStatusEnum.RUNNING == "RUNNING"
        assert JobStatusEnum.SUCCEEDED == "SUCCEEDED"
        assert JobStatusEnum.FAILED == "FAILED"


@pytest.mark.unit
class TestDocumentTopic:
    """Tests for DocumentTopic model."""

    def test_create_document_topic(self, db_session, sample_document, sample_topic):
        """Test creating a document-topic relationship."""
        doc_topic = DocumentTopic(
            document_id=sample_document.id, topic_id=sample_topic.id, relevance_score=0.85, is_primary=True
        )
        db_session.add(doc_topic)
        db_session.commit()

        assert doc_topic.id is not None
        assert doc_topic.relevance_score == 0.85
        assert doc_topic.is_primary is True


@pytest.mark.unit
class TestTopicRelationship:
    """Tests for TopicRelationship model."""

    def test_create_topic_relationship(self, db_session, sample_collection):
        """Test creating a topic relationship."""
        topic1 = Topic(collection_id=sample_collection.id, name="Topic 1", document_count=1)
        topic2 = Topic(collection_id=sample_collection.id, name="Topic 2", document_count=1)
        db_session.add_all([topic1, topic2])
        db_session.commit()

        relationship = TopicRelationship(
            collection_id=sample_collection.id,
            source_topic_id=topic1.id,
            target_topic_id=topic2.id,
            similarity_score=0.5,
            relationship_type="RELATED",
        )
        db_session.add(relationship)
        db_session.commit()

        assert relationship.id is not None
        assert relationship.similarity_score == 0.5
        assert relationship.relationship_type == "RELATED"


@pytest.mark.unit
class TestTopicInsight:
    """Tests for TopicInsight model."""

    def test_create_topic_insight(self, db_session, sample_topic):
        """Test creating a topic insight."""
        insight = TopicInsight(
            topic_id=sample_topic.id,
            summary="Test summary",
            key_themes=["theme1", "theme2"],
            common_questions=["q1", "q2"],
            related_concepts=["concept1"],
        )
        db_session.add(insight)
        db_session.commit()

        assert insight.id is not None
        assert insight.summary == "Test summary"
        assert len(insight.key_themes) == 2
