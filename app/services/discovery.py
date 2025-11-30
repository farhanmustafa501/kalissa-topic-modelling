from __future__ import annotations

import math
from typing import List, Tuple, Dict

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.db import SessionLocal
from app.models import (
	Collection,
	Document,
	Topic,
	DocumentTopic,
	TopicRelationship,
	TopicInsight,
	DiscoveryJob,
	JobStatusEnum,
)
from app.services.embeddings import get_embedding_for_text


def _update_job(session, job: DiscoveryJob, step: int, total: int, label: str, status: str | None = None) -> None:
	job.progress_step = step
	job.progress_total_steps = total
	job.error_message = None
	if status:
		job.status = status
	session.add(job)
	session.commit()


def _ensure_embeddings(session, collection_id: int, job: DiscoveryJob | None) -> List[Document]:
	docs = session.query(Document).filter(Document.collection_id == collection_id).all()
	total = len(docs)
	if job:
		_update_job(session, job, 1, 5, "Embedding documents", status=JobStatusEnum.RUNNING)
	for idx, d in enumerate(docs, start=1):
		if d.embedding is None and (d.content or "").strip():
			d.embedding = get_embedding_for_text(d.content or "")
		if job and idx % 10 == 0:
			_update_job(session, job, 1, 5, f"Embedding documents ({idx}/{total})")
	session.commit()
	return docs


def _choose_k(n_docs: int) -> int:
	if n_docs <= 2:
		return n_docs
	return max(2, min(8, int(round(math.sqrt(n_docs)))))


def _extract_keywords(texts: List[str], top_k: int = 6) -> List[str]:
	if not texts:
		return []
	vec = TfidfVectorizer(max_features=5000, stop_words="english")
	X = vec.fit_transform(texts)
	mean_scores = np.asarray(X.mean(axis=0)).ravel()
	indices = np.argsort(mean_scores)[::-1][:top_k]
	feature_names = np.array(vec.get_feature_names_out())
	return [t for t in feature_names[indices] if t]


def _topic_name_from_keywords(keywords: List[str]) -> str:
	return " ".join(keywords[:3]) if keywords else "Topic"


def _build_relationships(topic_id_to_centroid: Dict[int, np.ndarray]) -> List[Tuple[int, int, float]]:
	ids = list(topic_id_to_centroid.keys())
	if len(ids) < 2:
		return []
	centroids = np.vstack([topic_id_to_centroid[i] for i in ids])
	sim = cosine_similarity(centroids)
	edges: List[Tuple[int, int, float]] = []
	for i, src_id in enumerate(ids):
		for j, dst_id in enumerate(ids):
			if j <= i:
				continue
			w = float(sim[i, j])
			if w >= 0.2:
				edges.append((src_id, dst_id, w))
	return edges


def run_discovery(session: SessionLocal, collection_id: int, job: DiscoveryJob) -> None:
	try:
		_update_job(session, job, 0, 5, "Starting", status=JobStatusEnum.RUNNING)

		# 1. Ensure embeddings
		docs = _ensure_embeddings(session, collection_id, job)
		emb_docs = [d for d in docs if d.embedding is not None]
		if not emb_docs:
			_update_job(session, job, 5, 5, "No embeddable documents", status=JobStatusEnum.SUCCEEDED)
			return

		# 2. Cluster
		_update_job(session, job, 2, 5, "Clustering documents")
		X = np.vstack([np.array(d.embedding, dtype=np.float32) for d in emb_docs])
		k = _choose_k(len(emb_docs))
		model = KMeans(n_clusters=k, n_init=10, random_state=42)
		labels = model.fit_predict(X)
		centroids = model.cluster_centers_

		# 3. Reset old topics
		_update_job(session, job, 3, 5, "Resetting previous topics")
		old_topics = session.query(Topic).filter(Topic.collection_id == collection_id).all()
		for t in old_topics:
			session.delete(t)
		session.commit()

		# 4. Create topics and assignments
		_update_job(session, job, 4, 5, "Generating topics and insights")
		cluster_to_docs: Dict[int, List[Document]] = {}
		for d, label in zip(emb_docs, labels):
			cluster_to_docs.setdefault(int(label), []).append(d)

		label_to_topic: Dict[int, Topic] = {}
		label_to_centroid: Dict[int, np.ndarray] = {}
		for label, group_docs in cluster_to_docs.items():
			texts = [d.content or "" for d in group_docs]
			keywords = _extract_keywords(texts, top_k=8)
			name = _topic_name_from_keywords(keywords)
			topic = Topic(collection_id=collection_id, name=name, document_count=len(group_docs), size_score=float(len(group_docs)) / float(len(emb_docs)))
			session.add(topic)
			session.flush()
			label_to_topic[label] = topic
			label_to_centroid[topic.id] = centroids[int(label)]

			# Insights
			insight = TopicInsight(topic_id=topic.id, summary=f"This topic covers: {', '.join(keywords[:5])}.", key_themes=keywords[:5], common_questions=None, related_concepts=None)
			session.add(insight)
		session.commit()

		# DocumentTopic assignments with relevance
		for d, label in zip(emb_docs, labels):
			topic = label_to_topic[int(label)]
			centroid = label_to_centroid[topic.id]
			v = np.array(d.embedding, dtype=np.float32)
			relevance = float(cosine_similarity(v.reshape(1, -1), centroid.reshape(1, -1))[0][0])
			session.add(DocumentTopic(document_id=d.id, topic_id=topic.id, relevance_score=relevance, is_primary=True))
		session.commit()

		# 5. Relationships
		_update_job(session, job, 5, 5, "Linking related topics")
		for (src_topic_id, dst_topic_id, w) in _build_relationships(label_to_centroid):
			session.add(TopicRelationship(collection_id=collection_id, source_topic_id=src_topic_id, target_topic_id=dst_topic_id, similarity_score=w, relationship_type="RELATED"))
		session.commit()

		_update_job(session, job, 5, 5, "Done", status=JobStatusEnum.SUCCEEDED)
	except Exception as e:
		# Persist failure and message
		job.status = JobStatusEnum.FAILED
		job.error_message = str(e)[:500]
		session.add(job)
		session.commit()


