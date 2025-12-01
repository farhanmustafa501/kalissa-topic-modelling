import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure environment variables are sourced from .env files before anything reads them.
_BASE_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_ENV_FILES = (".env", ".env.local")

for filename in _DEFAULT_ENV_FILES:
	env_path = _BASE_DIR / filename
	if env_path.exists():
		# Do not override already-set environment variables (e.g., from deployment).
		load_dotenv(env_path, override=False)


def get_config() -> dict[str, Any]:
	"""
	Get application configuration from environment variables.
	
	Returns:
		Dictionary of configuration values
	"""
	return {
		"SECRET_KEY": os.getenv("SECRET_KEY", "dev-secret-change-me"),
		"DATABASE_URL": os.getenv("DATABASE_URL", ""),
		"OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
		"OPENAI_EMBEDDING_MODEL": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
		"OPENAI_EMBEDDING_DIM": int(os.getenv("OPENAI_EMBEDDING_DIM", "1536")),
		"OPENAI_MAX_INPUT_CHARS": int(os.getenv("OPENAI_MAX_INPUT_CHARS", "8000")),
		"CELERY_BROKER_URL": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
		"CELERY_RESULT_BACKEND": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
	}



