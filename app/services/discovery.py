"""
Topic discovery service using K-means clustering on document chunks.

This module implements the full pipeline:
1. Parse PDFs → Raw Text
2. Chunk text (800-1200 tokens, 100-200 overlap)
3. Embed chunks (text-embedding-3-small)
4. K-means clustering (k = sqrt(N_chunks / 2))
5. Topic labeling via GPT-4o-mini (using representative chunks)
6. Topic insights via GPT-4o-mini
7. Build topic relationships (cosine similarity > 0.25)
8. Rank documents per topic (average chunk similarity)
"""

from __future__ import annotations

import logging
import math

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    Chunk,
    DiscoveryJob,
    Document,
    DocumentTopic,
    JobStatusEnum,
    Topic,
    TopicInsight,
    TopicRelationship,
)
from app.services.ai import generate_topic_insights, generate_topic_name
from app.services.chunking import split_text
from app.services.embeddings import get_embeddings_batch

logger = logging.getLogger(__name__)

# Relationship threshold: topics with similarity > 0.25 are linked
RELATIONSHIP_THRESHOLD = 0.25

# Primary document threshold: documents with avg similarity > 0.70 are primary
PRIMARY_DOC_THRESHOLD = 0.70


def _update_job(
    session, job: DiscoveryJob, step: int, total: int, label: str, status: JobStatusEnum | None = None
) -> None:
    """
    Update discovery job progress.

    Args:
            session: Database session
            job: Discovery job to update
            step: Current step number
            total: Total number of steps
            label: Progress label
            status: Optional status to set
    """
    job.progress_step = step
    job.progress_total_steps = total
    job.error_message = None
    if status:
        job.status = status
    session.add(job)
    session.commit()
    logger.debug("Job progress updated", extra={"job_id": job.id, "step": step, "total": total, "label": label})


def _chunk_and_embed_documents(session, collection_id: int, job: DiscoveryJob | None) -> list[Chunk]:
    """
    Chunk documents and generate embeddings for chunks.

    This function:
    1. Gets all documents in the collection
    2. Splits each document into chunks
    3. Generates embeddings for all chunks in batches
    4. Stores chunks in the database

    Args:
            session: Database session
            collection_id: Collection ID
            job: Optional discovery job for progress updates

    Returns:
            List of Chunk objects with embeddings
    """
    logger.info("Starting chunking and embedding", extra={"collection_id": collection_id})

    if job:
        _update_job(session, job, 1, 10, "Chunking documents", status=JobStatusEnum.RUNNING)

    # Get all documents
    docs = session.scalars(select(Document).where(Document.collection_id == collection_id)).all()
    logger.info("Found documents", extra={"collection_id": collection_id, "num_docs": len(docs)})

    if not docs:
        logger.warning("No documents found in collection", extra={"collection_id": collection_id})
        return []

    all_chunks = []
    all_chunk_texts = []

    # Chunk each document
    for doc_idx, doc in enumerate(docs, start=1):
        if not (doc.content or "").strip():
            logger.debug("Skipping document with no content", extra={"doc_id": doc.id})
            continue

        # Split document into chunks
        chunk_texts = split_text(doc.content or "")
        if not chunk_texts:
            logger.debug("No chunks created for document", extra={"doc_id": doc.id})
            continue

        logger.debug("Document chunked", extra={"doc_id": doc.id, "num_chunks": len(chunk_texts)})

        # Create chunk records (without embeddings initially)
        for chunk_idx, chunk_text in enumerate(chunk_texts):
            chunk = Chunk(document_id=doc.id, chunk_index=chunk_idx, text=chunk_text, embedding=None)
            session.add(chunk)
            all_chunks.append(chunk)
            all_chunk_texts.append(chunk_text)

        if job and doc_idx % 5 == 0:
            _update_job(session, job, 1, 10, f"Chunking documents ({doc_idx}/{len(docs)})")

    session.flush()  # Flush to get chunk IDs
    logger.info("Chunks created", extra={"num_chunks": len(all_chunks)})

    # Generate embeddings in batches
    if job:
        _update_job(session, job, 2, 10, "Generating embeddings for chunks")

    logger.info("Generating embeddings", extra={"num_chunks": len(all_chunk_texts)})
    embeddings = get_embeddings_batch(all_chunk_texts, batch_size=100)

    # Assign embeddings to chunks
    for chunk, embedding in zip(all_chunks, embeddings, strict=False):
        chunk.embedding = embedding

    session.commit()
    logger.info("Chunking and embedding completed", extra={"num_chunks": len(all_chunks)})

    return all_chunks


