"""
Tests for Celery tasks.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.celery_app import celery_app
from app.models import JobStatusEnum
from app.tasks import run_discovery_task

# Configure Celery to run tasks synchronously in tests
celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True

def _call_task(job_id: int, collection_id: int):
	"""Helper to call the task function directly for testing.
	
	With task_always_eager=True, .apply() will execute synchronously.
	For bound tasks, Celery automatically passes self as the first argument.
	"""
	# Use .apply() which works correctly with eager mode and bound tasks
	return run_discovery_task.apply(args=(job_id, collection_id))


@pytest.mark.task
class TestCeleryTasks:
	"""Tests for Celery background tasks."""

	@patch('app.tasks.run_discovery')
	@patch('app.tasks.SessionLocal')
	def test_run_discovery_task_success(self, mock_session_local, mock_run_discovery, db_session, sample_collection, sample_discovery_job):
		"""Test successful execution of discovery task."""
		mock_session_local.return_value = db_session

		# Store IDs before task runs (objects may become detached)
		job_id = sample_discovery_job.id
		collection_id = sample_collection.id

		# Set job to RUNNING status
		sample_discovery_job.status = JobStatusEnum.RUNNING
		sample_discovery_job.started_at = datetime.utcnow()
		db_session.commit()

		# Run the task using helper function
		_call_task(job_id, collection_id)

		# Verify run_discovery was called
		mock_run_discovery.assert_called_once()
		call_args = mock_run_discovery.call_args
		assert call_args[0][0] == db_session
		assert call_args[0][1] == collection_id
		assert call_args[0][2].id == job_id

		# Re-query the job to get updated data (task closes session, so objects are detached)
		from app.models import DiscoveryJob
		job = db_session.get(DiscoveryJob, job_id)
		assert job is not None
		assert job.status == JobStatusEnum.SUCCEEDED
		assert job.finished_at is not None

	@patch('app.tasks.run_discovery')
	@patch('app.tasks.SessionLocal')
	def test_run_discovery_task_job_not_found(self, mock_session_local, mock_run_discovery, db_session):
		"""Test discovery task when job doesn't exist."""
		mock_session_local.return_value = db_session

		# Run with non-existent job ID
		_call_task(99999, 1)

		# Verify run_discovery was not called
		mock_run_discovery.assert_not_called()

	@patch('app.tasks.run_discovery')
	@patch('app.tasks.SessionLocal')
	def test_run_discovery_task_failure(self, mock_session_local, mock_run_discovery, db_session, sample_collection, sample_discovery_job):
		"""Test discovery task handles exceptions correctly."""
		mock_session_local.return_value = db_session

		# Store IDs before task runs (objects may become detached)
		job_id = sample_discovery_job.id
		collection_id = sample_collection.id

		# Make run_discovery raise an exception
		mock_run_discovery.side_effect = Exception("Test error")

		sample_discovery_job.status = JobStatusEnum.RUNNING
		db_session.commit()

		# Task should raise exception (Celery will mark it as failed)
		with pytest.raises(Exception):
			_call_task(job_id, collection_id)

		# Re-query the job to get updated data (task closes session, so objects are detached)
		from app.models import DiscoveryJob
		job = db_session.get(DiscoveryJob, job_id)
		
		# Verify job was marked as failed
		assert job is not None, "Job should exist"
		assert job.status == JobStatusEnum.FAILED, f"Expected FAILED but got {job.status}"
		assert job.error_message is not None
		assert "Test error" in job.error_message
		assert job.finished_at is not None

	@patch('app.tasks.run_discovery')
	@patch('app.tasks.SessionLocal')
	def test_run_discovery_task_already_completed(self, mock_session_local, mock_run_discovery, db_session, sample_collection, sample_discovery_job):
		"""Test discovery task when job is already completed."""
		mock_session_local.return_value = db_session

		# Set job to already succeeded
		sample_discovery_job.status = JobStatusEnum.SUCCEEDED
		sample_discovery_job.finished_at = datetime.utcnow()
		db_session.commit()

		# Run the task
		_call_task(sample_discovery_job.id, sample_collection.id)

		# Verify run_discovery was still called (task doesn't check status before running)
		mock_run_discovery.assert_called_once()

	@patch('app.tasks.run_discovery')
	@patch('app.tasks.SessionLocal')
	def test_run_discovery_task_persist_failure_error(self, mock_session_local, mock_run_discovery, db_session, sample_collection, sample_discovery_job):
		"""Test discovery task when persisting failure also fails."""
		mock_session_local.return_value = db_session

		# Make run_discovery raise an exception
		mock_run_discovery.side_effect = Exception("Original error")

		sample_discovery_job.status = JobStatusEnum.RUNNING
		db_session.commit()

		# Make session.commit() raise an error when trying to persist failure
		original_commit = db_session.commit
		call_count = [0]

		def failing_commit():
			call_count[0] += 1
			if call_count[0] > 1:  # Fail on second commit (the failure persistence)
				raise Exception("Commit failed")
			original_commit()

		db_session.commit = failing_commit

		# Task should still raise the original exception
		with pytest.raises(Exception):
			_call_task(sample_discovery_job.id, sample_collection.id)

