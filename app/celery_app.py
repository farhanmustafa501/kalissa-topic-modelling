"""
Celery application configuration and initialization.
"""
from celery import Celery

from app.config import get_config

config = get_config()

celery_app = Celery(
	"kalissa_topic_modelling",
	broker=config["CELERY_BROKER_URL"],
	backend=config["CELERY_RESULT_BACKEND"],
)

# Celery configuration
celery_app.conf.update(
	task_serializer="json",
	accept_content=["json"],
	result_serializer="json",
	timezone="UTC",
	enable_utc=True,
	task_track_started=True,
	task_time_limit=3600,  # 1 hour max per task
	task_soft_time_limit=3300,  # 55 minutes soft limit
)

# Import tasks to ensure they're registered with Celery
from app import tasks  # noqa: F401, E402

