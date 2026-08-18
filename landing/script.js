(() => {
  'use strict';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const header = document.querySelector('#siteHeader');
  const hero = document.querySelector('.hero');
  const finalCta = document.querySelector('#finalCta');
  const mobileCta = document.querySelector('#mobileCta');
  const reveals = [...document.querySelectorAll('.reveal')];

  if (reduceMotion || !('IntersectionObserver' in window)) {
    reveals.forEach((item) => item.classList.add('revealed'));
  } else {
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('revealed');
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    reveals.forEach((item) => revealObserver.observe(item));
  }

  let ticking = false;
  const updateChrome = () => {
    header?.classList.toggle('scrolled', window.scrollY > 12);
    if (hero && finalCta && mobileCta) {
      const heroPassed = window.scrollY > hero.offsetTop + hero.offsetHeight * 0.65;
      const finalReached = finalCta.getBoundingClientRect().top < window.innerHeight * 0.92;
      mobileCta.classList.toggle('visible', heroPassed && !finalReached);
    }
    ticking = false;
  };
  const onScroll = () => {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(updateChrome);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll, { passive: true });
  updateChrome();

  document.querySelectorAll('details').forEach((item) => {
    item.addEventListener('toggle', () => {
      if (!item.open) return;
      document.querySelectorAll('details[open]').forEach((other) => {
        if (other !== item) other.open = false;
      });
    });
  });

  document.querySelectorAll('.track-cta').forEach((link) => {
    link.addEventListener('click', () => {
      const detail = { event: 'cta_click', location: link.dataset.ctaLocation || 'unknown', href: link.href };
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push(detail);
      window.dispatchEvent(new CustomEvent('svoi:cta_click', { detail }));
    });
  });
})();
