(function () {
  var list = document.getElementById('document-list');
  if (!list) return;

  var MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

  function esc(s) {
    return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function fmtDate(iso) {
    if (!iso) return '';
    var parts = iso.split('-');
    if (parts.length !== 3) return iso;
    var m = parseInt(parts[1], 10) - 1;
    var mon = MONTHS[m] || parts[1];
    return mon + ' ' + parseInt(parts[2], 10) + ', ' + parts[0];
  }

  function docFileHref(doc) {
    return doc.fileUrl.indexOf('http') === 0 ? doc.fileUrl : '/' + doc.fileUrl;
  }

  // Browsers reliably preview PDFs inline; DOC/DOCX has no native preview,
  // so "View" becomes a download for those — same file either way.
  function isPreviewable(ext) {
    return ext === 'pdf';
  }

  // The `download` attribute on <a> is silently ignored by browsers when
  // the href is cross-origin (our files are served from Supabase storage,
  // a different origin than the site) — the browser just navigates the
  // current tab to the raw file instead of downloading it. Fetching the
  // file as a blob and downloading via a blob: URL forces a real download
  // regardless of origin, without ever leaving the current page.
  function triggerDownload(url, filename) {
    fetch(url, { mode: 'cors' })
      .then(function (r) {
        if (!r.ok) throw new Error('download fetch failed');
        return r.blob();
      })
      .then(function (blob) {
        var blobUrl = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 1000);
      })
      .catch(function () {
        // CORS-blocked or network error — fall back to a new tab rather
        // than navigating the current page away.
        window.open(url, '_blank', 'noopener');
      });
  }

  function renderDocItem(doc) {
    var bits = [];
    if (doc.docNumber) bits.push('No. ' + esc(doc.docNumber));
    if (doc.publicationDate) bits.push(fmtDate(doc.publicationDate));
    var meta = bits.length ? '<span class="td-doc-meta">' + bits.join(' &middot; ') + '</span>' : '';
    var href = docFileHref(doc);
    var ext = (doc.fileType || 'pdf').toLowerCase();
    var dlName = esc(doc.title || 'document') + '.' + ext;
    var previewable = isPreviewable(ext);
    var viewAttrs = previewable ? 'target="_blank" rel="noopener"' : 'data-force-download="1"';
    // Allow Download only hides the separate Download button — View keeps
    // its existing behavior either way (inline preview for PDFs, or a
    // force-download fallback for DOC/DOCX, since those have no inline
    // preview to show).
    var downloadBtn = doc.allowDownload === false ? '' :
      '<a class="btn btn-small" href="' + href + '" data-filename="' + dlName + '" data-force-download="1">Download</a>';
    return '<div class="td-doc-item">'
      + '<div class="td-doc-info"><strong>' + esc(doc.title) + '</strong>' + meta + '</div>'
      + '<div class="td-doc-actions">'
      +   '<a class="btn btn-small btn-outline" href="' + href + '" data-filename="' + dlName + '" ' + viewAttrs + '>View</a>'
      +   downloadBtn
      + '</div>'
      + '</div>';
  }

  function buildCategory(cat, docs, allEntries) {
    var row = document.createElement('div');
    row.className = 'doc-row td-category-row reveal';

    var body = document.createElement('div');
    var count = docs.length;
    body.innerHTML = '<strong>' + esc(cat.name) + '</strong><span>'
      + (count ? count + (count === 1 ? ' Document' : ' Documents') : 'No Documents Available')
      + '</span>';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'td-toggle-btn';
    btn.setAttribute('aria-expanded', 'false');
    btn.setAttribute('aria-label', 'Toggle ' + cat.name + ' documents');
    btn.innerHTML = '<svg class="td-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
      + '<path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    var panel = document.createElement('div');
    panel.className = 'td-doclist';

    var built = false;
    function buildPanelContent() {
      if (built) return;
      built = true;
      panel.innerHTML = docs.length
        ? docs.map(renderDocItem).join('')
        : '<p class="td-empty">No Documents Available</p>';
    }

    var entry = { btn: btn, panel: panel, row: row, buildPanelContent: buildPanelContent };
    allEntries.push(entry);

    function closeEntry(e) {
      e.btn.setAttribute('aria-expanded', 'false');
      e.panel.classList.remove('td-open');
      e.row.classList.remove('td-open');
    }

    // Single listener on the whole row: header (icon + title + count +
    // button) all share this one toggle. Clicks inside the document list
    // itself (View/Download links) are excluded so they never collapse
    // the panel they belong to.
    row.addEventListener('click', function (event) {
      if (event.target.closest('.td-doclist')) return;
      var isOpen = btn.getAttribute('aria-expanded') === 'true';
      // Accordion: only one category open at a time.
      allEntries.forEach(function (e) { if (e !== entry) closeEntry(e); });
      if (isOpen) {
        closeEntry(entry);
      } else {
        buildPanelContent();
        btn.setAttribute('aria-expanded', 'true');
        panel.classList.add('td-open');
        row.classList.add('td-open');
      }
    });

    row.appendChild(body);
    row.appendChild(btn);
    row.appendChild(panel);
    return row;
  }

  // Delegated: catches Download links (always) and View links for
  // non-previewable files (DOC/DOCX), across every category panel.
  list.addEventListener('click', function (event) {
    var link = event.target.closest('a[data-force-download]');
    if (!link) return;
    event.preventDefault();
    triggerDownload(link.getAttribute('href'), link.getAttribute('data-filename') || 'document');
  });

  function render(categories, docs) {
    var byCategory = {};
    docs.forEach(function (d) {
      (byCategory[d.categoryId] = byCategory[d.categoryId] || []).push(d);
    });
    list.innerHTML = '';
    var allEntries = [];
    categories.forEach(function (cat) {
      list.appendChild(buildCategory(cat, byCategory[cat.id] || [], allEntries));
    });
    // main.js's scroll-reveal only observes elements present at initial page
    // load, so rows built here after the async fetch never get the
    // `visible` class from it and would otherwise stay invisible forever.
    // Use the shared observer when present, else just show the rows.
    list.querySelectorAll('.reveal').forEach(function (el) {
      if (window.revealObserver) {
        window.revealObserver.observe(el);
      } else {
        el.classList.add('visible');
      }
    });
  }

  // Categories are CMS-managed (Transparency Categories, admin panel) —
  // only active ones are ever returned here, already sorted by display
  // order, so the public page always mirrors what's actually turned on.
  Promise.all([
    fetch('/api/transparency-categories').then(function (r) { return r.json(); }),
    fetch('/api/transparency-documents').then(function (r) { return r.json(); })
  ])
    .then(function (results) {
      render(results[0].categories || [], results[1].documents || []);
    })
    .catch(function () { render([], []); });
})();
