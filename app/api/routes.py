import logging
import os
from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionLocal, ensure_tables_initialized
from app.models import (
    Chunk,
    Collection,
    DiscoveryJob,
    Document,
    DocumentTopic,
    JobStatusEnum,
    Topic,
    TopicInsight,
    TopicRelationship,
)
from app.services.ai import answer_question_with_citations
from app.services.parser import extract_text_from_upload
from app.tasks import run_discovery_task

api_bp = Blueprint("api", __name__)
ui_bp = Blueprint("ui", __name__)

logger = logging.getLogger(__name__)

# Upload/validation settings (env-overridable)
ALLOWED_EXTS = set((os.getenv("ALLOWED_EXTS") or ".txt,.md,.pdf,.docx").lower().split(","))
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_BYTES") or 1 * 1024 * 1024)  # default 1 MB per file
MAX_FILES_PER_UPLOAD = int(os.getenv("MAX_FILES_PER_UPLOAD") or 10)
MAX_JSON_DOCS = int(os.getenv("MAX_JSON_DOCS") or 200)
MAX_TITLE_CHARS = int(os.getenv("MAX_TITLE_CHARS") or 500)  # matches DB column
MAX_CONTENT_CHARS = int(os.getenv("MAX_CONTENT_CHARS") or 200_000)  # ~200 KB of text per doc


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@ui_bp.get("/")
def index():
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        rows = session.scalars(select(Collection).order_by(Collection.created_at.desc())).all()
        return render_template("index.html", collections=rows)
    finally:
        session.close()


@api_bp.post("/collections/<int:collection_id>/discover")
def discover_collection(collection_id: int):
    """
    Start topic discovery job for a collection.

    Creates a discovery job and runs it as a Celery background task.
    The pipeline includes: chunking, embedding, clustering, topic labeling, and relationship building.
    """
    logger.info("discover_collection start", extra={"collection_id": collection_id})
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        # Check if collection exists
        c = session.get(Collection, collection_id)
        if not c:
            return jsonify({"error": "Collection not found"}), 404

        # Create job with correct total steps (10 steps in the pipeline)
        job = DiscoveryJob(
            collection_id=collection_id,
            status=JobStatusEnum.PENDING,
            mode="FULL",
            started_at=datetime.utcnow(),
            progress_step=0,
            progress_total_steps=10,
        )
        session.add(job)
        session.flush()
        c.last_discovery_job_id = job.id
        session.commit()

        # Start discovery as Celery task
        run_discovery_task.delay(job.id, collection_id)
        logger.info("Discovery job enqueued", extra={"collection_id": collection_id, "job_id": job.id})
        return jsonify({"job_id": job.id, "collection_id": collection_id, "status": "ENQUEUED"})
    except Exception as e:
        logger.exception("failed to enqueue discovery task", extra={"collection_id": collection_id, "error": str(e)})
        session.rollback()
        return jsonify({"error": f"failed to start discovery: {e!s}"}), 500
    finally:
        session.close()


@api_bp.get("/collections/<int:collection_id>/discover/status")
def discover_status(collection_id: int):
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        # Last job for collection
        row = session.scalars(
            select(DiscoveryJob).where(DiscoveryJob.collection_id == collection_id).order_by(DiscoveryJob.id.desc())
        ).first()
        if not row:
            return jsonify({"collection_id": collection_id, "status": "IDLE"})
        return jsonify(
            {
                "collection_id": collection_id,
                "status": row.status,
                "progress": {
                    "step": row.progress_step or 0,
                    "total_steps": row.progress_total_steps or 0,
                    "label": row.error_message
                    or (
                        "In progress"
                        if row.status == JobStatusEnum.RUNNING
                        else ("Done" if row.status == JobStatusEnum.SUCCEEDED else (row.error_message or "Pending"))
                    ),
                },
                "error": row.error_message,
            }
        )
    finally:
        session.close()


