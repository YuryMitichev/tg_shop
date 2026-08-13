(function () {
  'use strict';

  /* ===== SCROLL REVEAL via Intersection Observer ===== */
  var revealEls = document.querySelectorAll('.reveal');

  if ('IntersectionObserver' in window && revealEls.length) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');
          observer.unobserve(entry.target);
        }
      });
    }, {
      rootMargin: '0px 0px -60px 0px',
      threshold: 0.1
    });

    revealEls.forEach(function (el) {
      observer.observe(el);
    });
  } else {
    revealEls.forEach(function (el) {
      el.classList.add('revealed');
    });
  }

  /* ===== HEADER SHADOW ON SCROLL ===== */
  var header = document.getElementById('siteHeader');
  var scrolledClass = 'scrolled';

  function updateHeader() {
    if (window.scrollY > 8) {
      header.classList.add(scrolledClass);
    } else {
      header.classList.remove(scrolledClass);
    }
  }

  /* ===== STICKY MOBILE CTA ===== */
  var stickyCta = document.getElementById('stickyCta');
  var hero = document.querySelector('.hero');
  var finalCta = document.querySelector('.cta-final');

  function updateStickyCta() {
    var scrollY = window.scrollY;
    var showAfter = hero ? hero.offsetHeight * 0.6 : 400;
    var hideAt = finalCta ? finalCta.offsetTop - window.innerHeight + 100 : Infinity;

    if (scrollY > showAfter && scrollY < hideAt) {
      stickyCta.classList.add('visible');
    } else {
      stickyCta.classList.remove('visible');
    }
  }

  /* ===== COMBINED SCROLL HANDLER (throttled via rAF) ===== */
  var ticking = false;

  function onScroll() {
    if (!ticking) {
      window.requestAnimationFrame(function () {
        updateHeader();
        updateStickyCta();
        ticking = false;
      });
      ticking = true;
    }
  }

  window.addEventListener('scroll', onScroll, { passive: true });
  updateHeader();
  updateStickyCta();

  /* ===== FAQ: CLOSE OTHERS ON OPEN (optional UX enhancement) ===== */
  var faqItems = document.querySelectorAll('.faq-item');

  faqItems.forEach(function (item) {
    item.addEventListener('toggle', function () {
      if (item.open) {
        faqItems.forEach(function (other) {
          if (other !== item && other.open) {
            other.open = false;
          }
        });
      }
    });
  });

})();
