from flask import Blueprint, jsonify, render_template, request, redirect, url_for
import os
import logging
from threading import Thread
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionLocal, ensure_tables_initialized
from app.models import Collection, Document, Topic, TopicRelationship, DiscoveryJob, JobStatusEnum, TopicInsight, DocumentTopic
from app.services.parser import extract_text_from_upload
from app.services.embeddings import get_embedding_for_text
from app.services.discovery import run_discovery

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


def _run_discovery_async(job_id: int, collection_id: int) -> None:
	"""Background thread entry: run discovery and update job row."""
	session = SessionLocal()
	try:
		job = session.get(DiscoveryJob, job_id)
		if not job:
			return
		logger.info("discovery thread start", extra={"collection_id": collection_id, "job_id": job_id})
		run_discovery(session, collection_id, job)
		# mark finished
		job = session.get(DiscoveryJob, job_id)
		if job:
			job.finished_at = datetime.utcnow()
			session.add(job)
			session.commit()
		logger.info("discovery thread done", extra={"collection_id": collection_id, "job_id": job_id})
	except Exception:
		logger.exception("discovery thread failed", extra={"collection_id": collection_id, "job_id": job_id})
		try:
			j = session.get(DiscoveryJob, job_id)
			if j:
				j.status = JobStatusEnum.FAILED
				j.error_message = "Unhandled error"
				j.finished_at = datetime.utcnow()
				session.add(j)
				session.commit()
		except Exception:
			logger.exception("failed to persist job failure")
	finally:
		session.close()


@api_bp.post("/collections/<int:collection_id>/discover")
def discover_collection(collection_id: int):
	logger.info("discover_collection start", extra={"collection_id": collection_id})
	# Create job row and run discovery in a background thread (no Celery)
	ensure_tables_initialized()
	session = SessionLocal()
	try:
		job = DiscoveryJob(collection_id=collection_id, status=JobStatusEnum.PENDING, mode="FULL", started_at=datetime.utcnow(), progress_step=0, progress_total_steps=5)
		session.add(job)
		session.flush()
		c = session.get(Collection, collection_id)
		if c:
			c.last_discovery_job_id = job.id
		session.commit()

		Thread(target=_run_discovery_async, args=(job.id, collection_id), daemon=True).start()
		return jsonify({"job_id": job.id, "collection_id": collection_id, "status": "ENQUEUED"})
	except Exception:
		logger.exception("failed to start discovery thread")
		return jsonify({"error": "failed to start discovery"}), 500
	finally:
		session.close()


@api_bp.get("/collections/<int:collection_id>/discover/status")
def discover_status(collection_id: int):
	ensure_tables_initialized()
	session = SessionLocal()
	try:
		# Last job for collection
		row = session.scalars(select(DiscoveryJob).where(DiscoveryJob.collection_id == collection_id).order_by(DiscoveryJob.id.desc())).first()
		if not row:
			return jsonify({"collection_id": collection_id, "status": "IDLE"})
		return jsonify(
			{
				"collection_id": collection_id,
				"status": row.status,
				"progress": {
					"step": row.progress_step or 0,
					"total_steps": row.progress_total_steps or 0,
					"label": row.error_message or ("In progress" if row.status == JobStatusEnum.RUNNING else ("Done" if row.status == JobStatusEnum.SUCCEEDED else (row.error_message or "Pending"))),
				},
				"error": row.error_message,
			}
		)
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
		logger.info("add_documents done", extra={"collection_id": collection_id, "accepted": accepted, "rejected_count": len(rejected)})
		return jsonify({"collection_id": collection_id, "accepted": accepted, "rejected": rejected, "status": "RECEIVED"})
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
					rejected.append({"filename": filename, "reason": f"file type not allowed (allowed: {', '.join(sorted(ALLOWED_EXTS))})"})
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
		logger.info("upload_documents_files done", extra={"collection_id": collection_id, "created_count": len(created), "rejected_count": len(rejected)})
		return jsonify({
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
		})
	except SQLAlchemyError as e:
		session.rollback()
		logger.exception("upload_documents_files db error")
		return jsonify({"error": str(e)}), 500
	finally:
		session.close()


