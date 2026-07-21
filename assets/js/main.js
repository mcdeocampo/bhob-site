// Barangay Hulo Website - lightweight interactions only
(function () {
  const body = document.body;
  const header = document.querySelector('.site-header');
  const menuToggle = document.querySelector('.menu-toggle');
  const navMenu = document.querySelector('.nav-menu');

  // Single, safe mobile menu controller. Avoid duplicate toggle handlers.
  if (menuToggle && navMenu) {
    const closeMenu = () => {
      navMenu.classList.remove('open', 'active');
      menuToggle.classList.remove('open');
      menuToggle.setAttribute('aria-expanded', 'false');
      body.classList.remove('nav-open');
    };

    const openMenu = () => {
      navMenu.classList.add('open');
      menuToggle.classList.add('open');
      menuToggle.setAttribute('aria-expanded', 'true');
      body.classList.add('nav-open');
    };

    menuToggle.addEventListener('click', (event) => {
      event.stopPropagation();
      if (navMenu.classList.contains('open')) closeMenu();
      else openMenu();
    });

    document.addEventListener('click', (event) => {
      const clickedInside = navMenu.contains(event.target) || menuToggle.contains(event.target);
      if (!clickedInside) closeMenu();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeMenu();
    });

    window.addEventListener('resize', () => {
      if (window.innerWidth > 900) closeMenu();
    }, { passive: true });

    navMenu.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', closeMenu);
    });
  }

  // Active navigation state
  const currentPage = body.getAttribute('data-page') || 'index.html';
  document.querySelectorAll('.nav-link').forEach(link => {
    if (link.getAttribute('data-page') === currentPage) link.classList.add('active');
  });

  // Auto-assign reveal animations to key sections/cards for a more modern feel
  const autoRevealSelectors = [
    '.section-heading',
    '.split-layout > *',
    '.card-grid > *',
    '.profile-grid > *',
    '.officials-grid > *',
    '.downloads-grid > *',
    '.document-list > *',
    '.contact-grid > *',
    '.footer-grid > *',
    '.official-mini',
    '.accordion .accordion-item',
    '.table-wrap'
  ];
  const revealVariants = ['reveal', 'reveal-left', 'reveal-right', 'reveal-zoom'];
  autoRevealSelectors.forEach(selector => {
    document.querySelectorAll(selector).forEach((el, index) => {
      const hasReveal = revealVariants.some(cls => el.classList.contains(cls));
      if (!hasReveal) el.classList.add(revealVariants[index % revealVariants.length]);
      if (![1, 2, 3].some(n => el.classList.contains(`delay-${n}`)) && index > 0 && index < 4) {
        el.classList.add(`delay-${Math.min(index, 3)}`);
      }
    });
  });

  // Scroll reveal animation
  const revealItems = document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-zoom');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.05, rootMargin: '0px 0px 40px 0px' });
    revealItems.forEach(item => observer.observe(item));
    // Fallback: ensure all reveal items become visible after 2s regardless
    setTimeout(() => {
      revealItems.forEach(item => item.classList.add('visible'));
    }, 2000);
  } else {
    revealItems.forEach(item => item.classList.add('visible'));
  }

  // Accordions for services / charter sections
  document.querySelectorAll('.accordion-trigger').forEach(trigger => {
    trigger.setAttribute('aria-expanded', 'false');
    trigger.addEventListener('click', () => {
      const content = trigger.nextElementSibling;
      const icon = trigger.querySelector('b');
      const item = trigger.closest('.accordion-item');
      const isOpen = content.classList.toggle('open');
      trigger.classList.toggle('open', isOpen);
      item?.classList.toggle('open', isOpen);
      trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      if (icon) icon.textContent = isOpen ? '−' : '+';
    });
  });

  // Header depth on scroll
  const updateHeaderState = () => {
    if (window.scrollY > 24) header?.classList.add('scrolled');
    else header?.classList.remove('scrolled');
  };
  updateHeaderState();
  window.addEventListener('scroll', updateHeaderState, { passive: true });

  // Back to top button
  const backToTop = document.querySelector('.back-to-top');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 500) backToTop?.classList.add('show');
    else backToTop?.classList.remove('show');
  }, { passive: true });
  backToTop?.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

  // Today's date display
  const dateEl = document.getElementById('hero-date');
  if (dateEl) {
    const dateFmt = new Intl.DateTimeFormat('en-PH', {
      timeZone: 'Asia/Manila',
      weekday: 'short', month: 'long', day: 'numeric', year: 'numeric'
    });
    dateEl.textContent = dateFmt.format(new Date());
  }

  // Philippine Standard Time live clock
  const pstEl = document.getElementById('hero-pst');
  if (pstEl) {
    const fmt = new Intl.DateTimeFormat('en-PH', {
      timeZone: 'Asia/Manila',
      hour: 'numeric', minute: '2-digit', second: '2-digit',
      hour12: true
    });
    const tickPST = () => { pstEl.textContent = fmt.format(new Date()) + ' PHT'; };
    tickPST();
    setInterval(tickPST, 1000);
  }

  // Live weather — try Flask proxy first, fall back to Open-Meteo direct
  var weatherEl      = document.getElementById('hero-weather');
  var weatherFact    = document.querySelector('.hero-weather-fact');
  var weatherDivider = document.querySelector('.hero-weather-divider');

  var WMO_LABELS_JS = {
    0:'Clear Sky', 1:'Mainly Clear', 2:'Partly Cloudy', 3:'Overcast',
    45:'Fog', 48:'Icy Fog', 51:'Light Drizzle', 53:'Drizzle', 55:'Heavy Drizzle',
    61:'Slight Rain', 63:'Moderate Rain', 65:'Heavy Rain',
    71:'Light Snow', 73:'Snow', 75:'Heavy Snow',
    80:'Rain Showers', 81:'Rain Showers', 82:'Heavy Showers',
    95:'Thunderstorm', 96:'Thunderstorm', 99:'Thunderstorm'
  };

  function wmoColor(code) {
    var c = parseInt(code, 10);
    if (c === 0 || c === 1)              return '#fbbf24'; // clear/mainly clear: yellow
    if (c === 2)                         return '#93c5fd'; // partly cloudy: sky blue
    if (c === 3 || c === 45 || c === 48) return '#94a3b8'; // overcast/fog: gray
    if (c >= 51 && c <= 82)              return '#60a5fa'; // rain/drizzle: blue
    if (c >= 95)                         return '#a855f7'; // thunder: purple
    return 'rgba(255,255,255,0.80)';
  }

  function showWeather(temp, label, color) {
    if (!weatherEl || !weatherFact) return;
    weatherEl.textContent = temp + '°C · ' + label;
    var wSvg = weatherFact.querySelector('svg');
    if (wSvg && color) { wSvg.style.color = color; wSvg.style.opacity = '1'; }
    weatherFact.style.display = '';
    if (weatherDivider) weatherDivider.style.display = '';
  }

  function showWeatherUnavailable() {
    if (!weatherEl || !weatherFact) return;
    weatherEl.textContent = 'Weather unavailable';
    weatherFact.style.display = '';
    if (weatherDivider) weatherDivider.style.display = '';
  }

  function wttrColor(code) {
    var c = parseInt(code, 10);
    if (c === 113)                    return '#fbbf24'; // sunny
    if (c === 116)                    return '#93c5fd'; // partly cloudy
    if (c === 119 || c === 122)       return '#94a3b8'; // cloudy/overcast
    if (c === 143 || c === 248 || c === 260) return '#cbd5e1'; // fog/mist
    if (c >= 176 && c <= 314)         return '#60a5fa'; // rain/drizzle
    if (c === 386 || c === 389 || c === 392 || c === 395) return '#a855f7'; // thunder
    if (c >= 323 && c <= 377)         return '#e2e8f0'; // snow
    return 'rgba(255,255,255,0.80)';
  }

  function fetchWeatherFallback() {
    // Source B — wttr.in: completely different infrastructure from Open-Meteo
    fetch('https://wttr.in/Obando,Bulacan?format=j1')
      .then(function(r) {
        if (!r.ok) throw new Error('wttr-failed');
        return r.json();
      })
      .then(function(d) {
        var cc    = d.current_condition[0];
        var temp  = parseInt(cc.temp_C, 10);
        var code  = cc.weatherCode;
        var label = cc.weatherDesc[0].value;
        var color = wttrColor(code);
        showWeather(temp, label, color);
      })
      .catch(function() {
        // Source C — historical-forecast subdomain (different CDN from blocked api.open-meteo.com)
        var today = new Date().toISOString().slice(0, 10);
        fetch('https://historical-forecast-api.open-meteo.com/v1/forecast' +
              '?latitude=14.7201&longitude=120.9284' +
              '&hourly=temperature_2m,weather_code' +
              '&start_date=' + today + '&end_date=' + today +
              '&timezone=Asia%2FManila')
          .then(function(r) {
            if (!r.ok) throw new Error('hist-failed');
            return r.json();
          })
          .then(function(d) {
            var hours = d.hourly.time;
            var nowH  = new Date().getHours();
            var idx   = 0;
            for (var i = 0; i < hours.length; i++) {
              if (parseInt(hours[i].slice(11, 13), 10) <= nowH) idx = i;
            }
            var temp  = Math.round(d.hourly.temperature_2m[idx]);
            var code  = d.hourly.weather_code[idx];
            showWeather(temp, WMO_LABELS_JS[code] || 'Fair', wmoColor(code));
          })
          .catch(function() {
            // Source D — met.no (Norway MET, CORS-enabled, no key)
            fetch('https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=14.7201&lon=120.9284',
                  { headers: { 'Accept': 'application/json' } })
              .then(function(r) { return r.json(); })
              .then(function(d) {
                var ts   = d.properties.timeseries[0].data;
                var temp = Math.round(ts.instant.details.air_temperature);
                var sym  = ((ts.next_1_hours || ts.next_6_hours || {}).summary || {}).symbol_code || '';
                var base = sym.replace(/_day|_night|_polartwilight/, '');
                var lbls = { clearsky:'Clear Sky', fair:'Fair', partlycloudy:'Partly Cloudy',
                             cloudy:'Cloudy', fog:'Fog', lightrain:'Light Rain',
                             rain:'Rain', heavyrain:'Heavy Rain', thunder:'Thunderstorm' };
                var clrs = { clearsky:'#fbbf24', fair:'#fde68a', partlycloudy:'#93c5fd',
                             cloudy:'#94a3b8', fog:'#cbd5e1', lightrain:'#60a5fa',
                             rain:'#3b82f6', heavyrain:'#1d4ed8', thunder:'#a855f7' };
                showWeather(temp, lbls[base] || 'Fair', clrs[base] || 'rgba(255,255,255,0.80)');
              })
              .catch(showWeatherUnavailable);
          });
      });
  }

  if (weatherEl && weatherFact) {
    fetchWeatherFallback();
  }

  // ── AQI via Open-Meteo Air Quality API ─────────────────────────────────────
  // Coordinates: Barangay Hulo, Obando, Bulacan
  const AQI_LAT = 14.7201, AQI_LON = 120.9284;
  const AQI_CACHE_KEY = 'bhob_aqi_cache';
  const AQI_TTL = 15 * 60 * 1000; // 15 minutes

  function aqiInfo(val) {
    // label = full label (detail section), shortLabel = status bar chip, advisory = short word in status bar
    if (val === null || val === undefined) return { label: 'Unavailable', shortLabel: 'Unavailable', color: '#94a3b8', bg: 'rgba(148,163,184,.15)', advisory: null };
    if (val <= 50)  return { label: 'Good',                          shortLabel: 'Good',          color: '#16a34a', bg: 'rgba(22,163,74,.12)',   advisory: 'Good' };
    if (val <= 100) return { label: 'Moderate',                      shortLabel: 'Moderate',      color: '#ca8a04', bg: 'rgba(202,138,4,.12)',   advisory: 'Caution' };
    if (val <= 150) return { label: 'Unhealthy for Sensitive Groups', shortLabel: 'Sensitive',    color: '#ea580c', bg: 'rgba(234,88,12,.12)',   advisory: 'Caution' };
    if (val <= 200) return { label: 'Unhealthy',                     shortLabel: 'Unhealthy',     color: '#dc2626', bg: 'rgba(220,38,38,.12)',   advisory: 'Avoid Outdoor' };
    if (val <= 300) return { label: 'Very Unhealthy',                shortLabel: 'Very Unhealthy', color: '#9333ea', bg: 'rgba(147,51,234,.12)', advisory: 'Stay Indoors' };
    return                 { label: 'Hazardous',                     shortLabel: 'Hazardous',     color: '#7f1d1d', bg: 'rgba(127,29,29,.15)',   advisory: 'Health Warning' };
  }

  function aqiHealthMsg(val) {
    if (val === null || val === undefined) return 'Air quality information is temporarily unavailable. Please check again later.';
    if (val <= 50)  return 'Air quality is satisfactory and poses little or no risk. Great day for outdoor activities.';
    if (val <= 100) return 'Air quality is acceptable. Unusually sensitive individuals should consider limiting prolonged outdoor exertion.';
    if (val <= 150) return 'Members of sensitive groups may experience health effects. The general public is less likely to be affected.';
    if (val <= 200) return 'Everyone may begin to experience health effects. Sensitive groups should avoid prolonged outdoor exertion.';
    if (val <= 300) return 'Health alert: everyone may experience serious health effects. Avoid prolonged outdoor activities.';
    return 'Health warning of emergency conditions. Everyone is more likely to be affected. Stay indoors.';
  }

  function renderAQI(data) {
    const heroAqiEl    = document.getElementById('hero-aqi');
    const heroAqiFact  = document.getElementById('hero-aqi-fact');
    const heroAqiDiv   = document.querySelector('.hero-aqi-divider');
    const aqiNum       = document.getElementById('aqi-num');
    const aqiRing      = document.getElementById('aqi-ring');
    const aqiBadge     = document.getElementById('aqi-status-badge');
    const aqiMsg       = document.getElementById('aqi-health-msg');
    const aqiUpdated   = document.getElementById('aqi-updated');
    const aqiPm25      = document.getElementById('aqi-pm25');
    const aqiPm10      = document.getElementById('aqi-pm10');
    const aqiO3        = document.getElementById('aqi-o3');
    const aqiCo        = document.getElementById('aqi-co');
    const aqiNo2       = document.getElementById('aqi-no2');
    const aqiSo2       = document.getElementById('aqi-so2');

    const val  = data.aqi;
    const info = aqiInfo(val);

    // Hero bar — Local AQI (fixed Barangay Hulo coordinates, never visitor location)
    if (heroAqiEl && heroAqiFact) {
      if (val === null || val === undefined) {
        heroAqiEl.textContent = 'Local AQI unavailable';
      } else {
        heroAqiEl.innerHTML = 'Local AQI ' + val + ' · <span style="color:' + info.color + ';font-weight:700">' + info.shortLabel + '</span>';
      }
      heroAqiFact.style.display = '';
      heroAqiFact.querySelector('svg').style.color = info.color;
      if (heroAqiDiv) heroAqiDiv.style.display = '';
    }

    // Hero bar — Advisory (short label)
    var heroAdvisoryEl   = document.getElementById('hero-advisory');
    var heroAdvisoryFact = document.getElementById('hero-advisory-fact');
    var heroAdvisoryDiv  = document.querySelector('.hero-advisory-divider');
    if (heroAdvisoryEl && heroAdvisoryFact && info.advisory) {
      heroAdvisoryEl.innerHTML = '<span style="color:' + info.color + ';font-weight:600">' + info.advisory + '</span>';
      heroAdvisoryFact.querySelector('svg').style.color = info.color;
      heroAdvisoryFact.style.display = '';
      if (heroAdvisoryDiv) heroAdvisoryDiv.style.display = '';
    }

    // Full advisory section
    if (aqiNum) {
      aqiNum.textContent  = val !== null ? val : '—';
      if (aqiRing) { aqiRing.style.borderColor = info.color; aqiRing.style.background = info.bg; }
    }
    if (aqiBadge) { aqiBadge.textContent = info.label; aqiBadge.style.background = info.bg; aqiBadge.style.color = info.color; }
    if (aqiMsg)     aqiMsg.textContent  = aqiHealthMsg(val);
    if (aqiUpdated) aqiUpdated.textContent = 'Updated: ' + (data.updated || '—');
    if (aqiPm25)    aqiPm25.textContent  = data.pm25 !== null ? data.pm25.toFixed(1) : '—';
    if (aqiPm10)    aqiPm10.textContent  = data.pm10 !== null ? data.pm10.toFixed(1) : '—';
    if (aqiO3)      aqiO3.textContent    = data.o3   !== null ? data.o3.toFixed(1)   : '—';
    if (aqiCo)      aqiCo.textContent    = data.co   !== null ? data.co.toFixed(1)   : '—';
    if (aqiNo2)     aqiNo2.textContent   = data.no2  !== null ? data.no2.toFixed(1)  : '—';
    if (aqiSo2)     aqiSo2.textContent   = data.so2  !== null ? data.so2.toFixed(1)  : '—';
  }

  function showAQIUnavailable() {
    renderAQI({ aqi: null });
  }

  function fetchAQI() {
    const url = 'https://air-quality-api.open-meteo.com/v1/air-quality'
      + '?latitude=' + AQI_LAT + '&longitude=' + AQI_LON
      + '&current=us_aqi'
      + '&timezone=Asia%2FManila';

    fetch(url)
      .then(function(r) { if (!r.ok) throw new Error('aqi-failed'); return r.json(); })
      .then(function(d) {
        var val = (d.current && d.current.us_aqi !== undefined && d.current.us_aqi !== null)
                  ? d.current.us_aqi : null;
        if (val === null) { showAQIUnavailable(); return; }
        var data = { aqi: val };
        try { localStorage.setItem(AQI_CACHE_KEY, JSON.stringify({ aqi: val, cachedAt: Date.now() })); } catch(e) {}
        renderAQI(data);
      })
      .catch(showAQIUnavailable);
  }

  // Load AQI on page load; refresh every 15 minutes
  (function initAQI() {
    if (!document.getElementById('hero-aqi-fact')) return;
    try {
      var cached = JSON.parse(localStorage.getItem(AQI_CACHE_KEY));
      if (cached && cached.aqi !== null && (Date.now() - cached.cachedAt) < AQI_TTL) {
        renderAQI({ aqi: cached.aqi });
      } else {
        fetchAQI();
      }
    } catch(e) { fetchAQI(); }
    setInterval(fetchAQI, AQI_TTL);
  })();

  // ── Tide Forecast via /api/tide (server-side proxy hides API key) ───────────
  var TIDE_CACHE_KEY = 'bhob_tide_cache';
  var TIDE_CACHE_TTL = 30 * 60 * 1000; // 30 minutes
  var TIDE_COLOR = '#38bdf8'; // sky blue

  function renderTide(data) {
    var highFact = document.getElementById('hero-tide-high-fact');
    var highSpan = document.getElementById('hero-tide-high');
    var highDiv  = document.querySelector('.hero-tide-high-divider');
    var lowFact  = document.getElementById('hero-tide-low-fact');
    var lowSpan  = document.getElementById('hero-tide-low');
    var lowDiv   = document.querySelector('.hero-tide-low-divider');
    var miniCard = document.getElementById('tide-mini-card');
    var miniHigh = document.getElementById('tide-mini-high');
    var miniLow  = document.getElementById('tide-mini-low');

    if (data.status !== 'ok') {
      // Show unavailable on desktop bar and mobile mini-card
      if (highFact && highSpan) {
        highSpan.textContent = 'Tide unavailable';
        highFact.style.display = '';
      }
      if (miniCard) {
        if (miniHigh) miniHigh.textContent = 'Tide unavailable';
        if (miniLow)  miniLow.textContent  = '';
        miniCard.style.display = '';
      }
      return;
    }

    var high = data.high || {};
    var low  = data.low  || {};

    // Status bar: "High 10:00 AM · 1.4 m"
    var highBar = 'High <span style="color:' + TIDE_COLOR + ';font-weight:700">' + (high.time || '') + '</span>'
                + (high.height ? ' · <span style="color:' + TIDE_COLOR + ';font-weight:600">' + high.height + '</span>' : '');
    var lowBar  = 'Low <span style="color:' + TIDE_COLOR + ';font-weight:700">' + (low.time  || '') + '</span>'
                + (low.height  ? ' · <span style="color:' + TIDE_COLOR + ';font-weight:600">' + low.height  + '</span>' : '');

    if (highFact && highSpan) {
      highSpan.innerHTML = highBar;
      var hSvg = highFact.querySelector('svg');
      if (hSvg) { hSvg.style.color = TIDE_COLOR; hSvg.style.opacity = '1'; }
      highFact.style.display = '';
      if (highDiv) highDiv.style.display = '';
    }
    if (lowFact && lowSpan) {
      lowSpan.innerHTML = lowBar;
      var lSvg = lowFact.querySelector('svg');
      if (lSvg) { lSvg.style.color = TIDE_COLOR; lSvg.style.opacity = '1'; }
      lowFact.style.display = '';
      if (lowDiv) lowDiv.style.display = '';
    }

    // Mobile mini-card — two rows
    if (miniCard) {
      if (miniHigh) miniHigh.innerHTML = '<span style="font-weight:700">High</span> '
        + '<span style="color:' + TIDE_COLOR + ';font-weight:700">' + (high.time || '') + '</span>'
        + (high.height ? ' · <span style="color:' + TIDE_COLOR + ';font-weight:600">' + high.height + '</span>' : '');
      if (miniLow) miniLow.innerHTML = '<span style="font-weight:700">Low</span> '
        + '<span style="color:' + TIDE_COLOR + ';font-weight:700">' + (low.time  || '') + '</span>'
        + (low.height  ? ' · <span style="color:' + TIDE_COLOR + ';font-weight:600">' + low.height  + '</span>' : '');
      miniCard.style.display = '';
    }
  }

  function parseTideFromMarineAPI(d) {
    // Find HIGH (max) and LOW (min) in the next 25 hours from now
    var times   = (d.hourly || {}).time || [];
    var heights = (d.hourly || {}).sea_level_height_msl || [];
    if (!times.length || !heights.length) return null;

    // Find current Manila hour index
    var now       = new Date();
    var manilaStr = now.toLocaleString('en-CA', { timeZone: 'Asia/Manila',
      year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', hour12: false });
    var parts  = manilaStr.replace(',','').trim().split(/\s+/);
    var isoNow = parts[0] + 'T' + (parts[1] === '24' ? '00' : parts[1]) + ':00';
    var startIdx = 0;
    for (var i = 0; i < times.length; i++) {
      if (times[i] === isoNow) { startIdx = i; break; }
    }

    // Build window of (time, height) pairs for next 25 hours
    var window = [];
    var endIdx = Math.min(startIdx + 25, times.length);
    for (var j = startIdx; j < endIdx; j++) {
      if (heights[j] !== null && heights[j] !== undefined) {
        window.push({ time: times[j], height: heights[j] });
      }
    }
    if (!window.length) return null;

    var highItem = window[0], lowItem = window[0];
    for (var k = 1; k < window.length; k++) {
      if (window[k].height > highItem.height) highItem = window[k];
      if (window[k].height < lowItem.height)  lowItem  = window[k];
    }

    function fmtTime(iso) {
      var h = parseInt(iso.slice(11, 13), 10);
      return (h % 12 || 12) + ':00 ' + (h < 12 ? 'AM' : 'PM');
    }
    function fmtH(v) { return (Math.round(v * 10) / 10).toFixed(1) + ' m'; }

    return {
      status: 'ok', estimated: true,
      high: { time: fmtTime(highItem.time), height: fmtH(highItem.height) },
      low:  { time: fmtTime(lowItem.time),  height: fmtH(lowItem.height)  },
    };
  }

  function fetchTideDirect() {
    var url = 'https://marine-api.open-meteo.com/v1/marine'
            + '?latitude=14.7201&longitude=120.9284'
            + '&hourly=sea_level_height_msl'
            + '&forecast_days=2'
            + '&timezone=Asia%2FManila';
    fetch(url)
      .then(function(r) { if (!r.ok) throw new Error('marine-failed'); return r.json(); })
      .then(function(d) {
        var data = parseTideFromMarineAPI(d);
        if (!data) { renderTide({ status: 'unavailable' }); return; }
        try { localStorage.setItem(TIDE_CACHE_KEY, JSON.stringify({ data: data, cachedAt: Date.now() })); } catch(e) {}
        renderTide(data);
      })
      .catch(function() { renderTide({ status: 'unavailable' }); });
  }

  function fetchTide() {
    fetch('/api/tide')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.status !== 'ok') { fetchTideDirect(); return; }
        try { localStorage.setItem(TIDE_CACHE_KEY, JSON.stringify({ data: data, cachedAt: Date.now() })); } catch(e) {}
        renderTide(data);
      })
      .catch(fetchTideDirect);
  }

  (function initTide() {
    if (!document.getElementById('hero-tide-high-fact')) return; // index.html only
    try {
      var cached = JSON.parse(localStorage.getItem(TIDE_CACHE_KEY));
      if (cached && cached.data && (Date.now() - cached.cachedAt) < TIDE_CACHE_TTL) {
        renderTide(cached.data);
        return;
      }
    } catch(e) {}
    fetchTide();
    setInterval(fetchTide, TIDE_CACHE_TTL);
  })();



  // Lightweight pointer glow for desktop only
  if (window.matchMedia('(hover: hover)').matches) {
    document.querySelectorAll('.info-card, .official-card, .image-card, .download-card, .profile-item, .btn').forEach((el) => {
      el.addEventListener('pointermove', (event) => {
        const rect = el.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / rect.width) * 100;
        const y = ((event.clientY - rect.top) / rect.height) * 100;
        el.style.setProperty('--mx', `${x}%`);
        el.style.setProperty('--my', `${y}%`);
      });
    });
  }

  // Citizen's Charter process section observer
  const processSection = document.querySelector('.charter-section');
  if (processSection) {
    const revealProcess = () => processSection.classList.add('process-in-view');
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            revealProcess();
            observer.disconnect();
          }
        });
      }, { threshold: 0.22 });
      observer.observe(processSection);
    } else {
      revealProcess();
    }
  }

  // ── CMS content sync ───────────────────────────────────────────────────────
  // Applies configured site settings to any element carrying data-setting,
  // data-setting-src or data-setting-href. The server already injects these
  // values into the markup (see _inject_page in server.py); this pass mirrors
  // it exactly so the two can never disagree, and keeps working if the server
  // render ever falls back to the raw file.
  //
  // Note this runs alongside the per-page inline settings scripts. Those own
  // their own elements; nothing here should carry both mechanisms.
  fetch('/api/site-settings')
    .then(function (r) { return r.json(); })
    .then(function (s) {
      // A failed or empty read must leave the shipped markup alone rather than
      // blanking the page.
      if (!s || !Object.keys(s).length) return;

      document.querySelectorAll('[data-setting]').forEach(function (el) {
        var key = el.getAttribute('data-setting');
        // A key missing from the payload has never been configured, so leave
        // the markup's own copy in place. A key that IS present but empty was
        // deliberately cleared in admin and must blank the element.
        if (!(key in s)) return;
        el.textContent = s[key] || '';
      });

      // href — the element always renders; a link is attached only when its URL
      // is configured, so it stays inert rather than keeping a stale hardcoded
      // destination.
      document.querySelectorAll('[data-setting-href]').forEach(function (el) {
        var key = el.getAttribute('data-setting-href');
        if (s[key]) { el.href = s[key]; }
        else { el.removeAttribute('href'); }
      });

      // src — unlike href, an unset value leaves the markup's own src intact.
      // A missing logo setting must fall back to the shipped image rather than
      // render an empty box.
      document.querySelectorAll('[data-setting-src]').forEach(function (el) {
        var key = el.getAttribute('data-setting-src');
        var val = s[key];
        if (val) el.src = val.indexOf('http') === 0 ? val : '/' + val.replace(/^\/+/, '');
      });

      // <title data-site-title> — "Name | Locality"
      var parts = [s.barangay_name, s.barangay_locality].filter(Boolean);
      if (parts.length) {
        document.querySelectorAll('title[data-site-title]').forEach(function (el) {
          el.textContent = parts.join(' | ');
        });
      }
    })
    .catch(function () { /* silent — shipped markup stays */ });
})();
