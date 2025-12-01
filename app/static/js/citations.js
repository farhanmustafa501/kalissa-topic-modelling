// Initialize citation click handler when DOM is ready
(function() {
	'use strict';
	
	// Wait for DOM to be ready
	function initCitations() {
		console.log('Initializing citation click handler');
		
		// Handle citation clicks - use event delegation for dynamically added content
		document.addEventListener('click', function (e) {
			// Check if clicked element or its parent is a citation
			let el = e.target;
			
			// If clicked element is not a citation, check if it's inside one
			if (!el.classList || !el.classList.contains('citation')) {
				el = el.closest && el.closest('.citation');
			}
			
			if (!el) return;
			
			// Prevent default behavior
			e.preventDefault();
			e.stopPropagation();
			
			const docId = el.getAttribute('data-doc-id');
			const chunkId = el.getAttribute('data-chunk-id');
			
			if (!docId) {
				console.warn('Citation clicked but no data-doc-id found', el);
				return;
			}
			
			console.log('Citation clicked:', { docId, chunkId, element: el });
			
			// Open citation modal
			openCitationModal(docId, chunkId);
		});
		
		console.log('Citation click handler initialized');
	}
	
	/**
	 * Open citation modal with document content and highlighted chunk
	 */
	async function openCitationModal(docId, chunkId) {
		const modal = document.getElementById('citationModal');
		const modalContent = document.getElementById('citation-modal-content');
		const modalLabel = document.getElementById('citationModalLabel');
		
		if (!modal || !modalContent) {
			console.error('Citation modal not found');
			alert('Citation preview not available. Document ID: ' + docId);
			return;
		}
		
		// Show loading state
		modalContent.innerHTML = `
			<div class="text-center py-5">
				<div class="spinner-border text-primary" role="status">
					<span class="visually-hidden">Loading...</span>
				</div>
				<p class="text-muted mt-3">Loading document...</p>
			</div>
		`;
		
		// Open modal
		const bsModal = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
		bsModal.show();
		
		try {
			// Build API URL
			let apiUrl = `/api/documents/${docId}/citation`;
			if (chunkId) {
				apiUrl += `?chunk_id=${encodeURIComponent(chunkId)}`;
			}
			
			// Fetch document and chunk data
			const response = await fetch(apiUrl);
			if (!response.ok) {
				throw new Error('Failed to load document');
			}
			
			const data = await response.json();
			
			// Render document content with highlighted chunk
			let contentHtml = `
				<div class="citation-document-header mb-4 pb-3 border-bottom">
					<h6 class="fw-bold mb-2">${escapeHtml(data.title)}</h6>
					${data.chunk_index !== null ? `<span class="badge bg-primary">Chunk ${data.chunk_index}</span>` : ''}
				</div>
			`;
			
			// If we have a specific chunk, show it highlighted with context
			if (data.chunk_text && data.chunk_index !== null) {
				contentHtml += `
					<div class="citation-chunk-highlight mb-4">
						<div class="citation-chunk-header mb-2">
							<strong class="text-primary">Cited Section:</strong>
						</div>
						<div class="citation-chunk-content p-3 border rounded bg-light">
							${escapeHtml(data.chunk_text)}
						</div>
					</div>
				`;
			}
			
			// Show full document content with highlighted chunk
			if (data.content) {
				let documentContent = escapeHtml(data.content);
				
				// If we have a chunk, highlight it in the full document
				if (data.chunk_text && data.chunk_index !== null) {
					const chunkTextEscaped = escapeHtml(data.chunk_text);
					// Try to find and highlight the chunk text in the document
					// Use a simple approach: find the chunk text and wrap it
					const chunkTextPattern = chunkTextEscaped.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
					const regex = new RegExp(`(${chunkTextPattern})`, 'gi');
					documentContent = documentContent.replace(regex, '<mark class="citation-highlight">$1</mark>');
				}
				
				contentHtml += `
					<div class="citation-full-document">
						<div class="citation-document-header mb-2">
							<strong>Full Document:</strong>
						</div>
						<div class="citation-document-content p-3 border rounded" style="max-height: 500px; overflow-y: auto; white-space: pre-wrap; font-family: inherit; line-height: 1.6;">
							${documentContent}
						</div>
					</div>
				`;
			} else {
				contentHtml += `
					<div class="alert alert-info">
						<p class="mb-0">No document content available.</p>
					</div>
				`;
			}
			
			modalContent.innerHTML = contentHtml;
			
			// Scroll to highlighted chunk if it exists
			if (data.chunk_text && data.chunk_index !== null) {
				setTimeout(() => {
					// First scroll to the highlighted chunk section
					const chunkElement = modalContent.querySelector('.citation-chunk-content');
					if (chunkElement) {
						chunkElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
					}
					
					// Then scroll to the highlighted text in the full document
					setTimeout(() => {
						const highlightedText = modalContent.querySelector('.citation-highlight');
						if (highlightedText) {
							const docContent = modalContent.querySelector('.citation-document-content');
							if (docContent) {
								// Scroll within the document content container
								const textOffset = highlightedText.offsetTop - docContent.offsetTop;
								docContent.scrollTo({
									top: Math.max(0, textOffset - 100),
									behavior: 'smooth'
								});
							}
						}
					}, 500);
				}, 300);
			}
			
		} catch (error) {
			console.error('Error loading citation:', error);
			modalContent.innerHTML = `
				<div class="alert alert-danger">
					<p class="mb-0"><strong>Error:</strong> Failed to load document citation. Please try again.</p>
				</div>
			`;
		}
	}
	
	/**
	 * Escape HTML to prevent XSS
	 */
	function escapeHtml(text) {
		if (!text) return '';
		const div = document.createElement('div');
		div.textContent = text;
		return div.innerHTML;
	}
	
	// Initialize when DOM is ready
	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', initCitations);
	} else {
		// DOM is already ready
		initCitations();
	}
})();