@api_bp.get("/collections/<int:collection_id>/documents")
def list_documents_in_collection(collection_id: int):
	logger.info("list_documents start", extra={"collection_id": collection_id})
	ensure_tables_initialized()
	session = SessionLocal()
	try:
		rows = session.scalars(select(Document).where(Document.collection_id == collection_id).order_by(Document.created_at.desc())).all()
		resp = [
			{
				"id": d.id,
				"title": d.title,
				"has_embedding": (d.embedding is not None),
				"preview": d.preview,
				"created_at": d.created_at.isoformat() if d.created_at else None,
			}
			for d in rows
		]
		logger.info("list_documents done", extra={"collection_id": collection_id, "count": len(resp)})
		return jsonify(resp)
	finally:
		session.close()


@api_bp.post("/collections/<int:collection_id>/embeddings/extract")
def extract_embeddings_for_collection(collection_id: int):
	"""
	Compute and save embeddings for documents in the collection that are missing embeddings.
	This uses a deterministic mock embedding generator (no external API calls).
	"""
	logger.info("extract_embeddings start", extra={"collection_id": collection_id})
	ensure_tables_initialized()
	session = SessionLocal()
	try:
		reembed_all = (request.args.get("reembed_all") or request.form.get("reembed_all") or "").lower() in ("1", "true", "yes")
		q = select(Document).where(Document.collection_id == collection_id)
		rows = session.scalars(q).all()
		processed = 0
		for d in rows:
			if not reembed_all and d.embedding is not None:
				continue
			if not (d.content or "").strip():
				continue
			try:
				emb = get_embedding_for_text(d.content)
				d.embedding = emb
				processed += 1
			except Exception:
				logger.exception("embedding failed for doc", extra={"doc_id": d.id})
				continue
		session.commit()
		logger.info("extract_embeddings done", extra={"collection_id": collection_id, "processed": processed})
		return jsonify({"collection_id": collection_id, "processed": processed, "status": "OK"})
	except SQLAlchemyError as e:
		session.rollback()
		logger.exception("extract_embeddings db error")
		return jsonify({"error": str(e)}), 500
	finally:
		session.close()


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
		logger.info("topics_graph done", extra={"collection_id": collection_id, "nodes": len(nodes), "edges": len(edges)})
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
	question = (request.get_json(silent=True) or {}).get("question") or request.form.get("question") or ""
	# Placeholder answer that cites top two docs for the topic
	ensure_tables_initialized()
	session = SessionLocal()
	try:
		docs = session.execute(
			select(Document, DocumentTopic)
			.where(Document.id == DocumentTopic.document_id)
			.where(DocumentTopic.topic_id == topic_id)
			.order_by(DocumentTopic.relevance_score.desc())
			.limit(2)
		).all()
		cites = []
		for i, d in enumerate(docs, start=1):
			cites.append({"marker": f"[{i}]", "document_id": str(d.Document.id)})
		return jsonify(
			{
				"topic_id": topic_id,
				"question": question,
				"answer": "This is a heuristic answer. See citations for details.",
				"citations": cites,
			}
		)
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
		return render_template("topic_detail.html", topic=t, insight=ins, ranked_docs=docs)
	finally:
		session.close()


@ui_bp.get("/ui/collections/<int:collection_id>/discover/status")
def ui_discover_status(collection_id: int):
	# Render friendly HTML for HTMX polling
	ensure_tables_initialized()
	session = SessionLocal()
	try:
		row = session.scalars(select(DiscoveryJob).where(DiscoveryJob.collection_id == collection_id).order_by(DiscoveryJob.id.desc())).first()
		if not row:
			status = {"status": "IDLE", "step": 0, "total": 0, "label": "No job"}
		else:
			label = row.error_message or ("In progress" if row.status == JobStatusEnum.RUNNING else ("Done" if row.status == JobStatusEnum.SUCCEEDED else (row.error_message or "Pending")))
			status = {"status": row.status, "step": row.progress_step or 0, "total": row.progress_total_steps or 0, "label": label}
		return render_template("partials/job_status.html", collection_id=collection_id, status=status)
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
	ensure_tables_initialized()
	session = SessionLocal()
	try:
		c = session.get(Collection, collection_id)
		if not c:
			return jsonify({"error": "not found"}), 404
		session.delete(c)
		session.commit()
		logger.info("delete_collection", extra={"collection_id": collection_id})
		return jsonify({"status": "deleted", "id": collection_id})
	except SQLAlchemyError as e:
		session.rollback()
		logger.exception("delete_collection db error")
		return jsonify({"error": str(e)}), 500
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


