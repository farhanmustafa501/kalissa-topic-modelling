from flask import Blueprint, jsonify, render_template, request, redirect, url_for
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionLocal, ensure_tables_initialized
from app.models import Collection, Document

api_bp = Blueprint("api", __name__)
ui_bp = Blueprint("ui", __name__)


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


# Placeholder APIs per spec
@api_bp.post("/collections/<int:collection_id>/discover")
def discover_collection(collection_id: int):
	mode = request.args.get("mode", "full").upper()
	return jsonify(
		{
			"job_id": f"job-{collection_id}-placeholder",
			"collection_id": collection_id,
			"status": "PENDING",
			"mode": mode,
		}
	)


@api_bp.get("/collections/<int:collection_id>/discover/status")
def discover_status(collection_id: int):
	return jsonify(
		{
			"collection_id": collection_id,
			"status": "RUNNING",
			"progress": {"step": 2, "total_steps": 6, "label": "Clustering documents"},
			"error": None,
		}
	)


@api_bp.post("/collections/<int:collection_id>/documents")
def add_documents(collection_id: int):
	# Accept JSON body: { "documents": [ { "title": "...", "content": "..."}, ... ] }
	# Or form field: documents_json='[{"title": "...","content":"..."}]'
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
		accepted = 0
		for doc in documents:
			title = (doc or {}).get("title")
			content = (doc or {}).get("content")
			if not title:
				continue
			preview = (content or "")[:200] if content else None
			session.add(Document(collection_id=collection_id, title=title, content=content, preview=preview))
			accepted += 1
		session.commit()
		return jsonify({"collection_id": collection_id, "accepted": accepted, "status": "RECEIVED"})
	except SQLAlchemyError as e:
		session.rollback()
		return jsonify({"error": str(e)}), 500
	finally:
		session.close()


@api_bp.get("/collections/<int:collection_id>/topics/graph")
def topics_graph(collection_id: int):
	# Minimal placeholder graph
	data = {
		"nodes": [
			{"id": "t1", "label": "Supply Chain", "size_score": 0.82, "document_count": 6},
			{"id": "t2", "label": "Logistics", "size_score": 0.55, "document_count": 3},
			{"id": "t3", "label": "Inventory", "size_score": 0.65, "document_count": 4},
		],
		"edges": [
			{"source": "t1", "target": "t2", "weight": 0.41, "type": "RELATED"},
			{"source": "t1", "target": "t3", "weight": 0.35, "type": "RELATED"},
		],
	}
	return jsonify(data)


@api_bp.get("/topics/<int:topic_id>")
def topic_detail(topic_id: int):
	# Placeholder topic detail JSON
	return jsonify(
		{
			"id": topic_id,
			"name": f"Topic {topic_id}",
			"insights": {
				"summary": "This topic covers supply chain strategies and common bottlenecks.",
				"key_themes": ["Forecasting", "Distribution", "Vendor Management"],
				"common_questions": ["How to optimize routes?", "How to reduce lead time?"],
				"related_concepts": ["Just-In-Time", "Safety Stock"],
			},
			"documents": [
				{
					"id": "d1",
					"title": "Doc A",
					"preview": "First 200 chars lorem ipsum...",
					"relevance_score": 0.92,
					"is_primary": True,
				},
				{
					"id": "d2",
					"title": "Doc B",
					"preview": "Another preview...",
					"relevance_score": 0.74,
					"is_primary": False,
				},
			],
			"related_topics": [{"id": "t2", "name": "Logistics", "similarity": 0.41}],
		}
	)


@api_bp.post("/topics/<int:topic_id>/qa")
def topic_qa(topic_id: int):
	question = (request.get_json(silent=True) or {}).get("question") or request.form.get("question") or ""
	return jsonify(
		{
			"topic_id": topic_id,
			"question": question,
			"answer": "Placeholder answer with citations [1] and [2].",
			"citations": [
				{"marker": "[1]", "document_id": "d1"},
				{"marker": "[2]", "document_id": "d2"},
			],
		}
	)


# UI routes
@ui_bp.get("/ui/collections/<int:collection_id>/graph")
def ui_graph(collection_id: int):
	return render_template("graph.html", collection_id=collection_id)


@ui_bp.get("/ui/topics/<int:topic_id>")
def ui_topic(topic_id: int):
	# In a real app we would call services; for now, use placeholder HTML fragment.
	return render_template("topic_detail.html", topic_id=topic_id)


@ui_bp.get("/ui/collections/<int:collection_id>/discover/status")
def ui_discover_status(collection_id: int):
	# Render friendly HTML for HTMX polling
	status = {"status": "RUNNING", "step": 2, "total": 6, "label": "Clustering documents"}
	return render_template("partials/job_status.html", collection_id=collection_id, status=status)


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
		return jsonify({"id": c.id, "name": c.name, "description": c.description}), 201
	except SQLAlchemyError as e:
		session.rollback()
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


# Collections UI
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


