from __future__ import annotations

import logging
from datetime import datetime

from app.worker import celery_app
from app.db import SessionLocal
from app.models import DiscoveryJob, JobStatusEnum, Collection
from app.services.discovery import run_discovery

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.run_discovery_job")
def run_discovery_job(collection_id: int) -> str:
	session = SessionLocal()
	try:
		job = DiscoveryJob(collection_id=collection_id, status=JobStatusEnum.PENDING, mode="FULL", started_at=datetime.utcnow())
		session.add(job)
		session.flush()

		# mark on collection
		c = session.get(Collection, collection_id)
		if c:
			c.last_discovery_job_id = job.id
		session.commit()

		run_discovery(session, collection_id, job)
		finished = session.get(DiscoveryJob, job.id)
		if finished:
			finished.finished_at = datetime.utcnow()
			session.commit()
		logger.info("discovery job complete", extra={"collection_id": collection_id, "job_id": job.id})
		return str(job.id)
	except Exception:
		logger.exception("discovery job failed", extra={"collection_id": collection_id})
		j = session.query(DiscoveryJob).filter(DiscoveryJob.collection_id == collection_id).order_by(DiscoveryJob.id.desc()).first()
		if j:
			j.status = JobStatusEnum.FAILED
			j.error_message = "Unhandled error"
			j.finished_at = datetime.utcnow()
			session.commit()
		return "error"
	finally:
		session.close()


