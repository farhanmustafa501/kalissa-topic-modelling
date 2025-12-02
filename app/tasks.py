"""
Celery tasks for background job processing.
"""

import logging
from datetime import datetime

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import DiscoveryJob, JobStatusEnum
from app.services.discovery import run_discovery

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.run_discovery_task")
def run_discovery_task(self, job_id: int, collection_id: int) -> None:
    """
    Celery task to run topic discovery in the background.

    This task runs the complete topic discovery pipeline and updates
    the job status in the database.

    Args:
            job_id: Discovery job ID
            collection_id: Collection ID to process
    """
    session = SessionLocal()
    try:
        job = session.get(DiscoveryJob, job_id)
        if not job:
            logger.warning("Discovery job not found", extra={"job_id": job_id})
            return

        logger.info("Discovery task started", extra={"collection_id": collection_id, "job_id": job_id})

        # Run the discovery pipeline
        run_discovery(session, collection_id, job)

        # Mark job as finished (if not already marked by run_discovery)
        job = session.get(DiscoveryJob, job_id)
        if job and job.status == JobStatusEnum.RUNNING:
            job.finished_at = datetime.utcnow()
            if job.status != JobStatusEnum.SUCCEEDED and job.status != JobStatusEnum.FAILED:
                job.status = JobStatusEnum.SUCCEEDED
            session.add(job)
            session.commit()

        logger.info(
            "Discovery task completed",
            extra={"collection_id": collection_id, "job_id": job_id, "status": job.status if job else "unknown"},
        )
    except Exception as e:
        logger.exception(
            "Discovery task failed", extra={"collection_id": collection_id, "job_id": job_id, "error": str(e)}
        )
        try:
            j = session.get(DiscoveryJob, job_id)
            if j:
                j.status = JobStatusEnum.FAILED
                j.error_message = str(e)[:500] if str(e) else "Unhandled error"
                j.finished_at = datetime.utcnow()
                session.add(j)
                session.commit()
                logger.info("Job failure persisted", extra={"job_id": job_id})
        except Exception as inner_e:
            logger.exception("Failed to persist job failure", extra={"job_id": job_id, "inner_error": str(inner_e)})
        # Re-raise to mark task as failed in Celery
        raise
    finally:
        session.close()
