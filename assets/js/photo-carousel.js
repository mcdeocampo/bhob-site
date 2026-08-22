// Shared photo carousel for Announcement/Community Initiative "Read More"
// modals. Renders nothing for 0 photos (existing no-image behaviour is
// untouched), a plain <img> for 1 photo (no controls), and a swipeable/
// keyboard-navigable carousel with prev/next buttons + counter for 2+.
// Vanilla JS, no external library -- loaded only by announcements.html and
// projects.html, which each call window.initPhotoCarousel(wrapEl, photos)
// from their own openModal().
(function () {
  'use strict';

  function esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Photo URLs come back either as absolute (Supabase Storage uploads) or
  // site-relative (the "Default Images" picker, e.g. "assets/images/...")
  // -- same normalization the rest of this codebase already applies to
  // imageUrl before using it as an <img src>.
  function resolveUrl(url) {
    return url && url.indexOf('http') === 0 ? url : '/' + url;
  }

  window.initPhotoCarousel = function (wrapEl, photos) {
    if (!wrapEl) return;
    photos = Array.isArray(photos) ? photos.filter(function (p) { return p && p.url; }) : [];

    // Tear down any previous instance's listeners bound to this wrap element.
    if (wrapEl._carouselCleanup) { wrapEl._carouselCleanup(); wrapEl._carouselCleanup = null; }

    if (!photos.length) {
      wrapEl.innerHTML = '';
      wrapEl.style.display = 'none';
      return;
    }

    wrapEl.style.display = 'block';

    if (photos.length === 1) {
      wrapEl.innerHTML = '<img src="' + esc(resolveUrl(photos[0].url)) + '" alt="' + esc(photos[0].name || '') + '" style="width:100%;height:100%;object-fit:cover;display:block">';
      return;
    }

    var idx = 0;

    wrapEl.innerHTML =
      '<div class="photo-carousel">' +
        '<img class="photo-carousel-img" src="" alt="">' +
        '<button type="button" class="photo-carousel-btn photo-carousel-btn--prev" aria-label="Previous photo">&#8249;</button>' +
        '<button type="button" class="photo-carousel-btn photo-carousel-btn--next" aria-label="Next photo">&#8250;</button>' +
        '<div class="photo-carousel-counter"></div>' +
      '</div>';

    var track   = wrapEl.querySelector('.photo-carousel');
    var imgEl   = wrapEl.querySelector('.photo-carousel-img');
    var prevBtn = wrapEl.querySelector('.photo-carousel-btn--prev');
    var nextBtn = wrapEl.querySelector('.photo-carousel-btn--next');
    var counter = wrapEl.querySelector('.photo-carousel-counter');

    function render() {
      var p = photos[idx];
      imgEl.src = resolveUrl(p.url);
      imgEl.alt = p.name || '';
      counter.textContent = (idx + 1) + ' / ' + photos.length;
    }

    function nav(dir) {
      idx = (idx + dir + photos.length) % photos.length;
      render();
    }

    prevBtn.addEventListener('click', function () { nav(-1); });
    nextBtn.addEventListener('click', function () { nav(1); });

    // Keyboard nav only while this carousel's modal is actually visible --
    // mirrors the existing Calendar lightbox's own keydown gating rather
    // than capturing arrow keys globally.
    function onKeydown(e) {
      if (wrapEl.offsetParent === null) return; // hidden (modal closed)
      if (e.key === 'ArrowLeft')  { nav(-1); }
      else if (e.key === 'ArrowRight') { nav(1); }
    }
    document.addEventListener('keydown', onKeydown);

    // Touch swipe: only treat as a swipe if the gesture is predominantly
    // horizontal and past a small threshold, so normal vertical page
    // scrolling and small accidental movements are never hijacked.
    var touchStartX = 0, touchStartY = 0, touchActive = false;
    var SWIPE_THRESHOLD = 40;

    function onTouchStart(e) {
      if (!e.touches || !e.touches.length) return;
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      touchActive = true;
    }
    function onTouchEnd(e) {
      if (!touchActive) return;
      touchActive = false;
      var t = (e.changedTouches && e.changedTouches[0]) || null;
      if (!t) return;
      var dx = t.clientX - touchStartX;
      var dy = t.clientY - touchStartY;
      if (Math.abs(dx) < SWIPE_THRESHOLD || Math.abs(dx) < Math.abs(dy)) return;
      nav(dx < 0 ? 1 : -1);
    }
    track.addEventListener('touchstart', onTouchStart, { passive: true });
    track.addEventListener('touchend', onTouchEnd, { passive: true });

    wrapEl._carouselCleanup = function () {
      document.removeEventListener('keydown', onKeydown);
    };

    render();
  };
})();