def _choose_k(n_chunks: int) -> int:
    """
    Choose optimal k for K-means clustering.

    Formula: k = sqrt(N_chunks / 2)

    Args:
            n_chunks: Number of chunks to cluster

    Returns:
            Optimal number of clusters
    """
    if n_chunks <= 2:
        return max(1, n_chunks)

    k = int((n_chunks / 2) ** 0.5)
    # Ensure k is at least 2 and at most n_chunks
    k = max(2, min(k, n_chunks))

    logger.debug("K-means k chosen", extra={"n_chunks": n_chunks, "k": k})
    return k


def _get_representative_chunks(chunks: list[Chunk], centroid: np.ndarray, top_n: int = 5) -> list[str]:
    """
    Get top N chunks closest to cluster centroid.

    These representative chunks are used for topic labeling and insights.

    Args:
            chunks: List of chunks in the cluster
            centroid: Cluster centroid vector
            top_n: Number of representative chunks to return

    Returns:
            List of chunk text strings
    """
    if not chunks:
        return []

    # Get embeddings for chunks
    chunk_embeddings = []
    valid_chunks = []
    for chunk in chunks:
        if chunk.embedding:
            chunk_embeddings.append(np.array(chunk.embedding, dtype=np.float32))
            valid_chunks.append(chunk)

    if not chunk_embeddings:
        return []

    # Compute cosine similarities
    X = np.vstack(chunk_embeddings)
    sims = cosine_similarity([centroid], X)[0]

    # Get top N indices
    top_indices = sims.argsort()[-top_n:][::-1]

    representative_texts = [valid_chunks[i].text for i in top_indices]

    logger.debug(
        "Representative chunks selected", extra={"cluster_size": len(chunks), "top_n": len(representative_texts)}
    )

    return representative_texts


def _build_relationships(topic_id_to_centroid: dict[int, np.ndarray]) -> list[tuple[int, int, float]]:
    """
    Build topic relationships based on cosine similarity of centroids.

    Topics with similarity > RELATIONSHIP_THRESHOLD are linked.

    Args:
            topic_id_to_centroid: Dictionary mapping topic IDs to centroid vectors

    Returns:
            List of (source_topic_id, target_topic_id, similarity_score) tuples
    """
    ids = list(topic_id_to_centroid.keys())
    if len(ids) < 2:
        return []

    centroids = np.vstack([topic_id_to_centroid[i] for i in ids])
    sim_matrix = cosine_similarity(centroids)

    edges: list[tuple[int, int, float]] = []
    for i, src_id in enumerate(ids):
        for j, dst_id in enumerate(ids):
            if j <= i:
                continue
            similarity = float(sim_matrix[i, j])
            if similarity > RELATIONSHIP_THRESHOLD:
                edges.append((src_id, dst_id, similarity))

    logger.info("Topic relationships built", extra={"num_topics": len(ids), "num_relationships": len(edges)})

    return edges


