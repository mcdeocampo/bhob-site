// Barangay Hulo — Directory Module v2.0 (unified map + list)
// Self-contained: does not touch main.js or any other existing script.
// Fetches the 4 existing read-only endpoints (unchanged from Phase 1/2/F),
// normalizes each record into one common shape client-side, and renders a
// single synchronized map + compact list. No backend/API/DB changes.
(function () {
  'use strict';

  var HULO_CENTER = { lat: 14.7201, lng: 120.9284 };

  // ── Category grouping ────────────────────────────────────────────────────
  // All 4 modules' categories now live in the admin Category Management
  // screen and are fetched from /api/directory/categories at boot (see
  // SUBCAT_INDEX / loadCategoryGroups below). MASTER_MAP/ICON/COLOR below are
  // kept only as a last-resort fallback if that fetch ever fails.
  var TYPE_MODULE = { location: 'map', business: 'business', organization: 'organization', emergency: 'emergency' };
  var MASTER_MAP = {
    'Barangay Hall': 'Government',
    'Health Center': 'Healthcare',
    'Schools': 'Education',
    'Evacuation Centers': 'Facilities',
    'Public Facilities': 'Facilities',
    'Associations': 'Organizations',
    'Youth Organizations': 'Organizations',
    'Senior Citizens': 'Organizations',
    'Community Groups': 'Organizations',
    'Emergency Contacts': 'Emergency',
    'Hospitals': 'Emergency',
    'Police': 'Emergency',
    'Fire Services': 'Emergency',
    'Disaster Response Contacts': 'Emergency'
  };
  var MASTER_ORDER = ['Government', 'Healthcare', 'Education', 'Facilities', 'Business', 'Organizations', 'Emergency'];
  var MASTER_ICON = {
    Government: '🏛️', Healthcare: '🏥', Education: '🏫', Facilities: '🏗️',
    Business: '🏪', Organizations: '🤝', Emergency: '🚨'
  };
  var MASTER_COLOR = {
    Government: 'blue', Healthcare: 'teal', Education: 'gold', Facilities: 'blue',
    Business: 'gold', Organizations: 'blue', Emergency: 'red'
  };
  var MARKER_HEX = { blue: '#1565d8', teal: '#00a884', gold: '#f6c445', red: '#e5484d' };

  // module -> { subcategoryName -> { groupName, icon, color } }, populated
  // from /api/directory/categories at boot (the live, admin-managed taxonomy).
  var SUBCAT_INDEX = { business: {}, map: {}, organization: {}, emergency: {} };

  function resolveMasterCategory(type, categoryName) {
    var idx = SUBCAT_INDEX[TYPE_MODULE[type]];
    var hit = idx && idx[categoryName];
    if (hit) return hit.groupName;
    return MASTER_MAP[categoryName] || (type === 'business' ? 'Business' : 'Facilities');
  }

  // ── Small helpers ────────────────────────────────────────────────────────
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function normSrc(url) {
    return url.indexOf('http') === 0 ? url : '/' + url;
  }
  function mapsLink(lat, lng) {
    return 'https://www.google.com/maps?q=' + lat + ',' + lng;
  }
  function directionsLink(lat, lng) {
    return 'https://www.google.com/maps/dir/?api=1&destination=' + lat + ',' + lng;
  }
  function wazeLink(lat, lng) {
    return 'https://waze.com/ul?ll=' + lat + ',' + lng + '&navigate=yes';
  }
  // Standard phone-keypad conversion, so vanity numbers dial correctly:
  // "0917 PCG DOTC" -> 09177243682. Case-insensitive; spaces, hyphens and
  // punctuation are dropped. A leading "+" is kept for international form.
  function dialDigits(value) {
    var KEYPAD = {
      A:'2', B:'2', C:'2', D:'3', E:'3', F:'3', G:'4', H:'4', I:'4',
      J:'5', K:'5', L:'5', M:'6', N:'6', O:'6', P:'7', Q:'7', R:'7',
      S:'7', T:'8', U:'8', V:'8', W:'9', X:'9', Y:'9', Z:'9'
    };
    var str = String(value == null ? '' : value), out = '';
    for (var i = 0; i < str.length; i++) {
      var ch = str.charAt(i);
      if (ch >= '0' && ch <= '9') { out += ch; continue; }
      if (ch === '+' && out === '') { out += ch; continue; }
      var mapped = KEYPAD[ch.toUpperCase()];
      if (mapped) out += mapped;
    }
    return out;
  }
  function telHref(v) {
    // Single-action buttons (Call) use the first number listed.
    return 'tel:' + dialDigits(String(v || '').split('/')[0]);
  }
  // A record may hold several numbers separated by "/", e.g. "911 / 117".
  // Render each as its own tel: link, separator as plain text, so the second
  // number is reachable instead of being silently dropped.
  function telLinks(v) {
    var parts = String(v == null ? '' : v).split('/');
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      var label = parts[i].trim();
      if (!label) continue;
      // Display keeps its original text; only the tel: target is converted.
      var dial = dialDigits(label);
      out.push(/[0-9]/.test(label) ? '<a href="tel:' + dial + '">' + esc(label) + '</a>' : esc(label));
    }
    return out.join('<span class="dir2-tel-sep" aria-hidden="true"> / </span>');
  }
  function debounce(fn, wait) {
    var t;
    return function () {
      var args = arguments, ctx = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, wait);
    };
  }
  function fetchJSON(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('Request failed: ' + r.status);
      return r.json();
    });
  }
  function haversineMeters(a, b) {
    var R = 6371000, toRad = Math.PI / 180;
    var dLat = (b.lat - a.lat) * toRad, dLng = (b.lng - a.lng) * toRad;
    var la1 = a.lat * toRad, la2 = b.lat * toRad;
    var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  // Current time-of-day in Asia/Manila, in minutes since midnight (matches the
  // Asia/Manila convention already used by the site's date/time widget).
  function nowInManilaMinutes() {
    var fmt = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Manila', hour12: false, hour: '2-digit', minute: '2-digit' });
    var h = 0, m = 0;
    fmt.formatToParts(new Date()).forEach(function (p) {
      if (p.type === 'hour') h = parseInt(p.value, 10) % 24;
      if (p.type === 'minute') m = parseInt(p.value, 10);
    });
    return h * 60 + m;
  }

  // Computes a live Open/Closed/Opening Soon/Closing Soon/24-Hours badge from
  // structured hours. Returns null when structured hours aren't set (callers
  // fall back to showing the free-text `hours` field instead).
  function computeHoursStatus(it) {
    if (it.hoursIs24h) return { label: '24 Hours', cls: 'open' };
    if (!it.hoursOpen || !it.hoursClose) return null;
    function toMins(t) { var p = t.split(':'); return (+p[0]) * 60 + (+p[1]); }
    var nowM = nowInManilaMinutes();
    var openM = toMins(it.hoursOpen), closeM = toMins(it.hoursClose);
    var isOpen = openM <= closeM ? (nowM >= openM && nowM < closeM) : (nowM >= openM || nowM < closeM);
    if (isOpen) {
      var toClose = (closeM - nowM + 1440) % 1440;
      return toClose <= 30 ? { label: 'Closing Soon', cls: 'closing' } : { label: 'Open', cls: 'open' };
    }
    var toOpen = (openM - nowM + 1440) % 1440;
    return toOpen <= 30 ? { label: 'Opening Soon', cls: 'opening' } : { label: 'Closed', cls: 'closed' };
  }

  // Minimal transient toast (public site has no existing toast helper — admin's is not shared).
  function toast(msg) {
    var el = document.createElement('div');
    el.className = 'dir2-toast';
    el.textContent = msg;
    document.body.appendChild(el);
    requestAnimationFrame(function () { el.classList.add('show'); });
    setTimeout(function () {
      el.classList.remove('show');
      setTimeout(function () { el.remove(); }, 300);
    }, 2200);
  }

  // ── Normalize the 4 distinct API shapes into one common item shape ──────
  function normalize(type, raw) {
    var base = {
      id: raw.id, type: type, name: raw.name || '', category: raw.category || '',
      masterCategory: resolveMasterCategory(type, raw.category),
      description: raw.description || '', imageUrl: raw.imageUrl || '',
      lat: raw.lat, lng: raw.lng,
      website: raw.website || '', email: raw.email || '', facebook: raw.facebook || raw.social || '',
      featured: !!raw.featured, verified: !!raw.verified,
      keywords: raw.keywords || '', gallery: raw.gallery || [],
      hoursOpen: raw.hoursOpen || '', hoursClose: raw.hoursClose || '', hoursIs24h: !!raw.hoursIs24h,
      createdAt: raw.createdAt || '', updatedAt: raw.updatedAt || '',
      raw: raw
    };
    if (type === 'location') {
      base.address = raw.address || ''; base.phone = raw.contact || ''; base.altPhone = '';
      base.hours = raw.hours || '';
    } else if (type === 'business') {
      base.address = raw.address || ''; base.phone = raw.contact || ''; base.altPhone = '';
      base.hours = raw.hours || '';
    } else if (type === 'organization') {
      base.address = raw.location || ''; base.phone = raw.contactDetails || ''; base.altPhone = '';
      base.hours = '';
    } else if (type === 'emergency') {
      base.address = raw.address || ''; base.phone = raw.number || ''; base.altPhone = raw.altNumber || '';
      base.hours = '';
    }
    return base;
  }

  // Fetches the admin-managed category taxonomy for all 4 modules and wires
  // it into the existing MASTER_ICON/MASTER_COLOR/MASTER_ORDER lookups, so
  // every module's real categories render exactly the same way.
  function loadCategoryGroups() {
    return fetchJSON('/api/directory/categories').then(function (d) {
      var modules = d.modules || {};
      var newNames = [];
      Object.keys(modules).forEach(function (module) {
        if (!SUBCAT_INDEX[module]) SUBCAT_INDEX[module] = {};
        (modules[module] || []).forEach(function (g) {
          newNames.push(g.name);
          MASTER_ICON[g.name] = g.icon || MASTER_ICON[g.name] || '🏪';
          MASTER_COLOR[g.name] = g.color || MASTER_COLOR[g.name] || 'gold';
          (g.subcategories || []).forEach(function (s) {
            SUBCAT_INDEX[module][s.name] = { groupName: g.name, icon: g.icon, color: g.color };
          });
        });
      });
      // Replace the old static Government/Healthcare/Education/Facilities/
      // Business/Organizations/Emergency placeholder buckets with the real,
      // admin-managed groups fetched above, in the order they were seeded
      // (business groups first, then map, then organization, then emergency —
      // matching Object.keys() insertion order from the API response).
      if (newNames.length) {
        MASTER_ORDER = newNames.slice();
        // A few groups intentionally share a name across modules (e.g.
        // "Government" exists in both Business and Map) — dedupe so each
        // renders as one combined chip rather than two identical ones.
        var seen = {};
        MASTER_ORDER = MASTER_ORDER.filter(function (name) {
          if (seen[name]) return false;
          seen[name] = true;
          return true;
        });
      }
    }).catch(function () {});
  }

  function loadAll() {
    function safe(url, key, type) {
      return fetchJSON(url).then(function (d) {
        return (d[key] || []).map(function (x) { return normalize(type, x); });
      }).catch(function () { return []; });
    }
    return Promise.all([
      safe('/api/directory/map', 'locations', 'location'),
      safe('/api/directory/businesses', 'businesses', 'business'),
      safe('/api/directory/organizations', 'organizations', 'organization'),
      safe('/api/directory/emergency', 'contacts', 'emergency')
    ]).then(function (results) {
      return results[0].concat(results[1], results[2], results[3]);
    });
  }

  // ── State ────────────────────────────────────────────────────────────────
  var ALL_ITEMS = [];
  var activeMaster = 'All';
  var activeSubcategory = null;
  var searchQuery = '';
  var sortMode = 'alpha';
  var activeId = null;
  var userLoc = null;
  var nearMeRadius = null;
  var map = null, markers = {}, clusterGroup = null;
  var lastFocused = null;

  var listEl, chipsEl, subchipsEl, countEl, searchEl, searchClearEl, sortEl, mapEl, nearMeBtn, radiusRowEl;

  var LIST_BATCH_SIZE = 30;
  var listRenderState = { items: [], rendered: 0 };
  var listObserver = null;

  // ── Sorting ──────────────────────────────────────────────────────────────
  function sortItems(items, mode) {
    var arr = items.slice();
    if (mode === 'newest') {
      arr.sort(function (a, b) { return new Date(b.createdAt || 0) - new Date(a.createdAt || 0); });
    } else if (mode === 'updated') {
      arr.sort(function (a, b) { return new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0); });
    } else if (mode === 'nearest' && userLoc) {
      arr.sort(function (a, b) {
        var da = (a.lat != null) ? haversineMeters(userLoc, a) : Infinity;
        var db = (b.lat != null) ? haversineMeters(userLoc, b) : Infinity;
        return da - db;
      });
    } else {
      arr.sort(function (a, b) { return a.name.localeCompare(b.name); });
    }
    return arr;
  }

  function requestGeolocation(cb) {
    if (!navigator.geolocation) { cb(false); return; }
    navigator.geolocation.getCurrentPosition(function (pos) {
      userLoc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      cb(true);
    }, function () { cb(false); }, { timeout: 8000 });
  }

  // ── Filtering / rendering pipeline ──────────────────────────────────────
  function applyFilters() {
    var q = searchQuery.trim().toLowerCase();
    var searchFiltered = ALL_ITEMS.filter(function (it) {
      if (!q) return true;
      var hay = [it.name, it.category, it.masterCategory, it.address, it.description, it.raw.services, it.keywords].filter(Boolean).join(' ').toLowerCase();
      return hay.indexOf(q) !== -1;
    });
    if (nearMeRadius != null && userLoc) {
      searchFiltered = searchFiltered.filter(function (it) {
        return it.lat != null && it.lng != null && haversineMeters(userLoc, it) <= nearMeRadius;
      });
    }
    renderChips(searchFiltered);
    var masterFiltered = activeMaster === 'All' ? searchFiltered : searchFiltered.filter(function (it) { return it.masterCategory === activeMaster; });
    renderSubchips(masterFiltered);
    var finalItems = activeSubcategory ? masterFiltered.filter(function (it) { return it.category === activeSubcategory; }) : masterFiltered;
    finalItems = sortItems(finalItems, sortMode);
    // Featured items float to the top; Array#sort is stable, so the chosen
    // sort order is preserved within the featured and non-featured groups.
    finalItems = finalItems.slice().sort(function (a, b) { return (b.featured ? 1 : 0) - (a.featured ? 1 : 0); });
    renderList(finalItems);
    renderMarkers(finalItems);
    renderCount(finalItems.length);
    if (q || activeMaster !== 'All' || activeSubcategory || nearMeRadius != null) fitToMarkers(finalItems);
  }

  function renderCount(n) {
    if (!countEl) return;
    countEl.textContent = n + (n === 1 ? ' Result Found' : ' Results Found');
  }

  function renderChips(items) {
    if (!chipsEl) return;
    var counts = {};
    items.forEach(function (it) { counts[it.masterCategory] = (counts[it.masterCategory] || 0) + 1; });
    var groups = MASTER_ORDER.filter(function (g) { return counts[g]; });
    var html = '<button type="button" class="dir2-chip dir2-chip--all' + (activeMaster === 'All' ? ' active' : '') + '" data-cat="All">All (' + items.length + ')</button>';
    html += groups.map(function (g) {
      var color = MASTER_COLOR[g] || 'blue';
      return '<button type="button" class="dir2-chip dir2-chip--' + color + (activeMaster === g ? ' active' : '') + '" data-cat="' + esc(g) + '">' +
        (MASTER_ICON[g] ? MASTER_ICON[g] + ' ' : '') + esc(g) + ' (' + counts[g] + ')</button>';
    }).join('');
    chipsEl.innerHTML = html;
  }

  // Second-level chip row: subcategories within the currently active parent
  // category, so users can filter by parent OR drill into a specific
  // subcategory (mirrors the Near Me radius-chip pattern below).
  function renderSubchips(items) {
    if (!subchipsEl) return;
    if (activeMaster === 'All') { subchipsEl.innerHTML = ''; subchipsEl.classList.remove('open'); return; }
    var counts = {};
    items.forEach(function (it) { if (it.category) counts[it.category] = (counts[it.category] || 0) + 1; });
    var subNames = Object.keys(counts).sort();
    if (!subNames.length) { subchipsEl.innerHTML = ''; subchipsEl.classList.remove('open'); return; }
    var color = MASTER_COLOR[activeMaster] || 'blue';
    var html = '<button type="button" class="dir2-chip dir2-chip--all' + (!activeSubcategory ? ' active' : '') + '" data-sub="">All ' + esc(activeMaster) + '</button>';
    html += subNames.map(function (name) {
      return '<button type="button" class="dir2-chip dir2-chip--' + color + (activeSubcategory === name ? ' active' : '') + '" data-sub="' + esc(name) + '">' + esc(name) + ' (' + counts[name] + ')</button>';
    }).join('');
    subchipsEl.innerHTML = html;
    subchipsEl.classList.add('open');
  }

  // ── Near Me (radius filter) ──────────────────────────────────────────────
  var NEAR_ME_RADII = [500, 1000, 2000, 5000];
  var NEAR_ME_LABELS = { 500: '500m', 1000: '1km', 2000: '2km', 5000: '5km' };

  function renderRadiusChips() {
    if (!radiusRowEl) return;
    var html = '<button type="button" class="dir2-chip dir2-chip--all' + (nearMeRadius == null ? ' active' : '') + '" data-radius="">All Distances</button>';
    html += NEAR_ME_RADII.map(function (r) {
      return '<button type="button" class="dir2-chip dir2-chip--teal' + (nearMeRadius === r ? ' active' : '') + '" data-radius="' + r + '">' + NEAR_ME_LABELS[r] + '</button>';
    }).join('');
    radiusRowEl.innerHTML = html;
    radiusRowEl.classList.add('open');
  }

  function logoOrIconHtml(it, cssClass) {
    var icon = MASTER_ICON[it.masterCategory] || '📍';
    if (!it.imageUrl) return '<span class="' + cssClass + '-icon">' + icon + '</span>';
    return '<img class="' + cssClass + '-img" loading="lazy" src="' + esc(normSrc(it.imageUrl)) + '" alt="" ' +
      'onerror="this.outerHTML=' + esc(JSON.stringify('<span class="' + cssClass + '-icon">' + icon + '</span>')) + '">';
  }

  // Modal cover: when a photo exists, use it as a blurred backdrop with the
  // crisp logo centered in a white badge on top — avoids a flat dead-space
  // box, since every business image is a small logo-shaped PNG, not a photo
  // meant to fill the frame. Falls back to the plain icon+gradient cover
  // (same as logoOrIconHtml) if there's no image or it fails to load.
  function coverHtml(it, color) {
    var icon = MASTER_ICON[it.masterCategory] || '📍';
    var fallback = '<div class="dir2-modal-cover dir2-modal-cover--' + color + '"><span class="dir2-modal-cover-icon">' + icon + '</span></div>';
    if (!it.imageUrl) return fallback;
    var src = esc(normSrc(it.imageUrl));
    return '<div class="dir2-modal-cover dir2-modal-cover--photo" style="background-image:url(' + src + ')">' +
      '<img class="dir2-modal-cover-img" loading="lazy" src="' + src + '" alt="" ' +
      'onerror="this.closest(\'.dir2-modal-cover\').outerHTML=' + esc(JSON.stringify(fallback)) + '">' +
      '</div>';
  }

  // Rendered in batches with an IntersectionObserver sentinel so a large
  // directory doesn't dump hundreds of DOM nodes into the list at once.
  function renderList(items) {
    if (!listEl) return;
    if (listObserver) { listObserver.disconnect(); listObserver = null; }
    if (!items.length) {
      listEl.innerHTML = '<p class="dir2-empty">No listings match your search.</p>';
      return;
    }
    listRenderState = { items: items, rendered: 0 };
    listEl.innerHTML = '';
    renderNextListBatch();
  }

  function renderNextListBatch() {
    var items = listRenderState.items;
    var start = listRenderState.rendered;
    var end = Math.min(start + LIST_BATCH_SIZE, items.length);
    var wrap = document.createElement('div');
    wrap.innerHTML = items.slice(start, end).map(renderListItem).join('');
    while (wrap.firstChild) listEl.appendChild(wrap.firstChild);
    listRenderState.rendered = end;

    var oldSentinel = listEl.querySelector('.dir2-list-sentinel');
    if (oldSentinel) oldSentinel.remove();

    if (listRenderState.rendered >= items.length) return;

    var sentinel = document.createElement('div');
    sentinel.className = 'dir2-list-sentinel';
    listEl.appendChild(sentinel);
    if ('IntersectionObserver' in window) {
      listObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            listObserver.disconnect();
            renderNextListBatch();
          }
        });
      }, { root: listEl, rootMargin: '200px' });
      listObserver.observe(sentinel);
    } else {
      renderNextListBatch();
    }
  }

  function renderListItem(it) {
    var color = MASTER_COLOR[it.masterCategory] || 'blue';
    var badges = (it.featured ? '<span class="dir2-badge dir2-badge-featured">★ Featured</span>' : '') +
      (it.verified ? '<span class="dir2-badge dir2-badge-verified">✔ Verified</span>' : '');
    var status = computeHoursStatus(it);
    return '<article class="dir2-item' + (it.id === activeId ? ' active' : '') + (it.featured ? ' dir2-item-featured' : '') + '" data-id="' + esc(it.id) + '" tabindex="0" role="button" aria-label="View details for ' + esc(it.name) + '">' +
      '<div class="dir2-item-logo dir2-item-logo--' + (it.imageUrl ? 'neutral' : color) + '">' + logoOrIconHtml(it, 'dir2-item-logo') + '</div>' +
      '<div class="dir2-item-body">' +
      '<div class="dir2-item-top"><h3>' + esc(it.name) + '</h3>' + (badges ? '<span class="dir2-item-badges">' + badges + '</span>' : '') + '</div>' +
      '<div class="dir2-item-cat">' +
      (it.masterCategory && it.masterCategory !== it.category ? '<span class="dir2-parent-cat">' + esc(it.masterCategory) + '</span>' : '') +
      '<span class="dir2-chip dir2-chip--' + color + ' dir2-chip-static">' + esc(it.category) + '</span>' +
      '</div>' +
      (it.address ? '<p class="dir2-item-addr">📍 ' + esc(it.address) + '</p>' : '') +
      '<div class="dir2-item-meta">' +
      (it.phone ? '<span>📞 ' + esc(it.phone) + '</span>' : '') +
      (it.hours ? '<span>🕒 ' + esc(it.hours) + '</span>' : '') +
      (status ? '<span class="dir2-status dir2-status--' + status.cls + '">' + status.label + '</span>' : '') +
      '</div>' +
      '<div class="dir2-item-actions">' +
      '<button type="button" class="dir2-link" data-act="details" data-id="' + esc(it.id) + '">View Details</button>' +
      (it.lat != null && it.lng != null ? '<button type="button" class="dir2-link" data-act="locate" data-id="' + esc(it.id) + '">Locate on Map →</button>' : '') +
      '</div></div></article>';
  }

  // ── Map ──────────────────────────────────────────────────────────────────
  function initMap() {
    if (!mapEl || !window.L) return;
    map = L.map(mapEl, { scrollWheelZoom: false }).setView([HULO_CENTER.lat, HULO_CENTER.lng], 15);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    if (window.L.markerClusterGroup) {
      clusterGroup = L.markerClusterGroup({ maxClusterRadius: 50, disableClusteringAtZoom: 18, showCoverageOnHover: false });
      map.addLayer(clusterGroup);
    }
    // Small entrance animation each time a popup opens (CSS respects
    // prefers-reduced-motion on its own).
    map.on('popupopen', function (e) {
      var el = e.popup && e.popup.getElement && e.popup.getElement();
      if (!el) return;
      el.classList.remove('dir2-popup-anim');
      void el.offsetWidth;
      el.classList.add('dir2-popup-anim');
    });
  }

  function prefersReducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  // Smooth animated pan/zoom, falling back to an instant jump for visitors
  // who've asked for reduced motion.
  function flyOrJump(lat, lng, zoom) {
    if (!map) return;
    if (prefersReducedMotion()) map.setView([lat, lng], zoom);
    else map.flyTo([lat, lng], zoom, { duration: 0.6 });
  }

  function fitToMarkers(items) {
    if (!map) return;
    var pts = items.filter(function (it) { return it.lat != null && it.lng != null; }).map(function (it) { return [it.lat, it.lng]; });
    if (!pts.length) return;
    if (pts.length === 1) { flyOrJump(pts[0][0], pts[0][1], 17); return; }
    map.fitBounds(pts, { padding: [30, 30], maxZoom: 17, animate: !prefersReducedMotion(), duration: 0.6 });
  }

  function popupHtml(it) {
    var color = MASTER_COLOR[it.masterCategory] || 'blue';
    var thumb = it.imageUrl ? '<div class="dir2-popup-thumb-wrap" data-act="details" data-id="' + esc(it.id) + '" style="background-image:url(' + esc(normSrc(it.imageUrl)) + ')">' +
      '<img src="' + esc(normSrc(it.imageUrl)) + '" alt="" class="dir2-popup-thumb" loading="lazy" onerror="this.closest(\'.dir2-popup-thumb-wrap\').remove()">' +
      '</div>' : '';
    return '<div class="dir2-popup">' + thumb +
      '<strong>' + esc(it.name) + '</strong>' +
      '<span class="dir2-popup-cat dir2-popup-cat--' + color + '">' + esc(it.category) + '</span>' +
      (it.address ? '<span class="dir2-popup-line">📍 ' + esc(it.address) + '</span>' : '') +
      (it.phone ? '<span class="dir2-popup-line">📞 ' + esc(it.phone) + '</span>' : '') +
      '<div class="dir2-popup-actions">' +
      '<button type="button" class="dir2-popup-btn" data-act="details" data-id="' + esc(it.id) + '">View Details</button>' +
      (it.lat != null && it.lng != null ? '<a class="dir2-popup-btn" href="' + directionsLink(it.lat, it.lng) + '" target="_blank" rel="noopener noreferrer">Directions</a>' : '') +
      '</div></div>';
  }

  // Selected marker gets a bigger radius + thicker ring and stays that way
  // until a different listing is selected.
  var MARKER_DEFAULT_STYLE = { radius: 9, weight: 2, fillOpacity: 0.95 };
  var MARKER_ACTIVE_STYLE = { radius: 13, weight: 3, fillOpacity: 1 };

  function setMarkerActive(id, active) {
    var m = markers[id];
    if (!m) return;
    m.setStyle(active ? MARKER_ACTIVE_STYLE : MARKER_DEFAULT_STYLE);
    if (active && m.bringToFront) m.bringToFront();
  }

  function renderMarkers(items) {
    if (!map) return;
    var layerGroup = clusterGroup || map;
    var seen = {};
    items.forEach(function (it) {
      if (it.lat == null || it.lng == null) return;
      seen[it.id] = true;
      var color = MARKER_HEX[MASTER_COLOR[it.masterCategory] || 'blue'];
      var m = markers[it.id];
      if (!m) {
        var style = it.id === activeId ? MARKER_ACTIVE_STYLE : MARKER_DEFAULT_STYLE;
        m = L.circleMarker([it.lat, it.lng], { radius: style.radius, color: '#fff', weight: style.weight, fillColor: color, fillOpacity: style.fillOpacity });
        m.bindPopup(popupHtml(it));
        m.on('click', function () { selectItem(it.id, { fromMap: true }); });
        markers[it.id] = m;
      } else {
        m.setPopupContent(popupHtml(it));
      }
      if (!layerGroup.hasLayer(m)) layerGroup.addLayer(m);
    });
    Object.keys(markers).forEach(function (id) {
      if (!seen[id] && layerGroup.hasLayer(markers[id])) layerGroup.removeLayer(markers[id]);
    });
  }

  // ── Map ↔ list synchronization ──────────────────────────────────────────
  function highlightListItem(id) {
    if (!listEl) return;
    listEl.querySelectorAll('.dir2-item').forEach(function (el) {
      el.classList.toggle('active', el.getAttribute('data-id') === id);
    });
  }

  function selectItem(id, opts) {
    opts = opts || {};
    var prevId = activeId;
    activeId = id;
    var it = ALL_ITEMS.find(function (x) { return x.id === id; });
    if (!it) return;
    highlightListItem(id);
    if (prevId && prevId !== id) setMarkerActive(prevId, false);
    setMarkerActive(id, true);
    if (opts.fromMap) {
      var el = listEl && listEl.querySelector('.dir2-item[data-id="' + id + '"]');
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else if (it.lat != null && it.lng != null && map) {
      mapEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      var marker = markers[id];
      var layerGroup = clusterGroup || map;
      if (marker) {
        if (!layerGroup.hasLayer(marker)) layerGroup.addLayer(marker);
        if (clusterGroup && clusterGroup.hasLayer(marker)) {
          clusterGroup.zoomToShowLayer(marker, function () { marker.openPopup(); });
        } else {
          flyOrJump(it.lat, it.lng, 17);
          marker.openPopup();
        }
      }
    }
  }

  // ── Details modal ────────────────────────────────────────────────────────
  var modalOverlay, modalBody, modalClose;
  var lightboxOverlay, lightboxImg, lightboxClose;

  function metaRow(icon, html) { return '<li>' + icon + ' ' + html + '</li>'; }

  function detailsHtml(it) {
    var color = MASTER_COLOR[it.masterCategory] || 'blue';
    var cover = coverHtml(it, color);

    var status = computeHoursStatus(it);
    var hoursText = it.hours ? esc(it.hours) : '';
    if (status) hoursText = (hoursText ? hoursText + ' &middot; ' : '') + '<span class="dir2-status dir2-status--' + status.cls + '">' + status.label + '</span>';

    var rows = [];
    if (it.address) rows.push(metaRow('📍', esc(it.address)));
    if (it.phone) rows.push(metaRow('📞', telLinks(it.phone)));
    if (it.altPhone) rows.push(metaRow('📞', telLinks(it.altPhone) + ' (alternate)'));
    if (hoursText) rows.push(metaRow('🕒', hoursText));
    if (it.raw.contactPerson) rows.push(metaRow('👤', esc(it.raw.contactPerson)));
    if (it.raw.services) rows.push(metaRow('🛟', esc(it.raw.services)));
    if (it.email) rows.push(metaRow('✉️', '<a href="mailto:' + esc(it.email) + '">' + esc(it.email) + '</a>'));

    var officers = it.raw.officers || [];
    var badges = (it.featured ? '<span class="dir2-badge dir2-badge-featured">★ Featured</span>' : '') +
      (it.verified ? '<span class="dir2-badge dir2-badge-verified">✔ Verified</span>' : '');

    var gallery = it.gallery || [];
    var galleryHtml = gallery.length
      ? '<p class="dir2-subhead">Gallery</p><div class="dir2-gallery-strip">' + gallery.map(function (url) {
          var src = normSrc(url);
          return '<img src="' + esc(src) + '" alt="" loading="lazy" class="dir2-gallery-thumb" data-full="' + esc(src) + '" onerror="this.remove()">';
        }).join('') + '</div>'
      : '';

    var actions = [];
    if (it.lat != null && it.lng != null) {
      actions.push('<a class="dir2-btn" href="' + mapsLink(it.lat, it.lng) + '" target="_blank" rel="noopener noreferrer">Google Maps</a>');
      actions.push('<a class="dir2-btn" href="' + wazeLink(it.lat, it.lng) + '" target="_blank" rel="noopener noreferrer">Waze</a>');
    }
    if (it.phone) actions.push('<a class="dir2-btn" href="' + telHref(it.phone) + '">Call</a>');
    if (it.website) actions.push('<a class="dir2-btn" href="' + esc(it.website) + '" target="_blank" rel="noopener noreferrer">Website</a>');
    if (it.facebook) actions.push('<a class="dir2-btn" href="' + esc(it.facebook) + '" target="_blank" rel="noopener noreferrer">Facebook</a>');
    actions.push('<button type="button" class="dir2-btn" id="dir2-share-btn" data-id="' + esc(it.id) + '">Share</button>');

    return cover +
      '<div class="dir2-modal-content">' +
      '<div class="dir2-item-cat">' +
      (it.masterCategory && it.masterCategory !== it.category ? '<span class="dir2-parent-cat">' + esc(it.masterCategory) + '</span>' : '') +
      '<span class="dir2-chip dir2-chip--' + color + ' dir2-chip-static">' + esc(it.category) + '</span>' +
      '</div>' +
      (badges ? '<span class="dir2-item-badges">' + badges + '</span>' : '') +
      '<h2 id="dir2-modal-title">' + esc(it.name) + '</h2>' +
      (it.description ? '<p class="dir2-modal-desc">' + esc(it.description) + '</p>' : '') +
      (rows.length ? '<ul class="dir2-modal-meta">' + rows.join('') + '</ul>' : '') +
      (officers.length ? '<p class="dir2-subhead">Officers</p><ul class="dir2-modal-meta">' + officers.map(function (o) { return '<li>' + esc(o) + '</li>'; }).join('') + '</ul>' : '') +
      (it.raw.programs ? '<p class="dir2-subhead">Activities / Programs</p><p class="dir2-note">' + esc(it.raw.programs) + '</p>' : '') +
      galleryHtml +
      '<div class="dir2-modal-actions">' + actions.join('') + '</div>' +
      '</div>';
  }

  function trapFocus(e) {
    var focusable = modalOverlay.querySelectorAll('button, a[href]');
    if (!focusable.length) return;
    var first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  function onModalKeydown(e) {
    if (e.key === 'Escape') {
      if (lightboxOverlay && lightboxOverlay.classList.contains('open')) closeLightbox();
      else closeDetails();
    } else if (e.key === 'Tab') {
      trapFocus(e);
    }
  }

  function openLightbox(src) {
    if (!lightboxOverlay) return;
    lightboxImg.src = src;
    lightboxOverlay.classList.add('open');
  }

  function closeLightbox() {
    if (!lightboxOverlay) return;
    lightboxOverlay.classList.remove('open');
    lightboxImg.src = '';
  }

  function openDetails(id) {
    var it = ALL_ITEMS.find(function (x) { return x.id === id; });
    if (!it || !modalOverlay) return;
    modalBody.innerHTML = detailsHtml(it);
    modalOverlay.classList.add('open');
    document.body.classList.add('dir2-modal-lock');
    lastFocused = document.activeElement;
    modalClose.focus();
    document.addEventListener('keydown', onModalKeydown);
  }

  function closeDetails() {
    if (!modalOverlay) return;
    modalOverlay.classList.remove('open');
    document.body.classList.remove('dir2-modal-lock');
    document.removeEventListener('keydown', onModalKeydown);
    if (lastFocused && lastFocused.focus) lastFocused.focus();
  }

  function doShare(id) {
    var it = ALL_ITEMS.find(function (x) { return x.id === id; });
    if (!it) return;
    var shareUrl = location.origin + location.pathname;
    if (navigator.share) {
      navigator.share({ title: it.name, text: it.name + (it.category ? ' — ' + it.category : ''), url: shareUrl }).catch(function () {});
    } else if (navigator.clipboard) {
      navigator.clipboard.writeText(shareUrl).then(function () { toast('Link copied to clipboard'); }).catch(function () {});
    }
  }

  function toggleSearchClearBtn() {
    if (!searchClearEl || !searchEl) return;
    searchClearEl.hidden = !searchEl.value;
  }

  // ── Event wiring ─────────────────────────────────────────────────────────
  function wireEvents() {
    if (searchEl) {
      searchEl.addEventListener('input', function () {
        toggleSearchClearBtn();
      });
      searchEl.addEventListener('input', debounce(function () {
        searchQuery = searchEl.value;
        applyFilters();
      }, 200));
    }
    if (searchClearEl) {
      searchClearEl.addEventListener('click', function () {
        searchEl.value = '';
        searchQuery = '';
        activeMaster = 'All';
        activeSubcategory = null;
        toggleSearchClearBtn();
        applyFilters();
        searchEl.focus();
      });
    }

    if (sortEl) {
      sortEl.addEventListener('change', function () {
        var mode = sortEl.value;
        if (mode === 'nearest' && !userLoc) {
          requestGeolocation(function (ok) {
            if (!ok) { sortEl.value = 'alpha'; mode = 'alpha'; toast('Location unavailable — showing alphabetical order'); }
            sortMode = mode;
            applyFilters();
          });
          return;
        }
        sortMode = mode;
        applyFilters();
      });
    }

    if (chipsEl) {
      chipsEl.addEventListener('click', function (e) {
        var btn = e.target.closest('.dir2-chip');
        if (!btn) return;
        activeMaster = btn.getAttribute('data-cat');
        activeSubcategory = null;
        applyFilters();
      });
    }

    if (subchipsEl) {
      subchipsEl.addEventListener('click', function (e) {
        var btn = e.target.closest('.dir2-chip');
        if (!btn) return;
        activeSubcategory = btn.getAttribute('data-sub') || null;
        applyFilters();
      });
    }

    if (nearMeBtn) {
      nearMeBtn.addEventListener('click', function () {
        if (userLoc) { renderRadiusChips(); return; }
        requestGeolocation(function (ok) {
          if (!ok) { toast('Location unavailable — enable location access to use Near Me'); return; }
          renderRadiusChips();
        });
      });
    }
    if (radiusRowEl) {
      radiusRowEl.addEventListener('click', function (e) {
        var btn = e.target.closest('.dir2-chip');
        if (!btn) return;
        var r = btn.getAttribute('data-radius');
        nearMeRadius = r ? Number(r) : null;
        renderRadiusChips();
        applyFilters();
      });
    }

    if (listEl) {
      listEl.addEventListener('click', function (e) {
        var detailsBtn = e.target.closest('[data-act="details"]');
        if (detailsBtn) { openDetails(detailsBtn.getAttribute('data-id')); return; }
        var locateBtn = e.target.closest('[data-act="locate"]');
        var card = e.target.closest('.dir2-item');
        var target = locateBtn || card;
        if (target) selectItem(target.getAttribute('data-id'), { fromMap: false });
      });
      listEl.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        var card = e.target.closest('.dir2-item');
        if (card) { e.preventDefault(); selectItem(card.getAttribute('data-id'), { fromMap: false }); }
      });
    }

    // Leaflet popups are (re)created dynamically — delegate at the document level.
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.dir2-popup-btn[data-act="details"], .dir2-popup-thumb-wrap[data-act="details"]');
      if (btn) openDetails(btn.getAttribute('data-id'));
    });

    if (modalClose) modalClose.addEventListener('click', closeDetails);
    if (modalOverlay) {
      modalOverlay.addEventListener('click', function (e) {
        if (e.target === modalOverlay) closeDetails();
      });
    }
    if (modalBody) {
      modalBody.addEventListener('click', function (e) {
        var btn = e.target.closest('#dir2-share-btn');
        if (btn) { doShare(btn.getAttribute('data-id')); return; }
        var thumb = e.target.closest('.dir2-gallery-thumb');
        if (thumb) openLightbox(thumb.getAttribute('data-full'));
      });
    }

    if (lightboxClose) lightboxClose.addEventListener('click', closeLightbox);
    if (lightboxOverlay) {
      lightboxOverlay.addEventListener('click', function (e) {
        if (e.target === lightboxOverlay) closeLightbox();
      });
    }
  }

  function boot() {
    listEl = document.getElementById('dir2-list');
    chipsEl = document.getElementById('dir2-chips');
    subchipsEl = document.getElementById('dir2-subchips');
    countEl = document.getElementById('dir2-count');
    searchEl = document.getElementById('dir2-search');
    searchClearEl = document.getElementById('dir2-search-clear');
    sortEl = document.getElementById('dir2-sort');
    mapEl = document.getElementById('dir2-map');
    nearMeBtn = document.getElementById('dir2-nearme-btn');
    radiusRowEl = document.getElementById('dir2-radius-row');
    modalOverlay = document.getElementById('dir2-modal-overlay');
    modalBody = document.getElementById('dir2-modal-body');
    modalClose = document.getElementById('dir2-modal-close');
    lightboxOverlay = document.getElementById('dir2-lightbox-overlay');
    lightboxImg = document.getElementById('dir2-lightbox-img');
    lightboxClose = document.getElementById('dir2-lightbox-close');

    if (!listEl) return; // not on the directory page

    if (!navigator.geolocation && nearMeBtn) nearMeBtn.style.display = 'none';

    initMap();
    wireEvents();

    loadCategoryGroups().then(function () {
      return loadAll();
    }).then(function (items) {
      ALL_ITEMS = items;
      applyFilters();
    }).catch(function () {
      if (countEl) countEl.textContent = 'Unable to load the directory right now. Please try again later.';
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
