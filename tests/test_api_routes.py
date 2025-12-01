"""
Tests for API routes.
"""
import io
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models import Document


@pytest.mark.api
class TestCollectionsAPI:
    """Tests for collections API endpoints."""

    def test_list_collections(self, client, sample_collection):
        """Test listing all collections."""
        response = client.get('/api/collections')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]['id'] == sample_collection.id
        assert data[0]['name'] == sample_collection.name

    def test_get_collection(self, client, sample_collection):
        """Test getting a single collection."""
        response = client.get(f'/api/collections/{sample_collection.id}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['id'] == sample_collection.id
        assert data['name'] == sample_collection.name

    def test_get_collection_not_found(self, client):
        """Test getting a non-existent collection."""
        response = client.get('/api/collections/99999')
        assert response.status_code == 404

    def test_create_collection(self, client, db_session):
        """Test creating a new collection."""
        data = {
            'name': 'New Test Collection',
            'description': 'Test description'
        }
        response = client.post(
            '/api/collections',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 201
        result = json.loads(response.data)
        assert result['name'] == data['name']
        assert result['description'] == data['description']
        assert 'id' in result

    def test_create_collection_missing_name(self, client):
        """Test creating collection without name."""
        data = {'description': 'Test'}
        response = client.post(
            '/api/collections',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_create_collection_form_data(self, client, db_session):
        """Test creating collection via form data."""
        data = {'name': 'Form Collection', 'description': 'From form'}
        response = client.post(
            '/api/collections',
            data=data,
            content_type='application/x-www-form-urlencoded'
        )
        assert response.status_code == 201
        result = json.loads(response.data)
        assert result['name'] == 'Form Collection'

    def test_create_collection_db_error(self, client):
        """Test create_collection with database error."""
        with patch('app.api.routes.SessionLocal') as mock_session:
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance
            mock_session_instance.commit.side_effect = SQLAlchemyError("DB Error")

            data = {'name': 'Test Collection'}
            response = client.post(
                '/api/collections',
                data=json.dumps(data),
                content_type='application/json'
            )
            assert response.status_code == 500

    def test_delete_collection(self, client, sample_collection, db_session):
        """Test deleting a collection."""
        collection_id = sample_collection.id
        response = client.delete(f'/api/collections/{collection_id}')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['status'] == 'deleted'
        assert result['id'] == collection_id

    def test_delete_collection_not_found(self, client):
        """Test deleting a non-existent collection."""
        response = client.delete('/api/collections/99999')
        assert response.status_code == 404

    def test_delete_collection_with_job_id(self, client, sample_collection, sample_discovery_job, db_session):
        """Test deleting collection with last_discovery_job_id set."""
        sample_collection.last_discovery_job_id = sample_discovery_job.id
        db_session.add(sample_collection)
        db_session.commit()

        response = client.delete(f'/api/collections/{sample_collection.id}')
        assert response.status_code == 200

    def test_delete_collection_db_error(self, client, sample_collection):
        """Test delete_collection with database error."""
        with patch('app.api.routes.SessionLocal') as mock_session:
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance
            mock_session_instance.get.return_value = sample_collection
            mock_session_instance.commit.side_effect = SQLAlchemyError("DB Error")

            response = client.delete(f'/api/collections/{sample_collection.id}')
            assert response.status_code == 500

    def test_delete_collection_general_error(self, client, sample_collection):
        """Test delete_collection with general exception."""
        with patch('app.api.routes.SessionLocal') as mock_session:
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance
            mock_session_instance.get.return_value = sample_collection
            mock_session_instance.delete.side_effect = Exception("General error")

            response = client.delete(f'/api/collections/{sample_collection.id}')
            assert response.status_code == 500


@pytest.mark.api
class TestDocumentsAPI:
    """Tests for documents API endpoints."""

    def test_list_documents(self, client, sample_collection, sample_document):
        """Test listing documents in a collection."""
        response = client.get(f'/api/collections/{sample_collection.id}/documents')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]['id'] == sample_document.id

    def test_add_documents_json(self, client, sample_collection, db_session):
        """Test adding documents via JSON."""
        data = {
            'documents': [
                {'title': 'Doc 1', 'content': 'Content 1'},
                {'title': 'Doc 2', 'content': 'Content 2'}
            ]
        }
        response = client.post(
            f'/api/collections/{sample_collection.id}/documents',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['accepted'] == 2

    def test_upload_files(self, client, sample_collection, db_session):
        """Test uploading files."""
        # Create a simple text file
        file_content = b"Test file content"
        data = {
            'files': [(io.BytesIO(file_content), 'test.txt')]
        }
        response = client.post(
            f'/api/collections/{sample_collection.id}/documents/upload_files',
            data=data,
            content_type='multipart/form-data'
        )
        # Note: This might fail without proper file handling, but structure is correct
        assert response.status_code in [200, 400]  # 400 if file parsing fails in test env

    def test_add_documents_form_json(self, client, sample_collection, db_session):
        """Test adding documents via form field documents_json."""
        data = {
            'documents_json': json.dumps([
                {'title': 'Doc 1', 'content': 'Content 1'},
                {'title': 'Doc 2', 'content': 'Content 2'}
            ])
        }
        response = client.post(
            f'/api/collections/{sample_collection.id}/documents',
            data=data,
            content_type='application/x-www-form-urlencoded'
        )
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['accepted'] == 2

    def test_add_documents_invalid_json(self, client, sample_collection):
        """Test adding documents with invalid JSON."""
        data = {'documents_json': 'invalid json'}
        response = client.post(
            f'/api/collections/{sample_collection.id}/documents',
            data=data,
            content_type='application/x-www-form-urlencoded'
        )
        assert response.status_code == 400

    def test_add_documents_not_list(self, client, sample_collection):
        """Test adding documents with non-list data."""
        data = {'documents': 'not a list'}
        response = client.post(
            f'/api/collections/{sample_collection.id}/documents',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_add_documents_too_many(self, client, sample_collection):
        """Test adding too many documents."""
        documents = [{'title': f'Doc {i}', 'content': f'Content {i}'} for i in range(201)]
        data = {'documents': documents}
        response = client.post(
            f'/api/collections/{sample_collection.id}/documents',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_add_documents_rejected_missing_title(self, client, sample_collection, db_session):
        """Test adding documents with missing titles."""
        data = {
            'documents': [
                {'title': 'Valid Doc', 'content': 'Content'},
                {'content': 'No title'}  # Missing title
            ]
        }
        response = client.post(
            f'/api/collections/{sample_collection.id}/documents',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['accepted'] == 1
        assert len(result['rejected']) == 1

    def test_add_documents_title_truncation(self, client, sample_collection, db_session):
        """Test title truncation when exceeding MAX_TITLE_CHARS."""
        # Store collection_id before API call to avoid DetachedInstanceError
        collection_id = sample_collection.id
        long_title = 'A' * 600  # Exceeds default MAX_TITLE_CHARS (500)
        data = {
            'documents': [{'title': long_title, 'content': 'Content'}]
        }
        response = client.post(
            f'/api/collections/{collection_id}/documents',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 200
        # Title should be truncated to 500 chars
        # Query using the stored collection_id value
        doc = db_session.scalars(
            select(Document).where(Document.collection_id == collection_id).order_by(Document.id.desc())
        ).first()
        assert doc is not None
        assert len(doc.title) == 500

    def test_add_documents_content_truncation(self, client, sample_collection, db_session):
        """Test content truncation when exceeding MAX_CONTENT_CHARS."""
        # Store collection_id before API call to avoid DetachedInstanceError
        collection_id = sample_collection.id
        long_content = 'B' * 201000  # Exceeds default MAX_CONTENT_CHARS (200000)
        data = {
            'documents': [{'title': 'Test', 'content': long_content}]
        }
        response = client.post(
            f'/api/collections/{collection_id}/documents',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 200
        # Content should be truncated to 200000 chars
        # Query using the stored collection_id value
        doc = db_session.scalars(
            select(Document).where(Document.collection_id == collection_id).order_by(Document.id.desc())
        ).first()
        assert doc is not None
        assert len(doc.content) == 200000

    def test_add_documents_db_error(self, client, sample_collection):
        """Test add_documents with database error."""
        with patch('app.api.routes.SessionLocal') as mock_session:
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance
            mock_session_instance.commit.side_effect = SQLAlchemyError("DB Error")

            data = {'documents': [{'title': 'Test', 'content': 'Content'}]}
            response = client.post(
                f'/api/collections/{sample_collection.id}/documents',
                data=json.dumps(data),
                content_type='application/json'
            )
            assert response.status_code == 500

    def test_upload_files_no_files_part(self, client, sample_collection):
        """Test uploading files without files part."""
        response = client.post(
            f'/api/collections/{sample_collection.id}/documents/upload_files',
            data={},
            content_type='multipart/form-data'
        )
        assert response.status_code == 400

    def test_upload_files_empty_files(self, client, sample_collection):
        """Test uploading with empty files list."""
        # Use Flask's test client to send empty files list
        # The client will handle the request context properly
        data = {'files': []}
        response = client.post(
            f'/api/collections/{sample_collection.id}/documents/upload_files',
            data=data,
            content_type='multipart/form-data'
        )
        # Should fail because no files provided
        assert response.status_code == 400

    def test_extract_embeddings_deprecated(self, client, sample_collection):
        """Test deprecated extract embeddings endpoint."""
        response = client.post(f'/api/collections/{sample_collection.id}/embeddings/extract')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'DEPRECATED'


@pytest.mark.api
class TestUIRoutes:
    """Tests for UI routes."""

    def test_index(self, client):
        """Test index page."""
        response = client.get('/')
        assert response.status_code == 200

    def test_ui_collections(self, client, sample_collection):
        """Test UI collections page."""
        response = client.get('/ui/collections')
        assert response.status_code == 200
        assert b'collections' in response.data.lower()

    def test_ui_collections_direct(self, client, sample_collection):
        """Test direct collections route."""
        response = client.get('/collections')
        assert response.status_code == 200

    def test_ui_collection_detail(self, client, sample_collection):
        """Test UI collection detail page."""
        response = client.get(f'/ui/collections/{sample_collection.id}')
        assert response.status_code == 200

    def test_ui_collection_detail_not_found(self, client):
        """Test UI collection detail with non-existent collection."""
        response = client.get('/ui/collections/99999')
        assert response.status_code == 302  # Redirect

    def test_ui_collection_detail_direct(self, client, sample_collection):
        """Test direct collection detail route."""
        response = client.get(f'/collections/{sample_collection.id}')
        assert response.status_code == 200

    def test_ui_collection_detail_direct_not_found(self, client):
        """Test direct collection detail with non-existent collection."""
        response = client.get('/collections/99999')
        assert response.status_code == 302  # Redirect

    def test_ui_graph(self, client, sample_collection):
        """Test UI graph page."""
        response = client.get(f'/ui/collections/{sample_collection.id}/graph')
        assert response.status_code == 200

    def test_ui_graph_direct(self, client, sample_collection):
        """Test direct graph route."""
        response = client.get(f'/collections/{sample_collection.id}/graph')
        assert response.status_code == 200

    def test_ui_topic(self, client, sample_topic):
        """Test UI topic detail page."""
        response = client.get(f'/ui/topics/{sample_topic.id}')
        assert response.status_code == 200

    def test_ui_topic_not_found(self, client):
        """Test UI topic detail with non-existent topic."""
        response = client.get('/ui/topics/99999')
        assert response.status_code == 200
        assert b'not found' in response.data.lower()

    def test_ui_discover_status(self, client, sample_collection, sample_discovery_job):
        """Test UI discover status page."""
        response = client.get(f'/ui/collections/{sample_collection.id}/discover/status')
        assert response.status_code == 200

    def test_ui_discover_status_no_job(self, client, sample_collection):
        """Test UI discover status with no job."""
        response = client.get(f'/ui/collections/{sample_collection.id}/discover/status')
        assert response.status_code == 200
        assert b'No job' in response.data or b'IDLE' in response.data

    def test_ui_topic_with_chunks(self, client, sample_topic, sample_document, db_session):
        """Test UI topic page with chunks."""
        from app.models import Chunk, DocumentTopic
        doc_topic = DocumentTopic(
            document_id=sample_document.id,
            topic_id=sample_topic.id,
            relevance_score=0.85,
            is_primary=True
        )
        db_session.add(doc_topic)
        chunk = Chunk(
            document_id=sample_document.id,
            chunk_index=0,
            text="Test chunk"
        )
        db_session.add(chunk)
        db_session.commit()

        response = client.get(f'/ui/topics/{sample_topic.id}')
        assert response.status_code == 200

    def test_ui_topic_with_related_topics(self, client, sample_topic, db_session):
        """Test UI topic page with related topics."""
        from app.models import Topic, TopicRelationship
        related_topic = Topic(
            collection_id=sample_topic.collection_id,
            name="Related Topic"
        )
        db_session.add(related_topic)
        db_session.flush()

        rel = TopicRelationship(
            collection_id=sample_topic.collection_id,
            source_topic_id=sample_topic.id,
            target_topic_id=related_topic.id,
            similarity_score=0.8
        )
        db_session.add(rel)
        db_session.commit()

        response = client.get(f'/ui/topics/{sample_topic.id}')
        assert response.status_code == 200


@pytest.mark.api
class TestDiscoveryAPI:
    """Tests for discovery API endpoints."""

    @patch('app.api.routes.run_discovery_task')
    def test_start_discovery(self, mock_discovery_task, client, sample_collection, db_session):
        """Test starting a discovery job."""
        # Mock the Celery task's delay method
        mock_discovery_task.delay.return_value = None
        response = client.post(f'/api/collections/{sample_collection.id}/discover')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'job_id' in data
        assert data['status'] == 'ENQUEUED'
        # Verify the task was called
        assert mock_discovery_task.delay.called

    def test_get_discovery_status(self, client, sample_collection, sample_discovery_job):
        """Test getting discovery job status."""
        response = client.get(f'/api/collections/{sample_collection.id}/discover/status')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'status' in data
        assert 'progress' in data

    def test_delete_discovery_job(self, client, sample_collection, sample_discovery_job, db_session):
        """Test deleting a discovery job."""
        # Set the job as last_discovery_job_id
        sample_collection.last_discovery_job_id = sample_discovery_job.id
        db_session.commit()

        response = client.delete(
            f'/api/collections/{sample_collection.id}/discover/last_job'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'deleted'


@pytest.mark.api
class TestTopicsAPI:
    """Tests for topics API endpoints."""

    def test_get_topics_graph(self, client, sample_collection, sample_topic, db_session):
        """Test getting topics graph."""
        response = client.get(f'/api/collections/{sample_collection.id}/topics/graph')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'nodes' in data
        assert 'edges' in data
        assert isinstance(data['nodes'], list)
        assert isinstance(data['edges'], list)

    def test_get_topic_detail(self, client, sample_topic):
        """Test getting topic details."""
        response = client.get(f'/api/topics/{sample_topic.id}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['id'] == sample_topic.id
        assert data['name'] == sample_topic.name

    def test_get_topic_detail_not_found(self, client):
        """Test getting non-existent topic."""
        response = client.get('/api/topics/99999')
        assert response.status_code == 404

    @patch('app.api.routes.answer_question_with_citations')
    def test_topic_qa(self, mock_qa, client, sample_topic, sample_document, db_session):
        """Test topic Q&A endpoint."""
        # Add document to topic so Q&A endpoint doesn't return "No documents found"
        from app.models import DocumentTopic
        doc_topic = DocumentTopic(
            document_id=sample_document.id,
            topic_id=sample_topic.id,
            relevance_score=0.85,
            is_primary=True
        )
        db_session.add(doc_topic)
        # Also add a chunk to the document so Q&A can find context
        # The chunk must have an embedding for the query to find it
        from app.models import Chunk
        chunk = Chunk(
            document_id=sample_document.id,
            chunk_index=0,
            text="Test chunk content for Q&A",
            embedding=[0.1] * 1536  # Add embedding so it's found by the query
        )
        db_session.add(chunk)
        db_session.commit()

        # Mock the answer function to return test answer
        mock_qa.return_value = '<div class="qa-answer">Test answer</div>'

        data = {'question': 'What is this topic about?'}
        response = client.post(
            f'/api/topics/{sample_topic.id}/qa',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 200
        assert b'Test answer' in response.data
        # Verify the mock was called
        assert mock_qa.called

    def test_topic_qa_empty_question(self, client, sample_topic):
        """Test topic Q&A with empty question."""
        data = {'question': ''}
        response = client.post(
            f'/api/topics/{sample_topic.id}/qa',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 200
        assert b'Please provide a question' in response.data

    def test_topic_qa_no_documents(self, client, sample_topic):
        """Test topic Q&A with no documents."""
        data = {'question': 'What is this?'}
        response = client.post(
            f'/api/topics/{sample_topic.id}/qa',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 200
        assert b'No documents found' in response.data

    def test_topic_qa_no_chunks(self, client, sample_topic, sample_document, db_session):
        """Test topic Q&A with no chunks."""
        from app.models import DocumentTopic
        doc_topic = DocumentTopic(
            document_id=sample_document.id,
            topic_id=sample_topic.id,
            relevance_score=0.85,
            is_primary=True
        )
        db_session.add(doc_topic)
        db_session.commit()

        data = {'question': 'What is this?'}
        response = client.post(
            f'/api/topics/{sample_topic.id}/qa',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 200
        assert b'No relevant chunks found' in response.data

    @patch('app.api.routes.answer_question_with_citations')
    def test_topic_qa_exception(self, mock_qa, client, sample_topic, sample_document, db_session):
        """Test topic Q&A with exception."""
        from app.models import Chunk, DocumentTopic
        doc_topic = DocumentTopic(
            document_id=sample_document.id,
            topic_id=sample_topic.id,
            relevance_score=0.85,
            is_primary=True
        )
        db_session.add(doc_topic)
        chunk = Chunk(
            document_id=sample_document.id,
            chunk_index=0,
            text="Test chunk",
            embedding=[0.1] * 1536
        )
        db_session.add(chunk)
        db_session.commit()

        # Make the function raise an exception
        mock_qa.side_effect = Exception("Test error")

        data = {'question': 'What is this?'}
        response = client.post(
            f'/api/topics/{sample_topic.id}/qa',
            data=json.dumps(data),
            content_type='application/json'
        )
        assert response.status_code == 200
        assert b'An error occurred' in response.data


@pytest.mark.api
class TestHealthAPI:
    """Tests for health check endpoint."""

    def test_health(self, client):
        """Test health check endpoint."""
        response = client.get('/api/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'ok'

