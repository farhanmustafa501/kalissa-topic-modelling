"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2025-11-28 00:00:00
"""
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.execute("CREATE EXTENSION IF NOT EXISTS vector")

	op.create_table(
		"users",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("email", sa.String(length=255), nullable=False, unique=True),
		sa.Column("name", sa.String(length=255), nullable=True),
		sa.Column("created_at", sa.DateTime(), nullable=False),
	)

	op.create_table(
		"discovery_jobs",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("collection_id", sa.Integer(), nullable=False),
		sa.Column("status", sa.String(length=16), nullable=False),
		sa.Column("mode", sa.String(length=16), nullable=True),
		sa.Column("progress_step", sa.Integer(), nullable=True),
		sa.Column("progress_total_steps", sa.Integer(), nullable=True),
		sa.Column("error_message", sa.Text(), nullable=True),
		sa.Column("started_at", sa.DateTime(), nullable=True),
		sa.Column("finished_at", sa.DateTime(), nullable=True),
		sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], name="fk_discovery_jobs_collection", ondelete="CASCADE"),
	)

	op.create_table(
		"collections",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("owner_id", sa.Integer(), nullable=True),
		sa.Column("name", sa.String(length=255), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("created_at", sa.DateTime(), nullable=False),
		sa.Column("updated_at", sa.DateTime(), nullable=False),
		sa.Column("last_discovery_job_id", sa.Integer(), nullable=True),
		sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
		sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_collections_owner"),
		sa.ForeignKeyConstraint(["last_discovery_job_id"], ["discovery_jobs.id"], name="fk_collections_last_job"),
	)

	op.create_table(
		"documents",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("collection_id", sa.Integer(), nullable=False),
		sa.Column("title", sa.String(length=500), nullable=False),
		sa.Column("content", sa.Text(), nullable=True),
		sa.Column("preview", sa.String(length=400), nullable=True),
		sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=1536), nullable=True),
		sa.Column("created_at", sa.DateTime(), nullable=False),
		sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], name="fk_documents_collection", ondelete="CASCADE"),
	)
	op.create_index("ix_documents_collection_id", "documents", ["collection_id"])

	op.create_table(
		"topics",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("collection_id", sa.Integer(), nullable=False),
		sa.Column("name", sa.String(length=255), nullable=False),
		sa.Column("cluster_id", sa.String(length=64), nullable=True),
		sa.Column("document_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
		sa.Column("avg_confidence", sa.Float(), nullable=True),
		sa.Column("color", sa.String(length=16), nullable=True),
		sa.Column("size_score", sa.Float(), nullable=True),
		sa.Column("created_at", sa.DateTime(), nullable=False),
		sa.Column("updated_at", sa.DateTime(), nullable=False),
		sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], name="fk_topics_collection", ondelete="CASCADE"),
	)
	op.create_index("ix_topics_collection_id", "topics", ["collection_id"])

	op.create_table(
		"topic_insights",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("topic_id", sa.Integer(), nullable=False, unique=True),
		sa.Column("summary", sa.Text(), nullable=True),
		sa.Column("key_themes", sa.JSON(), nullable=True),
		sa.Column("common_questions", sa.JSON(), nullable=True),
		sa.Column("related_concepts", sa.JSON(), nullable=True),
		sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], name="fk_topic_insights_topic", ondelete="CASCADE"),
	)

	op.create_table(
		"document_topics",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("document_id", sa.Integer(), nullable=False),
		sa.Column("topic_id", sa.Integer(), nullable=False),
		sa.Column("relevance_score", sa.Float(), nullable=True),
		sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
		sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_document_topics_document", ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], name="fk_document_topics_topic", ondelete="CASCADE"),
		sa.UniqueConstraint("document_id", "topic_id", name="uq_document_topic"),
	)
	op.create_index("ix_document_topics_document_id", "document_topics", ["document_id"])
	op.create_index("ix_document_topics_topic_id", "document_topics", ["topic_id"])

	op.create_table(
		"topic_relationships",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("collection_id", sa.Integer(), nullable=False),
		sa.Column("source_topic_id", sa.Integer(), nullable=False),
		sa.Column("target_topic_id", sa.Integer(), nullable=False),
		sa.Column("similarity_score", sa.Float(), nullable=True),
		sa.Column("relationship_type", sa.String(length=32), nullable=True),
		sa.Column("common_document_count", sa.Integer(), nullable=True),
		sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], name="fk_topic_relationships_collection", ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["source_topic_id"], ["topics.id"], name="fk_topic_relationships_source", ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["target_topic_id"], ["topics.id"], name="fk_topic_relationships_target", ondelete="CASCADE"),
		sa.UniqueConstraint("source_topic_id", "target_topic_id", name="uq_topic_edge"),
	)
	op.create_index("ix_topic_relationships_collection_id", "topic_relationships", ["collection_id"])


def downgrade() -> None:
	op.drop_index("ix_topic_relationships_collection_id", table_name="topic_relationships")
	op.drop_table("topic_relationships")
	op.drop_index("ix_document_topics_topic_id", table_name="document_topics")
	op.drop_index("ix_document_topics_document_id", table_name="document_topics")
	op.drop_table("document_topics")
	op.drop_table("topic_insights")
	op.drop_index("ix_topics_collection_id", table_name="topics")
	op.drop_table("topics")
	op.drop_index("ix_documents_collection_id", table_name="documents")
	op.drop_table("documents")
	op.drop_table("collections")
	op.drop_table("discovery_jobs")
	op.drop_table("users")
	op.execute("DROP EXTENSION IF EXISTS vector")




