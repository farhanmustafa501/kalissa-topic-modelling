import os
from celery import Celery


def make_celery() -> Celery:
	broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
	backend_url = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
	celery = Celery(__name__, broker=broker_url, backend=backend_url, include=["app.tasks"])
	return celery


celery_app = make_celery()


@celery_app.task(name="app.tasks.ping")
def ping() -> str:
	return "pong"



