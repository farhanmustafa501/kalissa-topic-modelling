"""
AI service for topic labeling, insights generation, and Q&A with citations.

This module uses OpenAI's GPT models:
- GPT-4o-mini: For topic labeling and insights (cost-effective)
- GPT-4o: For Q&A with citations (higher quality)
"""

import os
import json
import re
import logging
from typing import List, Dict, Any, Optional

from openai import OpenAI
import httpx

logger = logging.getLogger(__name__)


def _get_client() -> Optional[OpenAI]:
	"""
	Get configured OpenAI client.
	
	Returns:
		OpenAI client instance or None if API key is not set
	"""
	api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY")
	if not api_key:
		logger.warning("OPENAI_API_KEY not set, AI features will be unavailable")
		return None
	try:
		http_client = httpx.Client(timeout=60.0)
		client = OpenAI(api_key=api_key, http_client=http_client)
		return client
	except Exception as e:
		logger.exception("Failed to create OpenAI client", extra={"error": str(e)})
		return None


def generate_topic_name(representative_chunks: List[str]) -> Dict[str, Any]:
	"""
	Generate topic name, summary, and keywords using GPT-4o-mini.
	
	Uses top 5 representative chunks (closest to cluster centroid) to generate
	a concise topic name and metadata.
	
	Args:
		representative_chunks: List of text chunks representing the topic (top 5)
		
	Returns:
		Dictionary with keys: name, summary, keywords
	"""
	client = _get_client()
	if not client:
		# Fallback: use first few words from first chunk
		first_chunk = (representative_chunks[0] or "")[:200] if representative_chunks else ""
		words = first_chunk.split()[:3]
		return {
			"name": " ".join(words) if words else "Topic",
			"summary": first_chunk[:200] if first_chunk else "No summary available",
			"keywords": words[:5] if words else []
		}
	
	# Build prompt with representative chunks
	chunk_texts = "\n\n".join(
		f"<CHUNK_{i+1}>\n{chunk[:1500]}" 
		for i, chunk in enumerate(representative_chunks[:5])
	)
	
	system_prompt = """You are assigning a name to a topic derived from clustering text documents.
Analyze the representative text samples and return a concise, descriptive topic name."""
	
	user_prompt = f"""You are assigning a name to a topic derived from clustering text documents.

Here are representative samples:

{chunk_texts}

Return concise JSON:
{{
  "name": "2–4 word topic title",
  "summary": "One-sentence description",
  "keywords": ["keyword1", "keyword2", "keyword3"]
}}"""
	
	try:
		logger.debug("Generating topic name with GPT-4o-mini", extra={"num_chunks": len(representative_chunks)})
		resp = client.chat.completions.create(
			model=os.getenv("OPENAI_TOPIC_MODEL", "gpt-4o-mini"),
			messages=[
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": user_prompt},
			],
			response_format={"type": "json_object"},
			temperature=0.2,
		)
		content = resp.choices[0].message.content or "{}"
		data = json.loads(content)
		
		result = {
			"name": (data.get("name") or "Topic")[:255],  # Match DB column limit
			"summary": (data.get("summary") or "")[:600],
			"keywords": list((data.get("keywords") or [])[:5]),
		}
		logger.info("Topic name generated successfully", extra={"topic_name": result["name"]})
		return result
	except Exception as e:
		logger.exception("Failed to generate topic name", extra={"error": str(e)})
		# Fallback
		first_chunk = (representative_chunks[0] or "")[:200] if representative_chunks else ""
		words = first_chunk.split()[:3]
		return {
			"name": " ".join(words) if words else "Topic",
			"summary": first_chunk[:200] if first_chunk else "No summary available",
			"keywords": words[:5] if words else []
		}


