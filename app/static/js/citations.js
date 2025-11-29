document.addEventListener('click', function (e) {
	const el = e.target.closest('.citation');
	if (!el) return;
	const docId = el.getAttribute('data-doc-id');
	if (!docId) return;
	const target = document.getElementById('doc-' + docId);
	if (!target) return;
	target.scrollIntoView({ behavior: 'smooth', block: 'center' });
	target.classList.add('highlight');
	setTimeout(() => target.classList.remove('highlight'), 1200);
});


