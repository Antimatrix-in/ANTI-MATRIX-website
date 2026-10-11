/**
 * Anti-Matrix — Automatic Client Testimonial Slider
 * Responsive, accessible, infinite horizontal sliding testimonial carousel.
 */
(function () {
  'use strict';

  function initTestimonialSlider() {
    var container = document.getElementById('testimonialSlider');
    if (!container) return;

    var viewport = container.querySelector('#testimonialViewport');
    var track = container.querySelector('#testimonialTrack');
    var prevBtn = container.querySelector('#testimonialPrevBtn');
    var nextBtn = container.querySelector('#testimonialNextBtn');

    if (!viewport || !track || !prevBtn || !nextBtn) return;

    var originalSlides = Array.from(track.querySelectorAll('.testimonial-slide'));
    var totalRealSlides = originalSlides.length;
    if (totalRealSlides === 0) return;

    // Check prefers-reduced-motion
    var prefersReducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    var prefersReducedMotion = prefersReducedMotionQuery.matches;
    prefersReducedMotionQuery.addEventListener('change', function (e) {
      prefersReducedMotion = e.matches;
      if (prefersReducedMotion) {
        stopAutoplay();
      } else {
        startAutoplay();
      }
    });

    var AUTOPLAY_INTERVAL = 3500; // 3.5 seconds
    var TRANSITION_DURATION = 500; // 500ms
    var TRANSITION_EASE = 'cubic-bezier(0.25, 1, 0.5, 1)';

    var currentIndex = 1; // 1-based index because slide 0 is clone of last
    var isAnimating = false;
    var autoplayTimer = null;
    var isHovered = false;
    var isFocused = false;
    var safetyTimeout = null;

    // If there is only 1 slide, no need for infinite loop or navigation controls
    if (totalRealSlides <= 1) {
      prevBtn.style.display = 'none';
      nextBtn.style.display = 'none';
      return;
    }

    // Clone boundary slides for seamless infinite loop
    var lastClone = originalSlides[totalRealSlides - 1].cloneNode(true);
    lastClone.setAttribute('aria-hidden', 'true');
    lastClone.classList.add('testimonial-slide-clone');
    lastClone.removeAttribute('id');

    var firstClone = originalSlides[0].cloneNode(true);
    firstClone.setAttribute('aria-hidden', 'true');
    firstClone.classList.add('testimonial-slide-clone');
    firstClone.removeAttribute('id');

    track.insertBefore(lastClone, track.firstChild);
    track.appendChild(firstClone);

    var allSlides = Array.from(track.querySelectorAll('.testimonial-slide'));

    function applyPosition(index, animate) {
      if (animate && !prefersReducedMotion) {
        track.style.transition = 'transform ' + TRANSITION_DURATION + 'ms ' + TRANSITION_EASE;
      } else {
        track.style.transition = 'none';
      }
      track.style.transform = 'translate3d(-' + (index * 100) + '%, 0, 0)';
    }

    function updateAccessibility() {
      allSlides.forEach(function (slide, idx) {
        var isCurrent = idx === currentIndex;
        if (slide.classList.contains('testimonial-slide-clone')) {
          slide.setAttribute('aria-hidden', 'true');
        } else {
          slide.setAttribute('aria-hidden', isCurrent ? 'false' : 'true');
        }
      });
    }

    // Set initial position without animation
    applyPosition(currentIndex, false);
    updateAccessibility();

    function goToNext() {
      if (isAnimating) return;
      isAnimating = true;
      currentIndex++;
      applyPosition(currentIndex, true);
      armSafetyTimeout();
    }

    function goToPrev() {
      if (isAnimating) return;
      isAnimating = true;
      currentIndex--;
      applyPosition(currentIndex, true);
      armSafetyTimeout();
    }

    // Safety fallback in case transitionend is delayed or missed
    function armSafetyTimeout() {
      if (safetyTimeout) clearTimeout(safetyTimeout);
      safetyTimeout = setTimeout(function () {
        if (isAnimating) {
          handleTransitionEnd();
        }
      }, TRANSITION_DURATION + 150);
    }

    function handleTransitionEnd() {
      if (safetyTimeout) {
        clearTimeout(safetyTimeout);
        safetyTimeout = null;
      }

      // Check if we reached the clones and seamlessly wrap around
      if (currentIndex >= totalRealSlides + 1) {
        // We moved past the last real slide to firstClone -> wrap to first real slide (index 1)
        currentIndex = 1;
        applyPosition(currentIndex, false);
      } else if (currentIndex <= 0) {
        // We moved before the first real slide to lastClone -> wrap to last real slide
        currentIndex = totalRealSlides;
        applyPosition(currentIndex, false);
      }

      isAnimating = false;
      updateAccessibility();
    }

    track.addEventListener('transitionend', function (e) {
      if (e.target !== track || e.propertyName !== 'transform') return;
      handleTransitionEnd();
    });

    // ── Autoplay Management ──────────────────────────────
    function startAutoplay() {
      stopAutoplay();
      if (prefersReducedMotion || isHovered || isFocused || document.hidden) {
        return;
      }
      autoplayTimer = setInterval(function () {
        goToNext();
      }, AUTOPLAY_INTERVAL);
    }

    function stopAutoplay() {
      if (autoplayTimer) {
        clearInterval(autoplayTimer);
        autoplayTimer = null;
      }
    }

    function resetAutoplay() {
      stopAutoplay();
      startAutoplay();
    }

    // ── Manual Navigation Controls ──────────────────────
    nextBtn.addEventListener('click', function (e) {
      e.preventDefault();
      goToNext();
      resetAutoplay();
    });

    prevBtn.addEventListener('click', function (e) {
      e.preventDefault();
      goToPrev();
      resetAutoplay();
    });

    // ── Pause on Hover & Focus ──────────────────────────
    container.addEventListener('mouseenter', function () {
      isHovered = true;
      stopAutoplay();
    });

    container.addEventListener('mouseleave', function () {
      isHovered = false;
      startAutoplay();
    });

    container.addEventListener('focusin', function () {
      isFocused = true;
      stopAutoplay();
    });

    container.addEventListener('focusout', function () {
      isFocused = false;
      startAutoplay();
    });

    // ── Page Visibility Handling ────────────────────────
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) {
        stopAutoplay();
      } else {
        startAutoplay();
      }
    });

    // ── Keyboard Navigation ─────────────────────────────
    container.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        goToPrev();
        resetAutoplay();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        goToNext();
        resetAutoplay();
      }
    });

    // ── Mobile Touch / Swipe Handling ───────────────────
    var touchStartX = 0;
    var touchStartY = 0;
    var touchMoved = false;

    viewport.addEventListener('touchstart', function (e) {
      if (e.touches.length === 1) {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchMoved = false;
        stopAutoplay();
      }
    }, { passive: true });

    viewport.addEventListener('touchmove', function (e) {
      touchMoved = true;
    }, { passive: true });

    viewport.addEventListener('touchend', function (e) {
      if (!touchMoved) {
        startAutoplay();
        return;
      }
      var touchEndX = e.changedTouches[0].clientX;
      var touchEndY = e.changedTouches[0].clientY;
      var deltaX = touchEndX - touchStartX;
      var deltaY = touchEndY - touchStartY;

      // Ensure horizontal swipe is dominant and exceeds minimum threshold
      if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 40) {
        if (deltaX < 0) {
          // Swiped left -> Next
          goToNext();
        } else {
          // Swiped right -> Prev
          goToPrev();
        }
      }
      resetAutoplay();
    }, { passive: true });

    // ── Cleanup on Unload ────────────────────────────────
    window.addEventListener('beforeunload', stopAutoplay);
    window.addEventListener('pagehide', stopAutoplay);

    // Start initial autoplay cycle
    startAutoplay();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTestimonialSlider);
  } else {
    initTestimonialSlider();
  }
})();
