/** MagicTech Store — Animations & Interactions
 * - Canvas particle network (constellation effect)
 * - IntersectionObserver scroll-reveal
 * - 3D tilt on product cards
 * - Fly-to-cart animation
 * - Header scroll morph
 * - Counter animations
 */
(function () {
  'use strict';

  // ===== CANVAS PARTICLE NETWORK =====
  function initParticles() {
    const canvas = document.getElementById('particles-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w, h, particles = [], mouse = { x: null, y: null };
    const PARTICLE_COUNT = 50;
    const MAX_DIST = 120;

    function resize() {
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    // Create particles
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        r: Math.random() * 2 + 1
      });
    }

    // Track mouse
    document.addEventListener('mousemove', (e) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    });

    function draw() {
      ctx.clearRect(0, 0, w, h);

      // Get theme colors
      const style = getComputedStyle(document.documentElement);
      const accent = style.getPropertyValue('--accent').trim() || '#4f46e5';
      const accentSec = style.getPropertyValue('--accent-sec').trim() || '#06b6d4';
      const isDark = document.documentElement.dataset.theme === 'dark';
      const alpha = isDark ? 0.3 : 0.15;

      // Update and draw particles
      particles.forEach(p => {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > w) p.vx *= -1;
        if (p.y < 0 || p.y > h) p.vy *= -1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = accent;
        ctx.globalAlpha = alpha;
        ctx.fill();
      });

      // Draw connections
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < MAX_DIST) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = accent;
            ctx.globalAlpha = (1 - dist / MAX_DIST) * alpha * 0.5;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }

        // Mouse interaction
        if (mouse.x !== null) {
          const dx = particles[i].x - mouse.x;
          const dy = particles[i].y - mouse.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 150) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(mouse.x, mouse.y);
            ctx.strokeStyle = accentSec;
            ctx.globalAlpha = (1 - dist / 150) * 0.2;
            ctx.lineWidth = 0.8;
            ctx.stroke();
          }
        }
      }
      ctx.globalAlpha = 1;
      requestAnimationFrame(draw);
    }
    draw();
  }

  // ===== SCROLL REVEAL (IntersectionObserver) =====
  function initReveal() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          // Don't unobserve — allow re-triggering if needed
        }
      });
    }, {
      threshold: 0.1,
      rootMargin: '0px 0px -50px 0px'
    });

    document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-scale, .reveal-stagger').forEach(el => {
      observer.observe(el);
    });
  }

  // ===== 3D TILT ON PRODUCT CARDS =====
  function initTilt() {
    document.querySelectorAll('.product-card').forEach(card => {
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        const rotateX = ((y - centerY) / centerY) * -5;
        const rotateY = ((x - centerX) / centerX) * 5;

        card.style.transform = `perspective(800px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(1.02)`;
      });

      card.addEventListener('mouseleave', () => {
        card.style.transform = 'perspective(800px) rotateX(0) rotateY(0) scale(1)';
      });
    });
  }

  // ===== FLY-TO-CART ANIMATION =====
  function initFlyToCart() {
    document.querySelectorAll('.product-card form[action*="cart_add"]').forEach(form => {
      // Also handle non-form buttons
      const btn = form.querySelector('button') || form.querySelector('a');
      if (!btn) return;

      btn.addEventListener('click', (e) => {
        const card = form.closest('.product-card');
        if (!card) return;

        const img = card.querySelector('img');
        if (!img) return;

        const cartLink = document.querySelector('.cart-link');
        if (!cartLink) return;

        // Create fly element
        const fly = document.createElement('div');
        fly.className = 'fly-item';
        const imgRect = img.getBoundingClientRect();
        fly.style.left = imgRect.left + imgRect.width / 2 - 25 + 'px';
        fly.style.top = imgRect.top + imgRect.height / 2 - 25 + 'px';
        document.body.appendChild(fly);

        // Animate
        requestAnimationFrame(() => {
          const cartRect = cartLink.getBoundingClientRect();
          fly.style.left = cartRect.left + cartRect.width / 2 - 25 + 'px';
          fly.style.top = cartRect.top + cartRect.height / 2 - 25 + 'px';
          fly.classList.add('fly');
        });

        // Remove after animation
        setTimeout(() => fly.remove(), 850);
      });
    });
  }

  // ===== HEADER SCROLL MORPH =====
  function initHeaderScroll() {
    const header = document.querySelector('.header');
    if (!header) return;

    let ticking = false;
    window.addEventListener('scroll', () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          header.classList.toggle('scrolled', window.scrollY > 20);
          ticking = false;
        });
        ticking = true;
      }
    });
  }

  // ===== HERO PARALLAX =====
  function initHeroParallax() {
    const hero = document.querySelector('.hero');
    if (!hero) return;

    window.addEventListener('scroll', () => {
      const scrolled = window.scrollY;
      const heroHeight = hero.offsetHeight;
      if (scrolled < heroHeight) {
        const orb = hero.querySelector('.hero-orb');
        if (orb) {
          orb.style.transform = `translateY(${scrolled * 0.15}px)`;
        }
      }
    });
  }

  // ===== COUNTER ANIMATION =====
  function initCounters() {
    document.querySelectorAll('[data-count]').forEach(el => {
      const target = parseInt(el.dataset.count, 10);
      const duration = 1500;
      const start = performance.now();

      function update(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(target * eased);
        if (progress < 1) requestAnimationFrame(update);
      }
      requestAnimationFrame(update);
    });
  }

  // ===== SMOOTH ANCHOR SCROLL =====
  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        const target = document.querySelector(anchor.getAttribute('href'));
        if (target) {
          e.preventDefault();
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });
  }

  // ===== SEARCH INPUT GLOW =====
  function initSearchGlow() {
    const searchInput = document.querySelector('.search input[type="search"]');
    if (!searchInput) return;

    const glow = document.createElement('div');
    glow.style.cssText = 'position:absolute;inset:-2px;border-radius:999px;background:linear-gradient(135deg,var(--accent),var(--accent-sec));z-index:-1;opacity:0;transition:opacity 0.3s;filter:blur(8px);';
    searchInput.parentElement.style.position = 'relative';
    searchInput.parentElement.insertBefore(glow, searchInput);

    searchInput.addEventListener('focus', () => glow.style.opacity = '0.4');
    searchInput.addEventListener('blur', () => glow.style.opacity = '0');
  }

  // ===== INIT =====
  document.addEventListener('DOMContentLoaded', () => {
    initParticles();
    initReveal();
    initTilt();
    initFlyToCart();
    initHeaderScroll();
    initHeroParallax();
    initCounters();
    initSmoothScroll();
    initSearchGlow();
  });
})();
