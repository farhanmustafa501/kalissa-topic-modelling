from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, scoped_session


class Base(DeclarativeBase):
	pass


def _get_database_url() -> str:
	url = os.getenv("DATABASE_URL")
	if not url:
		raise RuntimeError("DATABASE_URL is not set")
	return url


engine = create_engine(_get_database_url(), echo=False, future=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False))

_tables_initialized = False


def ensure_tables_initialized() -> None:
	global _tables_initialized
	if _tables_initialized:
		return
	try:
		Base.metadata.create_all(engine)
		_tables_initialized = True
	except Exception:
		# DB might not be ready yet; leave as not initialized and let caller retry on next request
		_tables_initialized = False


def get_db_session() -> Generator:
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()