@api_bp.delete("/collections/<int:collection_id>/discover/last_job")
def delete_last_discovery_job(collection_id: int):
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        # Get the collection first
        collection = session.get(Collection, collection_id)
        if not collection:
            return jsonify({"error": "Collection not found"}), 404

        # Get the last discovery job for this collection
        row = session.scalars(
            select(DiscoveryJob).where(DiscoveryJob.collection_id == collection_id).order_by(DiscoveryJob.id.desc())
        ).first()
        if not row:
            return jsonify({"status": "no_job"}), 404

        job_id = row.id

        # IMPORTANT: Clear the reference in ALL collections that reference this job
        # (not just the current collection, in case there's a data inconsistency)
        collections_with_job = session.scalars(
            select(Collection).where(Collection.last_discovery_job_id == job_id)
        ).all()

        if collections_with_job:
            logger.info(
                "Clearing job reference from collections",
                extra={"job_id": job_id, "num_collections": len(collections_with_job)},
            )
            for coll in collections_with_job:
                coll.last_discovery_job_id = None
                session.add(coll)

            # Commit the changes to clear references BEFORE deleting the job
            session.commit()
            logger.info("Job references cleared from collections", extra={"job_id": job_id})

        # Refresh the job row to ensure we have the latest state
        session.refresh(row)

        # Now delete the job
        session.delete(row)
        session.commit()

        logger.info(
            "Discovery job deleted",
            extra={"collection_id": collection_id, "job_id": job_id, "collections_cleared": len(collections_with_job)},
        )
        return jsonify({"status": "deleted", "job_id": job_id})
    except SQLAlchemyError as e:
        session.rollback()
        logger.exception("Failed to delete discovery job", extra={"collection_id": collection_id, "error": str(e)})
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@api_bp.post("/collections/<int:collection_id>/documents")
def add_documents(collection_id: int):
    # Accept JSON body: { "documents": [ { "title": "...", "content": "..."}, ... ] }
    # Or form field: documents_json='[{"title": "...","content":"..."}]'
    logger.info("add_documents start", extra={"collection_id": collection_id})
    session = SessionLocal()
    try:
        payload = request.get_json(silent=True) or {}
        if not payload and "documents_json" in request.form:
            import json

            try:
                payload = {"documents": json.loads(request.form["documents_json"])}
            except Exception:
                return jsonify({"error": "Invalid documents_json"}), 400

        documents = payload.get("documents", [])
        if not isinstance(documents, list):
            return jsonify({"error": "documents must be a list"}), 400
        if len(documents) > MAX_JSON_DOCS:
            return jsonify({"error": f"Too many documents in one request (limit {MAX_JSON_DOCS})"}), 400

        accepted = 0
        rejected = []
        for doc in documents:
            title = (doc or {}).get("title")
            content = (doc or {}).get("content")
            if not title or not str(title).strip():
                rejected.append({"reason": "missing title"})
                continue
            title = str(title).strip()
            if len(title) > MAX_TITLE_CHARS:
                title = title[:MAX_TITLE_CHARS]
            content = (content or "") if isinstance(content, str) else ""
            if len(content) > MAX_CONTENT_CHARS:
                content = content[:MAX_CONTENT_CHARS]
            preview = content[:200] if content else None
            session.add(Document(collection_id=collection_id, title=title, content=content, preview=preview))
            accepted += 1
        session.commit()
        logger.info(
            "add_documents done",
            extra={"collection_id": collection_id, "accepted": accepted, "rejected_count": len(rejected)},
        )
        return jsonify(
            {"collection_id": collection_id, "accepted": accepted, "rejected": rejected, "status": "RECEIVED"}
        )
    except SQLAlchemyError as e:
        session.rollback()
        logger.exception("add_documents db error")
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@api_bp.post("/collections/<int:collection_id>/documents/upload_files")
def upload_documents_files(collection_id: int):
    """
    Bulk upload and parse documents from multipart form-data: files=<multiple>
    Returns counts and created document ids.
    """
    logger.info("upload_documents_files start", extra={"collection_id": collection_id})
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        if "files" not in request.files:
            return jsonify({"error": "No files part 'files' provided"}), 400
        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "No files provided"}), 400
        if len(files) > MAX_FILES_PER_UPLOAD:
            return jsonify({"error": f"Too many files in one request (limit {MAX_FILES_PER_UPLOAD})"}), 400

        created = []
        rejected = []
        for fs in files:
            try:
                filename = (fs.filename or "upload").strip()
                ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if ext not in ALLOWED_EXTS:
                    rejected.append(
                        {
                            "filename": filename,
                            "reason": f"file type not allowed (allowed: {', '.join(sorted(ALLOWED_EXTS))})",
                        }
                    )
                    continue
                file_bytes = fs.read() or b""
                if len(file_bytes) > MAX_FILE_BYTES:
                    rejected.append({"filename": filename, "reason": f"file too large (max {MAX_FILE_BYTES} bytes)"})
                    continue
                title, text = extract_text_from_upload(filename, file_bytes)
                if len(title) > MAX_TITLE_CHARS:
                    title = title[:MAX_TITLE_CHARS]
                if text and len(text) > MAX_CONTENT_CHARS:
                    text = text[:MAX_CONTENT_CHARS]
                preview = (text or "")[:200] if text else None
                doc = Document(collection_id=collection_id, title=title, content=text, preview=preview)
                session.add(doc)
                session.flush()
                created.append(doc.id)
            except Exception:
                # Skip a single file failure; continue others
                logger.exception("upload parse failed")
                rejected.append({"filename": getattr(fs, "filename", "unknown"), "reason": "parse failed"})
                continue
        session.commit()
        logger.info(
            "upload_documents_files done",
            extra={"collection_id": collection_id, "created_count": len(created), "rejected_count": len(rejected)},
        )
        return jsonify(
            {
                "collection_id": collection_id,
                "created_count": len(created),
                "document_ids": created,
                "rejected": rejected,
                "limits": {
                    "allowed_exts": sorted(ALLOWED_EXTS),
                    "max_file_bytes": MAX_FILE_BYTES,
                    "max_files_per_upload": MAX_FILES_PER_UPLOAD,
                    "max_title_chars": MAX_TITLE_CHARS,
                    "max_content_chars": MAX_CONTENT_CHARS,
                },
            }
        )
    except SQLAlchemyError as e:
        session.rollback()
        logger.exception("upload_documents_files db error")
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@api_bp.get("/collections/<int:collection_id>/documents")
def list_documents_in_collection(collection_id: int):
    """
    List all documents in a collection.

    Note: Embeddings are now stored at the chunk level, not document level.
    """
    logger.info("list_documents start", extra={"collection_id": collection_id})
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        rows = session.scalars(
            select(Document).where(Document.collection_id == collection_id).order_by(Document.created_at.desc())
        ).all()

        # Count chunks per document
        doc_ids = [d.id for d in rows]
        chunk_counts = {}
        if doc_ids:
            chunk_stats = session.execute(
                select(Chunk.document_id, func.count(Chunk.id).label("chunk_count"))
                .where(Chunk.document_id.in_(doc_ids))
                .group_by(Chunk.document_id)
            ).all()
            chunk_counts = {stat.document_id: stat.chunk_count for stat in chunk_stats}

        resp = [
            {
                "id": d.id,
                "title": d.title,
                "has_chunks": (chunk_counts.get(d.id, 0) > 0),
                "chunk_count": chunk_counts.get(d.id, 0),
                "preview": d.preview,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in rows
        ]
        logger.info("list_documents done", extra={"collection_id": collection_id, "count": len(resp)})
        return jsonify(resp)
    finally:
        session.close()


# Note: Embeddings are now generated automatically during topic discovery
# This endpoint is deprecated but kept for backward compatibility
@api_bp.post("/collections/<int:collection_id>/embeddings/extract")
def extract_embeddings_for_collection(collection_id: int):
    """
    DEPRECATED: Embeddings are now generated automatically during topic discovery.
    This endpoint is kept for backward compatibility but does nothing.
    """
    logger.warning("extract_embeddings endpoint called but is deprecated", extra={"collection_id": collection_id})
    return jsonify(
        {
            "collection_id": collection_id,
            "processed": 0,
            "status": "DEPRECATED",
            "message": "Embeddings are now generated automatically during topic discovery. Use /collections/<id>/discover instead.",
        }
    )


@api_bp.get("/collections/<int:collection_id>/topics/graph")
def topics_graph(collection_id: int):
    # Return real topics and relationships from DB; no mock data
    logger.info("topics_graph", extra={"collection_id": collection_id})
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        topics = session.scalars(select(Topic).where(Topic.collection_id == collection_id)).all()
        rels = session.scalars(select(TopicRelationship).where(TopicRelationship.collection_id == collection_id)).all()
        nodes = [
            {
                "id": f"t{t.id}",
                "label": t.name,
                "size_score": t.size_score,
                "document_count": t.document_count,
            }
            for t in topics
        ]
        edges = [
            {
                "source": f"t{e.source_topic_id}",
                "target": f"t{e.target_topic_id}",
                "weight": e.similarity_score or 0.0,
                "type": e.relationship_type or "RELATED",
            }
            for e in rels
        ]
        logger.info(
            "topics_graph done", extra={"collection_id": collection_id, "nodes": len(nodes), "edges": len(edges)}
        )
        return jsonify({"nodes": nodes, "edges": edges})
    finally:
        session.close()


@api_bp.get("/topics/<int:topic_id>")
def topic_detail(topic_id: int):
    # Return dynamic topic detail JSON
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        t = session.get(Topic, topic_id)
        if not t:
            return jsonify({"error": "not found"}), 404
        ins = session.scalars(select(TopicInsight).where(TopicInsight.topic_id == topic_id)).first()
        docs = session.execute(
            select(Document, DocumentTopic)
            .where(Document.id == DocumentTopic.document_id)
            .where(DocumentTopic.topic_id == topic_id)
            .order_by(DocumentTopic.relevance_score.desc())
        ).all()
        return jsonify(
            {
                "id": t.id,
                "name": t.name,
                "insights": {
                    "summary": (ins.summary if ins else None),
                    "key_themes": (ins.key_themes if ins else []),
                    "common_questions": (ins.common_questions if ins else []),
                    "related_concepts": (ins.related_concepts if ins else []),
                },
                "documents": [
                    {
                        "id": d.Document.id,
                        "title": d.Document.title,
                        "preview": d.Document.preview,
                        "relevance_score": d.DocumentTopic.relevance_score,
                        "is_primary": d.DocumentTopic.is_primary,
                    }
                    for d in docs
                ],
            }
        )
    finally:
        session.close()


@api_bp.post("/topics/<int:topic_id>/qa")
def topic_qa(topic_id: int):
    """
    Topic-scoped Q&A with citations using GPT-4o.

    Returns HTML answer with inline citations that map to document chunks.
    Uses top 10 chunks from documents in the topic for context.
    """
    question = (request.get_json(silent=True) or {}).get("question") or request.form.get("question") or ""

    if not question or not question.strip():
        return '<div class="qa-answer">Please provide a question.</div>'

    logger.info("Topic Q&A request", extra={"topic_id": topic_id, "question_length": len(question)})
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        # Get documents in this topic
        doc_rows = session.execute(
            select(Document, DocumentTopic)
            .where(Document.id == DocumentTopic.document_id)
            .where(DocumentTopic.topic_id == topic_id)
            .order_by(DocumentTopic.relevance_score.desc())
        ).all()

        if not doc_rows:
            return '<div class="qa-answer">No documents found for this topic.</div>'

        # Get chunks from these documents, ordered by relevance
        doc_ids = [r.Document.id for r in doc_rows]
        chunks = session.scalars(
            select(Chunk)
            .where(Chunk.document_id.in_(doc_ids))
            .where(Chunk.embedding.isnot(None))
            .order_by(Chunk.document_id, Chunk.chunk_index)
            .limit(10)  # Top 10 chunks
        ).all()

        if not chunks:
            return '<div class="qa-answer">No relevant chunks found for this topic.</div>'

        # Build context chunks with proper IDs (format: D{doc_id}-C{chunk_index})
        context_chunks = []
        for chunk in chunks:
            doc = next((r.Document for r in doc_rows if r.Document.id == chunk.document_id), None)
            if doc:
                chunk_id = f"D{chunk.document_id}-C{chunk.chunk_index}"
                context_chunks.append(
                    {
                        "id": chunk_id,
                        "text": chunk.text,
                        "document_id": chunk.document_id,
                        "title": doc.title,
                    }
                )

        logger.debug("Q&A context prepared", extra={"num_chunks": len(context_chunks)})

        # Generate answer with citations
        html = answer_question_with_citations(question, context_chunks)
        return html
    except Exception as e:
        logger.exception("Topic Q&A failed", extra={"topic_id": topic_id, "error": str(e)})
        return '<div class="qa-answer">An error occurred while generating the answer.</div>'
    finally:
        session.close()


# UI routes
@ui_bp.get("/ui/collections/<int:collection_id>/graph")
def ui_graph(collection_id: int):
    return render_template("graph.html", collection_id=collection_id)


@ui_bp.get("/ui/topics/<int:topic_id>")
def ui_topic(topic_id: int):
    # Render dynamic HTML fragment for topic details
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        t = session.get(Topic, topic_id)
        if not t:
            return "<div class='text-danger small'>Topic not found</div>"
        ins = session.scalars(select(TopicInsight).where(TopicInsight.topic_id == topic_id)).first()
        docs = session.execute(
            select(Document, DocumentTopic)
            .where(Document.id == DocumentTopic.document_id)
            .where(DocumentTopic.topic_id == topic_id)
            .order_by(DocumentTopic.relevance_score.desc())
        ).all()
        # Load chunks for each document
        doc_ids = [row.Document.id for row in docs]
        chunks_by_doc = {}
        if doc_ids:
            chunks = session.scalars(
                select(Chunk).where(Chunk.document_id.in_(doc_ids)).order_by(Chunk.document_id, Chunk.chunk_index)
            ).all()
            for chunk in chunks:
                if chunk.document_id not in chunks_by_doc:
                    chunks_by_doc[chunk.document_id] = []
                chunks_by_doc[chunk.document_id].append(chunk)
        # Related topics via relationships
        rel_rows = session.scalars(
            select(TopicRelationship).where(
                (TopicRelationship.source_topic_id == topic_id) | (TopicRelationship.target_topic_id == topic_id)
            )
        ).all()
        related = []
        for r in rel_rows:
            other_id = r.target_topic_id if r.source_topic_id == topic_id else r.source_topic_id
            other = session.get(Topic, other_id)
            if other:
                related.append({"id": other.id, "name": other.name, "similarity": r.similarity_score or 0.0})
        related.sort(key=lambda x: x["similarity"], reverse=True)
        return render_template(
            "topic_detail.html",
            topic=t,
            insight=ins,
            ranked_docs=docs,
            related_topics=related,
            chunks_by_doc=chunks_by_doc,
        )
    finally:
        session.close()


@ui_bp.get("/ui/collections/<int:collection_id>/discover/status")
def ui_discover_status(collection_id: int):
    """
    Render friendly HTML for HTMX polling.
    Stops polling automatically when job is SUCCEEDED or FAILED.
    """
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        row = session.scalars(
            select(DiscoveryJob).where(DiscoveryJob.collection_id == collection_id).order_by(DiscoveryJob.id.desc())
        ).first()
        if not row:
            status = {"status": "IDLE", "step": 0, "total": 0, "label": "No job"}
            job_id = None
        else:
            label = row.error_message or (
                "In progress"
                if row.status == JobStatusEnum.RUNNING
                else ("Done" if row.status == JobStatusEnum.SUCCEEDED else (row.error_message or "Pending"))
            )
            status = {
                "status": row.status,
                "step": row.progress_step or 0,
                "total": row.progress_total_steps or 0,
                "label": label,
            }
            job_id = row.id
        return render_template("partials/job_status.html", collection_id=collection_id, status=status, job_id=job_id)
    finally:
        session.close()


@api_bp.get("/documents/<int:document_id>/citation")
def get_document_citation(document_id: int):
    """
    Get document content and specific chunk information for citation modal.

    Query params:
    - chunk_id: Optional chunk ID in format "D{doc_id}-C{chunk_index}" (e.g., "D1-C3")
    """
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        doc = session.get(Document, document_id)
        if not doc:
            return jsonify({"error": "Document not found"}), 404

        chunk_id = request.args.get("chunk_id")
        chunk_index = None
        chunk_text = None

        if chunk_id:
            # Parse chunk_id format: "D{doc_id}-C{chunk_index}"
            try:
                if chunk_id.startswith("D") and "-C" in chunk_id:
                    parts = chunk_id.split("-C")
                    if len(parts) == 2:
                        parsed_doc_id = int(parts[0][1:])
                        chunk_index = int(parts[1])
                        if parsed_doc_id != document_id:
                            return jsonify({"error": "Chunk ID does not match document ID"}), 400

                        # Get the specific chunk
                        chunk = session.scalars(
                            select(Chunk)
                            .where(Chunk.document_id == document_id)
                            .where(Chunk.chunk_index == chunk_index)
                        ).first()

                        if chunk:
                            chunk_text = chunk.text
            except (ValueError, IndexError):
                # Invalid chunk_id format, ignore it
                pass

        # Get all chunks for this document to show context
        all_chunks = session.scalars(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
        ).all()

        chunks_data = [
            {
                "chunk_index": c.chunk_index,
                "text": c.text,
                "is_highlighted": (c.chunk_index == chunk_index) if chunk_index is not None else False,
            }
            for c in all_chunks
        ]

        return jsonify(
            {
                "document_id": doc.id,
                "title": doc.title,
                "content": doc.content or "",
                "chunk_index": chunk_index,
                "chunk_text": chunk_text,
                "chunks": chunks_data,
            }
        )
    except Exception as e:
        logger.exception("Failed to get document citation", extra={"document_id": document_id, "error": str(e)})
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


# Collections API
@api_bp.get("/collections")
def list_collections():
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        rows = session.scalars(select(Collection).order_by(Collection.created_at.desc())).all()
        return jsonify(
            [
                {
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "is_stale": c.is_stale,
                }
                for c in rows
            ]
        )
    finally:
        session.close()


@api_bp.post("/collections")
def create_collection():
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        data = request.get_json(silent=True) or {}
        if not data and request.form:
            data = {"name": request.form.get("name"), "description": request.form.get("description")}
        name = (data.get("name") or "").strip()
        description = (data.get("description") or "").strip() or None
        if not name:
            return jsonify({"error": "name is required"}), 400
        c = Collection(name=name, description=description)
        session.add(c)
        session.commit()
        logger.info("create_collection", extra={"collection_id": c.id})
        return jsonify({"id": c.id, "name": c.name, "description": c.description}), 201
    except SQLAlchemyError as e:
        session.rollback()
        logger.exception("create_collection db error")
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@api_bp.get("/collections/<int:collection_id>")
def get_collection(collection_id: int):
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        c = session.get(Collection, collection_id)
        if not c:
            return jsonify({"error": "not found"}), 404
        return jsonify(
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "is_stale": c.is_stale,
            }
        )
    finally:
        session.close()