def generate_topic_insights(representative_chunks: List[str], topic_name: str) -> Dict[str, Any]:
	"""
	Generate topic insights using GPT-4o-mini.
	
	Uses representative chunks to generate insights including summary, themes,
	questions, and related concepts.
	
	Args:
		representative_chunks: List of text chunks representing the topic (top 5)
		topic_name: Name of the topic
		
	Returns:
		Dictionary with keys: summary, themes, questions, related_concepts
	"""
	client = _get_client()
	if not client:
		# Fallback
		return {
			"summary": f"This topic covers: {topic_name}.",
			"themes": [topic_name] if topic_name else [],
			"questions": [f"What is {topic_name}?"] if topic_name else [],
			"related_concepts": []
		}
	
	# Build prompt with representative chunks
	chunk_texts = "\n\n".join(
		f"<text{i+1}>\n{chunk[:1500]}" 
		for i, chunk in enumerate(representative_chunks[:5])
	)
	
	system_prompt = """You are a helpful research assistant. Generate insights about topics derived from document clustering."""
	
	user_prompt = f"""Generate insights about this topic.

Topic: {topic_name}

Representative texts:
{chunk_texts}

Return JSON:
{{
  "summary": "2–3 sentences",
  "themes": ["theme1", "theme2", "theme3"],
  "questions": ["question1", "question2", "question3"],
  "related_concepts": ["concept1", "concept2", "concept3"]
}}"""
	
	try:
		logger.debug("Generating topic insights with GPT-4o-mini", extra={"topic_name": topic_name, "num_chunks": len(representative_chunks)})
		resp = client.chat.completions.create(
			model=os.getenv("OPENAI_INSIGHTS_MODEL", "gpt-4o-mini"),
			messages=[
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": user_prompt},
			],
			response_format={"type": "json_object"},
			temperature=0.2,
		)
		content = resp.choices[0].message.content or "{}"
		data = json.loads(content)
		
		result = {
			"summary": (data.get("summary") or "")[:600],
			"themes": list((data.get("themes") or [])[:5]),
			"questions": list((data.get("questions") or [])[:5]),
			"related_concepts": list((data.get("related_concepts") or [])[:5]),
		}
		logger.info("Topic insights generated successfully", extra={"topic_name": topic_name})
		return result
	except Exception as e:
		logger.exception("Failed to generate topic insights", extra={"error": str(e), "topic_name": topic_name})
		# Fallback
		return {
			"summary": f"This topic covers: {topic_name}.",
			"themes": [topic_name] if topic_name else [],
			"questions": [f"What is {topic_name}?"] if topic_name else [],
			"related_concepts": []
		}


def answer_question_with_citations(question: str, chunks: List[Dict[str, str]]) -> str:
	"""
	Answer a question using RAG with GPT-4o, including inline citations.
	
	This function uses GPT-4o (not mini) for higher quality answers with citations.
	Each chunk is identified with an ID like [D2-C7] for inline citation.
	
	Args:
		question: User's question
		chunks: List of chunk dictionaries with keys: id, text, document_id, title
		         Format: [{"id": "D1-C3", "text": "...", "document_id": 1, "title": "..."}, ...]
		
	Returns:
		HTML string with answer and clickable citations
	"""
	if not question or not question.strip():
		return '<div class="qa-answer">Please provide a question.</div>'
	
	if not chunks:
		return '<div class="qa-answer">No relevant context found to answer this question.</div>'
	
	client = _get_client()
	if not client:
		return '<div class="qa-answer">AI service unavailable. Please configure OPENAI_API_KEY.</div>'
	
	# Build context with chunk IDs
	context_items = []
	for chunk in chunks[:10]:  # Top 10 chunks
		chunk_id = chunk.get("id", "UNKNOWN")
		chunk_text = chunk.get("text", chunk.get("content", ""))[:1000]
		context_items.append(f"[ID: {chunk_id}] {chunk_text}")
	
	context_text = "\n\n".join(context_items)
	
	system_prompt = """You answer using ONLY the provided chunks.
Every chunk has an ID like [D2-C7].

If you use information from a chunk, cite it inline like:
"...text..." [D2-C7].

Be accurate and only cite chunks that actually contain the relevant information."""
	
	user_prompt = f"""Question:
{question}

Context:
{context_text}"""
	
	try:
		logger.debug("Generating Q&A answer with GPT-4o", extra={"question_length": len(question), "num_chunks": len(chunks)})
		resp = client.chat.completions.create(
			model=os.getenv("OPENAI_QA_MODEL", "gpt-4o"),  # Use GPT-4o for Q&A
			messages=[
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": user_prompt},
			],
			temperature=0.2,
		)
		raw_answer = (resp.choices[0].message.content or "").strip()
		logger.info("Q&A answer generated successfully", extra={"answer_length": len(raw_answer)})
	except Exception as e:
		logger.exception("Failed to generate Q&A answer", extra={"error": str(e)})
		raw_answer = "Unable to generate an AI answer at this time."
	
	# Convert [D2-C7] style citations to clickable spans
	# Map chunk IDs to document IDs for highlighting
	chunk_id_to_doc_id = {chunk.get("id"): str(chunk.get("document_id", "")) for chunk in chunks}
	
	def replace_cite(match):
		chunk_id = match.group(1)
		doc_id = chunk_id_to_doc_id.get(chunk_id, "")
		if doc_id:
			return f'<span class="citation" data-doc-id="{doc_id}" data-chunk-id="{chunk_id}">[{chunk_id}]</span>'
		return match.group(0)
	
	# Pattern matches [ID: D1-C3] or [D1-C3] formats
	html_answer = re.sub(r"\[(?:ID:\s*)?([D\d]+-C\d+)\]", replace_cite, raw_answer)
	return f'<div class="qa-answer">{html_answer}</div>'


