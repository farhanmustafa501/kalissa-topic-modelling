import os
from typing import Dict, Any


def get_config() -> Dict[str, Any]:
	return {
		"SECRET_KEY": os.getenv("SECRET_KEY", "dev-secret-change-me"),
		"DATABASE_URL": os.getenv("DATABASE_URL", ""),
		"OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
		"CELERY_BROKER_URL": os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
		"CELERY_RESULT_BACKEND": os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
	}