@api_bp.delete("/collections/<int:collection_id>")
def delete_collection(collection_id: int):
    """
    Delete a collection and all its related data.

    This will cascade delete:
    - Documents (and their chunks)
    - Topics (and their relationships, insights)
    - Discovery jobs
    """
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        c = session.get(Collection, collection_id)
        if not c:
            return jsonify({"error": "not found"}), 404

        # Clear the last_discovery_job_id reference before deletion
        # This prevents foreign key constraint issues
        if c.last_discovery_job_id:
            c.last_discovery_job_id = None
            session.add(c)
            session.flush()  # Flush to clear the reference

        # Delete the collection (cascade will handle related records)
        session.delete(c)
        session.commit()

        logger.info("delete_collection", extra={"collection_id": collection_id})
        return jsonify({"status": "deleted", "id": collection_id})
    except SQLAlchemyError as e:
        session.rollback()
        logger.exception("delete_collection db error", extra={"collection_id": collection_id, "error": str(e)})
        return jsonify({"error": "Failed to delete collection: " + str(e)}), 500
    except Exception as e:
        session.rollback()
        logger.exception("delete_collection unexpected error", extra={"collection_id": collection_id, "error": str(e)})
        return jsonify({"error": "Unexpected error: " + str(e)}), 500
    finally:
        session.close()