def _compute_doc_relevance(doc_chunks: list[Chunk], centroid: np.ndarray) -> float:
    """
    Compute document relevance score as average similarity of chunks to topic centroid.

    Args:
            doc_chunks: List of chunks from the document
            centroid: Topic centroid vector

    Returns:
            Average similarity score (0.0 to 1.0)
    """
    if not doc_chunks:
        return 0.0

    # Get embeddings for chunks that have them
    chunk_embeddings = []
    for chunk in doc_chunks:
        # Check if embedding exists and is not None/empty (handle numpy arrays properly)
        if chunk.embedding is not None:
            embedding_array = np.array(chunk.embedding, dtype=np.float32)
            if embedding_array.size > 0:
                chunk_embeddings.append(embedding_array)

    if not chunk_embeddings:
        return 0.0

    # Compute similarities
    X = np.vstack(chunk_embeddings)
    sims = cosine_similarity(X, [centroid]).flatten()

    avg_similarity = float(sims.mean())
    # Clamp similarity to [0.0, 1.0] to handle floating point precision issues
    return max(0.0, min(1.0, avg_similarity))


def run_discovery(session: SessionLocal, collection_id: int, job: DiscoveryJob) -> None:
    """
    Run the complete topic discovery pipeline.

    Pipeline steps:
    1. Chunk documents and generate embeddings
    2. K-means clustering on chunks
    3. Create topics with GPT-4o-mini labeling
    4. Generate insights with GPT-4o-mini
    5. Build topic relationships
    6. Rank documents per topic

    Args:
            session: Database session
            collection_id: Collection ID
            job: Discovery job record
    """
    try:
        logger.info("Starting topic discovery", extra={"collection_id": collection_id, "job_id": job.id})
        _update_job(session, job, 0, 10, "Starting", status=JobStatusEnum.RUNNING)

        # Step 1: Chunk documents and generate embeddings
        chunks = _chunk_and_embed_documents(session, collection_id, job)
        chunks_with_embeddings = [c for c in chunks if c.embedding is not None]

        if not chunks_with_embeddings:
            logger.warning("No chunks with embeddings found", extra={"collection_id": collection_id})
            _update_job(session, job, 10, 10, "No embeddable chunks", status=JobStatusEnum.SUCCEEDED)
            return

        logger.info("Chunks ready for clustering", extra={"num_chunks": len(chunks_with_embeddings)})

        # Step 2: K-means clustering
        if job:
            _update_job(session, job, 3, 10, "Clustering chunks")

        X = np.vstack([np.array(c.embedding, dtype=np.float32) for c in chunks_with_embeddings])
        k = _choose_k(len(chunks_with_embeddings))

        logger.info("Running K-means", extra={"n_chunks": len(chunks_with_embeddings), "k": k})
        model = KMeans(n_clusters=k, n_init=10, random_state=42, max_iter=300)
        labels = model.fit_predict(X)
        centroids = model.cluster_centers_

        logger.info("Clustering completed", extra={"num_clusters": k})

        # Step 3: Reset old topics
        if job:
            _update_job(session, job, 4, 10, "Resetting previous topics")

        old_topics = session.scalars(select(Topic).where(Topic.collection_id == collection_id)).all()
        for t in old_topics:
            session.delete(t)
        session.commit()

        # Step 4: Create topics and generate labels/insights
        if job:
            _update_job(session, job, 5, 10, "Generating topic labels")

        # Group chunks by cluster
        cluster_to_chunks: dict[int, list[Chunk]] = {}
        for chunk, label in zip(chunks_with_embeddings, labels, strict=False):
            cluster_to_chunks.setdefault(int(label), []).append(chunk)

        label_to_topic: dict[int, Topic] = {}
        topic_id_to_centroid: dict[int, np.ndarray] = {}

        for label, cluster_chunks in cluster_to_chunks.items():
            centroid = centroids[int(label)]

            # Get representative chunks (top 5 closest to centroid)
            representative_texts = _get_representative_chunks(cluster_chunks, centroid, top_n=5)

            # Generate topic name using GPT-4o-mini
            if job:
                _update_job(session, job, 6, 10, f"Labeling topic {label + 1}/{len(cluster_to_chunks)}")

            topic_metadata = generate_topic_name(representative_texts)
            topic_name = topic_metadata.get("name", f"Topic {label + 1}")

            # Count unique documents in this cluster
            doc_ids = set(c.document_id for c in cluster_chunks)
            document_count = len(doc_ids)

            # Calculate size score (log-based for better visualization)
            max_docs = (
                max(len(set(c.document_id for c in chunks)) for chunks in cluster_to_chunks.values())
                if cluster_to_chunks
                else 1
            )
            size_score = min(1.0, math.log(document_count + 1) / math.log(max_docs + 1))

            # Create topic
            topic = Topic(
                collection_id=collection_id,
                name=topic_name,
                document_count=document_count,
                size_score=size_score,
            )
            session.add(topic)
            session.flush()

            label_to_topic[label] = topic
            topic_id_to_centroid[topic.id] = centroid

            # Generate insights using GPT-4o-mini
            if job:
                _update_job(session, job, 7, 10, f"Generating insights for topic {label + 1}")

            insights = generate_topic_insights(representative_texts, topic_name)
            insight = TopicInsight(
                topic_id=topic.id,
                summary=insights.get("summary"),
                key_themes=insights.get("themes"),
                common_questions=insights.get("questions"),
                related_concepts=insights.get("related_concepts"),
            )
            session.add(insight)

        session.commit()
        logger.info("Topics created", extra={"num_topics": len(label_to_topic)})

        # Step 5: Assign documents to topics and rank them
        if job:
            _update_job(session, job, 8, 10, "Ranking documents per topic")

        # Group chunks by document
        doc_id_to_chunks: dict[int, list[Chunk]] = {}
        for chunk in chunks_with_embeddings:
            doc_id_to_chunks.setdefault(chunk.document_id, []).append(chunk)

        # For each document, compute relevance to each topic
        for doc_id, doc_chunks in doc_id_to_chunks.items():
            # Compute similarity to all topic centroids
            all_scores: list[tuple[int, float]] = []
            for topic_id, centroid in topic_id_to_centroid.items():
                score = _compute_doc_relevance(doc_chunks, centroid)
                all_scores.append((topic_id, score))

            # Sort by score
            all_scores.sort(key=lambda x: x[1], reverse=True)

            # Primary topic (highest score)
            if all_scores:
                primary_topic_id, primary_score = all_scores[0]
                is_primary = primary_score >= PRIMARY_DOC_THRESHOLD

                session.add(
                    DocumentTopic(
                        document_id=doc_id,
                        topic_id=primary_topic_id,
                        relevance_score=primary_score,
                        is_primary=is_primary,
                    )
                )

                # Secondary topics (if score is high enough)
                for topic_id, score in all_scores[1:]:
                    if score >= 0.6:  # Secondary threshold
                        session.add(
                            DocumentTopic(
                                document_id=doc_id,
                                topic_id=topic_id,
                                relevance_score=score,
                                is_primary=False,
                            )
                        )

        session.commit()
        logger.info("Document-topic assignments completed")

        # Step 6: Build topic relationships
        if job:
            _update_job(session, job, 9, 10, "Building topic relationships")

        for src_topic_id, dst_topic_id, similarity in _build_relationships(topic_id_to_centroid):
            session.add(
                TopicRelationship(
                    collection_id=collection_id,
                    source_topic_id=src_topic_id,
                    target_topic_id=dst_topic_id,
                    similarity_score=similarity,
                    relationship_type="SIMILAR",
                )
            )

        session.commit()
        logger.info("Topic relationships created")

        # Complete
        _update_job(session, job, 10, 10, "Done", status=JobStatusEnum.SUCCEEDED)
        logger.info("Topic discovery completed successfully", extra={"collection_id": collection_id, "job_id": job.id})

    except Exception as e:
        logger.exception(
            "Topic discovery failed", extra={"collection_id": collection_id, "job_id": job.id, "error": str(e)}
        )
        # Persist failure
        job.status = JobStatusEnum.FAILED
        job.error_message = str(e)[:500]
        session.add(job)
        session.commit()
