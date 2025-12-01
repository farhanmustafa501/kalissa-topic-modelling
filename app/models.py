from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Collection(Base):
	__tablename__ = "collections"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	name: Mapped[str] = mapped_column(String(255), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
	last_discovery_job_id: Mapped[int | None] = mapped_column(ForeignKey("discovery_jobs.id"), nullable=True)
	is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
	documents: Mapped[list[Document]] = relationship(back_populates="collection", cascade="all, delete-orphan")
	topics: Mapped[list[Topic]] = relationship(back_populates="collection", cascade="all, delete-orphan")
	discovery_jobs: Mapped[list[DiscoveryJob]] = relationship(
		"DiscoveryJob",
		back_populates="collection",
		foreign_keys="DiscoveryJob.collection_id",
		cascade="all, delete-orphan",
	)
	last_discovery_job: Mapped[DiscoveryJob | None] = relationship(
		"DiscoveryJob",
		foreign_keys=[last_discovery_job_id],
		uselist=False,
		viewonly=True,
	)


class Document(Base):
	__tablename__ = "documents"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), nullable=False, index=True)
	title: Mapped[str] = mapped_column(String(500), nullable=False)
	content: Mapped[str | None] = mapped_column(Text, nullable=True)
	preview: Mapped[str | None] = mapped_column(String(400), nullable=True)
	embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

	collection: Mapped[Collection] = relationship(back_populates="documents")
	document_topics: Mapped[list[DocumentTopic]] = relationship(back_populates="document", cascade="all, delete-orphan")
	chunks: Mapped[list[Chunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
	"""
	Represents a text chunk from a document.
	Chunks are created by splitting documents into smaller pieces (800-1200 tokens)
	for better embedding and clustering.
	"""
	__tablename__ = "chunks"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
	chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  # Order within document (0, 1, 2, ...)
	text: Mapped[str] = mapped_column(Text, nullable=False)
	embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

	document: Mapped[Document] = relationship(back_populates="chunks")


class Topic(Base):
	__tablename__ = "topics"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), nullable=False, index=True)
	name: Mapped[str] = mapped_column(String(255), nullable=False)
	document_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
	size_score: Mapped[float | None] = mapped_column(Float, nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

	collection: Mapped[Collection] = relationship(back_populates="topics")
	insight: Mapped[TopicInsight | None] = relationship(back_populates="topic", uselist=False, cascade="all, delete-orphan")
	document_topics: Mapped[list[DocumentTopic]] = relationship(back_populates="topic", cascade="all, delete-orphan")
	source_relationships: Mapped[list[TopicRelationship]] = relationship(
		foreign_keys="TopicRelationship.source_topic_id", back_populates="source_topic", cascade="all, delete-orphan"
	)
	target_relationships: Mapped[list[TopicRelationship]] = relationship(
		foreign_keys="TopicRelationship.target_topic_id", back_populates="target_topic", cascade="all, delete-orphan"
	)


class DocumentTopic(Base):
	__tablename__ = "document_topics"
	__table_args__ = (UniqueConstraint("document_id", "topic_id", name="uq_document_topic"),)

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
	topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False, index=True)
	relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
	is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

	document: Mapped[Document] = relationship(back_populates="document_topics")
	topic: Mapped[Topic] = relationship(back_populates="document_topics")


class TopicRelationship(Base):
	__tablename__ = "topic_relationships"
	__table_args__ = (UniqueConstraint("source_topic_id", "target_topic_id", name="uq_topic_edge"),)

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), nullable=False, index=True)
	source_topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
	target_topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
	similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
	relationship_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

	source_topic: Mapped[Topic] = relationship(foreign_keys=[source_topic_id], back_populates="source_relationships")
	target_topic: Mapped[Topic] = relationship(foreign_keys=[target_topic_id], back_populates="target_relationships")


class TopicInsight(Base):
	__tablename__ = "topic_insights"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), unique=True, nullable=False)
	summary: Mapped[str | None] = mapped_column(Text, nullable=True)
	key_themes: Mapped[list | None] = mapped_column(JSON, nullable=True)
	common_questions: Mapped[list | None] = mapped_column(JSON, nullable=True)
	related_concepts: Mapped[list | None] = mapped_column(JSON, nullable=True)

	topic: Mapped[Topic] = relationship(back_populates="insight")


class JobStatusEnum(str):
	PENDING = "PENDING"
	RUNNING = "RUNNING"
	SUCCEEDED = "SUCCEEDED"
	FAILED = "FAILED"


class DiscoveryJob(Base):
	__tablename__ = "discovery_jobs"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), nullable=False, index=True)
	status: Mapped[str] = mapped_column(String(16), default=JobStatusEnum.PENDING, nullable=False)
	mode: Mapped[str | None] = mapped_column(String(16), nullable=True)  # FULL / INCREMENTAL
	progress_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
	progress_total_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
	error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
	started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
	finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

	collection: Mapped[Collection] = relationship(
		"Collection",
		back_populates="discovery_jobs",
		foreign_keys=[collection_id],
	)