# Collections UI (legacy /ui/*)
@ui_bp.get("/ui/collections")
def ui_collections():
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        rows = session.scalars(select(Collection).order_by(Collection.created_at.desc())).all()
        return render_template("collections.html", collections=rows)
    finally:
        session.close()


@ui_bp.get("/ui/collections/<int:collection_id>")
def ui_collection_detail(collection_id: int):
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        c = session.get(Collection, collection_id)
        if not c:
            return redirect(url_for("ui.ui_collections"))
        return render_template("collection_detail.html", collection=c)
    finally:
        session.close()


# Direct UI routes (no /ui prefix)
@ui_bp.get("/collections")
def ui_collections_direct():
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        rows = session.scalars(select(Collection).order_by(Collection.created_at.desc())).all()
        return render_template("collections.html", collections=rows)
    finally:
        session.close()


@ui_bp.get("/collections/<int:collection_id>")
def ui_collection_detail_direct(collection_id: int):
    ensure_tables_initialized()
    session = SessionLocal()
    try:
        c = session.get(Collection, collection_id)
        if not c:
            return redirect(url_for("ui.ui_collections_direct"))
        return render_template("collection_detail.html", collection=c)
    finally:
        session.close()


@ui_bp.get("/collections/<int:collection_id>/graph")
def ui_graph_direct(collection_id: int):
    return render_template("graph.html", collection_id=collection_id)
