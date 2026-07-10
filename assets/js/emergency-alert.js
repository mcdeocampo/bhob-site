/* Emergency Alert System — Public (Phase 2) */
(function () {
  'use strict';

  var API_URL = '/api/emergency-alerts/active';
  var POLL_INTERVAL = 60000;

  // Track current displayed alert to detect changes across polls
  var _currentId = null;
  var _currentVersion = null;
  var _currentPriority = null;

  function ackKey(id, version) {
    return 'EmergencyAlert_' + id + '_Version_' + version;
  }

  function isAcknowledged(id, version) {
    try { return localStorage.getItem(ackKey(id, version)) === 'true'; } catch (e) { return false; }
  }

  function acknowledge(id, version) {
    try { localStorage.setItem(ackKey(id, version), 'true'); } catch (e) {}
  }

  function esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Escape HTML then convert inline Markdown (bold, italic) to tags
  function inlineFmt(text) {
    var s = String(text || '')
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    s = s.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*([^*\n]+?)\*/g, '<em>$1</em>');
    return s;
  }

  // Strip all Markdown and collapse to a single safe line (for banner)
  function formatMsgInline(text) {
    return String(text || '')
      .replace(/\*{1,3}([^*\n]+?)\*{1,3}/g, '$1')
      .replace(/^#{1,6}\s+/gm, '')
      .replace(/^[*\-•+]\s+/gm, '')
      .replace(/^\d+[.)]\s+/gm, '')
      .replace(/\n+/g, ' ')
      .trim()
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function formatInstructions(raw) {
    if (!raw) return '';
    var lines = String(raw).replace(/\r\n/g,'\n').replace(/\r/g,'\n').split('\n');
    var items = [];
    for (var i = 0; i < lines.length; i++) {
      var t = lines[i].trim();
      if (!t) continue;
      t = t.replace(/^#{1,6}\s+/, '');
      t = t.replace(/^[*\-•+]\s+/, '');
      t = t.replace(/^\d+[.)]\s+/, '');
      if (t) items.push(t);
    }
    if (!items.length) return '';
    if (items.length === 1) {
      return '<p class="ea-msg-para">' + inlineFmt(items[0]) + '</p>';
    }
    var html = '<ul class="ea-instr-list">';
    for (var j = 0; j < items.length; j++) {
      html += '<li>' + inlineFmt(items[j]) + '</li>';
    }
    return html + '</ul>';
  }

  // Convert multi-line text with Markdown to structured HTML (for popup/detail)
  function formatMsgBlock(raw) {
    if (!raw) return '';
    var lines = String(raw).replace(/\r\n/g,'\n').replace(/\r/g,'\n').split('\n');
    var out = '', inUl = false, inOl = false, para = [];
    function flushPara() {
      if (!para.length) return;
      out += '<p class="ea-msg-para">' + para.join('<br>') + '</p>';
      para = [];
    }
    function closeLists() {
      if (inUl) { out += '</ul>'; inUl = false; }
      if (inOl) { out += '</ol>'; inOl = false; }
    }
    for (var i = 0; i < lines.length; i++) {
      var t = lines[i].trim();
      if (!t) { flushPara(); closeLists(); continue; }
      if (/^#{1,6}\s/.test(t)) {
        flushPara(); closeLists();
        out += '<p class="ea-msg-heading">' + inlineFmt(t.replace(/^#{1,6}\s+/, '')) + '</p>';
        continue;
      }
      if (/^[*\-•+]\s/.test(t)) {
        flushPara();
        if (!inUl) { closeLists(); out += '<ul class="ea-msg-list">'; inUl = true; }
        out += '<li>' + inlineFmt(t.replace(/^[*\-•+]\s+/, '')) + '</li>';
        continue;
      }
      if (/^\d+[.)]\s/.test(t)) {
        flushPara();
        if (!inOl) { closeLists(); out += '<ol class="ea-msg-list">'; inOl = true; }
        out += '<li>' + inlineFmt(t.replace(/^\d+[.)]\s+/, '')) + '</li>';
        continue;
      }
      closeLists();
      para.push(inlineFmt(lines[i]));
    }
    flushPara(); closeLists();
    return out;
  }

  function priorityClass(p) {
    if (p === 'Critical') return 'ea-banner-critical';
    if (p === 'Warning')  return 'ea-banner-warning';
    return 'ea-banner-advisory';
  }

  function alertSlug(title) {
    return (title || 'alert').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  }

  function warningIconSVG() {
    return '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" style="width:100%;height:100%">' +
      '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<path d="M12 9v4M12 17h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' +
      '</svg>';
  }

  // ── Banner ──────────────────────────────────────────────────────────────────
  function removeBanner() {
    var el = document.getElementById('ea-banner');
    if (el && el.parentNode) el.parentNode.removeChild(el);
    // Do NOT reset _currentId/_currentPriority here — user may have closed
    // the banner with X but the alert is still active; we still need to
    // detect the resolved transition on the next poll.
  }

  function showBanner(alert) {
    // Remove existing banner first so we always render fresh
    var existing = document.getElementById('ea-banner');
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);

    var slug = alertSlug(alert.title);
    var areaNote = alert.targetArea ? ' &mdash; ' + esc(alert.targetArea) : '';
    var detailUrl = '/emergency-alerts/' + esc(slug) + '?id=' + esc(alert.id);

    var banner = document.createElement('div');
    banner.id = 'ea-banner';
    banner.className = 'ea-banner is-visible ' + priorityClass(alert.priority);
    banner.setAttribute('role', 'alert');
    banner.setAttribute('aria-live', 'polite');
    banner.innerHTML =
      '<div class="ea-banner-inner container">' +
        '<span class="ea-banner-icon">' + warningIconSVG() + '</span>' +
        '<div class="ea-banner-body">' +
          '<div class="ea-banner-title">&#x1F6A8; ' + esc(alert.priority) + ' Alert &mdash; ' + esc(alert.title) + '</div>' +
          '<div class="ea-banner-msg">' + formatMsgInline(alert.message) + areaNote + '</div>' +
        '</div>' +
        '<div class="ea-banner-actions">' +
          '<a class="ea-banner-link" href="' + detailUrl + '">View Details</a>' +
          '<button class="ea-banner-close" aria-label="Close alert banner" id="ea-banner-close-btn">' +
            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>' +
          '</button>' +
        '</div>' +
      '</div>';

    var header = document.querySelector('.site-header');
    if (header && header.parentNode) {
      header.parentNode.insertBefore(banner, header.nextSibling);
    } else {
      document.body.insertBefore(banner, document.body.firstChild);
    }

    document.getElementById('ea-banner-close-btn').addEventListener('click', function () {
      removeBanner();
    });
  }

  // ── Popup ───────────────────────────────────────────────────────────────────
  function removePopup() {
    var el = document.getElementById('ea-popup-overlay');
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  function showPopup(alert) {
    removePopup();

    var slug = alertSlug(alert.title);
    var detailUrl = '/emergency-alerts/' + esc(slug) + '?id=' + esc(alert.id);

    var areaHtml = alert.targetArea
      ? '<div class="ea-popup-meta-row">&#x1F4CD; Affected area: <strong style="margin-left:3px">' + esc(alert.targetArea) + '</strong></div>'
      : '';
    var instrHtml = alert.instructions
      ? '<div class="ea-popup-section">' +
          '<div class="ea-popup-section-label">What To Do</div>' +
          '<div class="ea-popup-instr">' + formatInstructions(alert.instructions) + '</div>' +
        '</div>'
      : '';

    var overlay = document.createElement('div');
    overlay.id = 'ea-popup-overlay';
    overlay.className = 'ea-popup-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Critical Emergency Alert');
    overlay.innerHTML =
      '<div class="ea-popup-box">' +
        '<div class="ea-popup-head">' +
          '<div class="ea-popup-label">&#x1F6A8; Critical Emergency Alert</div>' +
          '<div class="ea-popup-title">' + esc(alert.title) + '</div>' +
          '<div class="ea-popup-badges">' +
            '<span class="ea-popup-badge ea-popup-badge-type">' + esc(alert.alertType) + '</span>' +
            '<span class="ea-popup-badge ea-popup-badge-priority">Critical Priority</span>' +
          '</div>' +
        '</div>' +
        '<div class="ea-popup-body">' +
          '<div class="ea-popup-section">' +
            '<div class="ea-popup-section-label">Emergency Message</div>' +
            '<div class="ea-popup-msg">' + formatMsgBlock(alert.message) + '</div>' +
          '</div>' +
          instrHtml +
          areaHtml +
        '</div>' +
        '<div class="ea-popup-foot">' +
          '<a class="ea-popup-btn-detail" href="' + detailUrl + '" id="ea-popup-detail-btn">View Details</a>' +
          '<button class="ea-popup-btn-close" id="ea-popup-close-btn">Close</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    function closePopup() {
      acknowledge(alert.id, alert.version);
      removePopup();
    }

    document.getElementById('ea-popup-close-btn').addEventListener('click', closePopup);
    // Acknowledge when navigating to detail page so popup doesn't reappear there
    document.getElementById('ea-popup-detail-btn').addEventListener('click', function () {
      acknowledge(alert.id, alert.version);
    });
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closePopup();
    });
  }

  // ── Skip popup on the detail page itself ─────────────────────────────────────
  var _isDetailPage = document.body.getAttribute('data-page') === 'emergency-alert-detail.html';

  // ── Resolved alert — sessionStorage persistence ───────────────────────────────
  var RESOLVED_KEY = 'EA_Resolved';
  var RESOLVED_TTL = 10 * 60 * 1000; // 10 minutes

  function storeResolved(priority, customMessage) {
    try {
      sessionStorage.setItem(RESOLVED_KEY, JSON.stringify({
        priority:      priority || 'Advisory',
        status:        'resolved',
        customMessage: customMessage || null,
        timestamp:     Date.now()
      }));
    } catch (e) {}
  }

  function clearResolved() {
    try { sessionStorage.removeItem(RESOLVED_KEY); } catch (e) {}
  }

  function getStoredResolved() {
    try {
      var raw = sessionStorage.getItem(RESOLVED_KEY);
      if (!raw) return null;
      var data = JSON.parse(raw);
      if (!data || !data.timestamp) { clearResolved(); return null; }
      if (Date.now() - data.timestamp > RESOLVED_TTL) { clearResolved(); return null; }
      return data;
    } catch (e) { return null; }
  }

  // ── Resolved toast ───────────────────────────────────────────────────────────
  function resolvedCopy(priority, customMessage) {
    var title = priority === 'Critical' ? 'Emergency Resolved'
              : priority === 'Warning'  ? 'Warning Lifted'
              : 'Advisory Lifted';
    var defaultMsg = priority === 'Critical'
      ? 'The previous emergency alert has been lifted. The situation has returned to normal. Residents may resume normal activities and are advised to continue monitoring official Barangay announcements for any further updates.'
      : priority === 'Warning'
      ? 'The previous warning has been lifted. The situation has returned to normal. Residents are advised to remain alert and continue monitoring official Barangay announcements for any further updates.'
      : 'The previous advisory has been lifted. The situation has returned to normal. Residents are encouraged to continue monitoring official Barangay announcements for any further updates.';
    return { title: title, msg: (customMessage && customMessage.trim()) ? customMessage.trim() : defaultMsg };
  }

  function removeResolvedToast() {
    var el = document.getElementById('ea-toast');
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  function showResolvedToast(priority, customMessage, fromStorage) {
    removeResolvedToast();

    if (!fromStorage) storeResolved(priority, customMessage);

    var copy = resolvedCopy(priority, customMessage);
    var toast = document.createElement('div');
    toast.id = 'ea-toast';
    toast.className = 'ea-toast';
    toast.setAttribute('role', 'status');
    toast.innerHTML =
      '<div class="ea-toast-head">' +
        '<span class="ea-toast-head-label">&#x1F7E2;&nbsp; All Clear</span>' +
        '<button class="ea-toast-close" id="ea-toast-close" aria-label="Dismiss">&#x2715;</button>' +
      '</div>' +
      '<div class="ea-toast-body">' +
        '<div class="ea-toast-icon">' +
          '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>' +
        '</div>' +
        '<div class="ea-toast-content">' +
          '<div class="ea-toast-title">' + copy.title + '</div>' +
          '<div class="ea-toast-msg">' + copy.msg + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="ea-toast-progress"><div class="ea-toast-bar"></div></div>';

    document.body.appendChild(toast);
    setTimeout(function () { toast.classList.add('is-visible'); }, 16);

    function fadeOut(el) {
      el.classList.remove('is-visible');
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 450);
    }

    // User explicitly dismisses → clear storage so it doesn't reappear
    document.getElementById('ea-toast-close').addEventListener('click', function () {
      clearTimeout(autoTimer);
      clearResolved();
      fadeOut(toast);
    });

    // Auto-dismiss keeps storage so it reappears on next page load within TTL
    var autoTimer = setTimeout(function () { fadeOut(toast); }, 15000);
  }

  function checkStoredResolved() {
    var stored = getStoredResolved();
    if (stored) showResolvedToast(stored.priority, stored.customMessage || null, true);
  }

  // ── Core logic ───────────────────────────────────────────────────────────────
  function applyAlert(data) {
    if (!data || !data.active) {
      if (_currentId !== null) {
        var _p = _currentPriority;
        fetch('/api/emergency-alerts/resolved-message?priority=' + encodeURIComponent(_p))
          .then(function(r) { return r.json(); })
          .then(function(cfg) { showResolvedToast(_p, cfg.message || null, false); })
          .catch(function() { showResolvedToast(_p, null, false); });
      }
      _currentId = null;
      _currentVersion = null;
      _currentPriority = null;
      removeBanner();
      removePopup();
      return;
    }

    // New active alert supersedes any resolved notification
    clearResolved();
    removeResolvedToast();

    var acked = isAcknowledged(data.id, data.version);
    var showingPopup = data.enablePopup && !acked;

    showBanner(data);
    _currentId = data.id;
    _currentVersion = data.version;
    _currentPriority = data.priority;

    if (showingPopup && !_isDetailPage) {
      showPopup(data);
    } else {
      removePopup();
    }
  }

  function checkAlerts() {
    fetch(API_URL)
      .then(function (r) { return r.json(); })
      .then(applyAlert)
      .catch(function () {});
  }

  function init() {
    // Show any stored resolved notification before the first API poll
    checkStoredResolved();
    checkAlerts();
    setInterval(checkAlerts, POLL_INTERVAL);
  }

  // Run on load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
