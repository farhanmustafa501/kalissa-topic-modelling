import os
from typing import Dict, Any


def get_config() -> Dict[str, Any]:
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
	}



