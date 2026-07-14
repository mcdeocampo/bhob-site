// Public Services page — fetches CMS-managed services and renders the
// existing accordion markup. Uses its own click handler (event delegation)
// instead of main.js's static per-element accordion binding, since these
// cards do not exist yet when main.js runs at DOMContentLoaded.
(function () {
  var ICONS = {
    clearance:  { bg:'linear-gradient(135deg,#dbeafe,#bfdbfe)', fill:'#1d4ed8', path:'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zm-1 7V3.5L18.5 9H13zM7 17v-1.5h10V17H7zm0-3v-1.5h10V14H7z' },
    residency:  { bg:'linear-gradient(135deg,#ccfbf1,#99f6e4)', fill:'#0d9488', path:'M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z' },
    indigency:  { bg:'linear-gradient(135deg,#ffe4e6,#fecdd3)', fill:'#e11d48', path:'M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z' },
    business:   { bg:'linear-gradient(135deg,#fef3c7,#fde68a)', fill:'#d97706', path:'M20 6h-2.18c.07-.44.18-.88.18-1.35C18 3.18 16.82 2 15.35 2H8.65C7.18 2 6 3.18 6 4.65c0 .47.11.91.18 1.35H4c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zM8.65 4h6.7c.35 0 .65.3.65.65 0 .9-.28 1.85-.5 2.35H8.5c-.22-.5-.5-1.45-.5-2.35 0-.35.3-.65.65-.65zM20 19H4V8h16v11z' },
    jobseeker:  { bg:'linear-gradient(135deg,#d1fae5,#a7f3d0)', fill:'#059669', path:'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z' },
    blotter:    { bg:'linear-gradient(135deg,#e0e7ff,#c7d2fe)', fill:'#4338ca', path:'M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z' },
    health:     { bg:'linear-gradient(135deg,#dcfce7,#bbf7d0)', fill:'#16a34a', path:'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-2 10h-4v4h-2v-4H7v-2h4V7h2v4h4v2z' },
    senior:     { bg:'linear-gradient(135deg,#ede9fe,#ddd6fe)', fill:'#7c3aed', path:'M12 2a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm5 18H7v-2h4v-4.26A6.98 6.98 0 0 1 5 8h2a5 5 0 0 0 10 0h2a6.98 6.98 0 0 1-6 5.74V18h4v2z' },
    pwd:        { bg:'linear-gradient(135deg,#f5f3ff,#ede9fe)', fill:'#6d28d9', path:'M12 2a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm9 7h-6v13h-2v-6h-2v6H9V9H3V7h18v2z' },
    disaster:   { bg:'linear-gradient(135deg,#fee2e2,#fecaca)', fill:'#dc2626', path:'M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-1 6h2v2h-2V7zm0 4h2v6h-2v-6z' },
    youth:      { bg:'linear-gradient(135deg,#fefce8,#fef9c3)', fill:'#ca8a04', path:'M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z' }
  };

  function esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function iconMarkup(service) {
    if (service.iconType === 'upload' && service.icon) {
      var src = service.icon.indexOf('http') === 0 ? service.icon : '/' + service.icon;
      return '<span class="svc-icon" style="background:#eef2f7"><img src="' + esc(src) + '" alt="" width="22" height="22" style="object-fit:contain"></span>';
    }
    var ic = ICONS[service.icon];
    if (!ic) return '<span class="svc-icon" style="background:#eef2f7"></span>';
    return '<span class="svc-icon" style="background:' + ic.bg + '">' +
      '<svg viewBox="0 0 24 24" fill="' + ic.fill + '" width="22" height="22"><path d="' + ic.path + '"/></svg></span>';
  }

  function timeChip(text) {
    if (!text) return '';
    var isUrgent = /immediate/i.test(text);
    var cls = isUrgent ? 'svc-chip-emergency' : 'svc-chip-time';
    var icon = isUrgent ? '⚡' : '⏱';
    return '<span class="svc-chip ' + cls + '">' + icon + ' ' + esc(text) + '</span>';
  }

  function feeChip(text) {
    if (!text) return '';
    var isFree = /free/i.test(text);
    var cls = isFree ? 'svc-chip-free' : 'svc-chip-paid';
    var icon = isFree ? '✓' : '₱';
    return '<span class="svc-chip ' + cls + '">' + icon + ' ' + esc(text) + '</span>';
  }

  function metaRow(label, value) {
    if (!value) return '';
    return '<span><strong>' + esc(label) + ':</strong> ' + value + '</span>';
  }

  function renderService(service) {
    var desc = service.description || service.shortDescription || '';
    var banner = service.bannerImage
      ? '<img class="svc-banner" src="' + esc(service.bannerImage.indexOf('http') === 0 ? service.bannerImage : '/' + service.bannerImage) + '" alt="">'
      : '';

    var requirements = (service.requirements || []).join(', ');
    var steps = (service.steps || []).map(function (s, i) { return (i + 1) + '. ' + esc(s); }).join(' ');
    var contactParts = [];
    if (service.contactNumber) contactParts.push(esc(service.contactNumber));
    if (service.contactEmail) contactParts.push(esc(service.contactEmail));
    var contact = contactParts.join(' · ');
    var files = (service.files || []).map(function (f) {
      var href = f.filepath.indexOf('http') === 0 ? f.filepath : '/' + f.filepath;
      return '<a href="' + esc(href) + '" target="_blank" rel="noopener">' + esc(f.filename || 'Download') + '</a>';
    }).join(', ');

    return '<div class="accordion-item">' +
      '<button class="accordion-trigger" aria-expanded="false">' +
        iconMarkup(service) +
        '<span class="svc-info">' +
          '<span class="svc-name">' + esc(service.title) + '</span>' +
          '<span class="svc-chips">' + timeChip(service.processingTime) + feeChip(service.fee) + '</span>' +
        '</span>' +
        '<b>+</b>' +
      '</button>' +
      '<div class="accordion-content">' +
        banner +
        (desc ? '<p>' + esc(desc) + '</p>' : '') +
        '<div class="service-meta">' +
          metaRow('Requirements', requirements ? esc(requirements) : '') +
          metaRow('Processing Time', service.processingTime ? esc(service.processingTime) : '') +
          metaRow('Fees', service.fee ? esc(service.fee) : '') +
          metaRow('Office', service.office ? esc(service.office) : '') +
          metaRow('Steps', steps) +
          metaRow('Hours', service.processingHours ? esc(service.processingHours) : '') +
          metaRow('Contact', contact) +
          metaRow('Forms', files) +
          metaRow('Notes', service.notes ? esc(service.notes) : '') +
        '</div>' +
      '</div>' +
    '</div>';
  }

  function renderError() {
    var el = document.getElementById('svc-list');
    if (el) el.innerHTML = '<p style="text-align:center;padding:40px 0;color:#64748b">Unable to load public services right now. Please try again later.</p>';
  }

  function render(services) {
    var el = document.getElementById('svc-list');
    if (!el) return;
    if (!services.length) {
      el.innerHTML = '<p style="text-align:center;padding:40px 0;color:#64748b">No public services are available right now.</p>';
      return;
    }
    el.innerHTML = services.map(renderService).join('');
  }

  // Event delegation for the accordion open/close — mirrors main.js's own
  // per-element accordion binding (main.js runs before this content exists).
  function bindAccordion() {
    var el = document.getElementById('svc-list');
    if (!el) return;
    el.addEventListener('click', function (e) {
      var trigger = e.target.closest('.accordion-trigger');
      if (!trigger || !el.contains(trigger)) return;
      var content = trigger.nextElementSibling;
      var icon = trigger.querySelector('b');
      var item = trigger.closest('.accordion-item');
      var isOpen = content.classList.toggle('open');
      trigger.classList.toggle('open', isOpen);
      if (item) item.classList.toggle('open', isOpen);
      trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      if (icon) icon.textContent = isOpen ? '−' : '+';
    });
  }

  function init() {
    bindAccordion();
    fetch('/api/public-services')
      .then(function (r) { if (!r.ok) throw new Error('bad status'); return r.json(); })
      .then(function (d) { render(d.services || []); })
      .catch(renderError);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
