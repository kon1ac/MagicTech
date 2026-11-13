/* ==========================================================================
   MagicTech Store — ядро интерактива (store.js)
   Чистый ванильный JS, без внешних зависимостей.
   Содержит: MT.tween (мини-движок анимаций в духе anime.js), тема,
   prefers-reduced-motion, кастомный курсор, ripple, шапка, прогресс-скролл,
   scroll-reveal, тосты, переходы между страницами, skeleton, счётчик корзины.
   ========================================================================== */
(function () {
  'use strict';

  var root = document.documentElement;
  var reduceQuery = window.matchMedia('(prefers-reduced-motion: reduce)');

  /* ======================================================================
     1. MT.tween — компактный движок анимаций (API вдохновлён anime.js)
     Работает только с transform/opacity через rAF → GPU-ускорение.
     ====================================================================== */
  var EASINGS = {
    linear: function (t) { return t; },
    easeInQuad: function (t) { return t * t; },
    easeOutQuad: function (t) { return t * (2 - t); },
    easeInQuart: function (t) { return t * t * t * t; },
    easeOutQuart: function (t) { return 1 - Math.pow(1 - t, 4); },
    easeInOutQuart: function (t) {
      return t < 0.5 ? 8 * t * t * t * t : 1 - Math.pow(-2 * t + 2, 4) / 2;
    },
    easeInOutCubic: function (t) {
      return t < 0.5 ? 4 * t * t * t : (t - 1) * (2 * t - 2) * (2 * t - 2) + 1;
    },
    easeOutBack: function (t) {
      var c = 1.70158;
      return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2);
    },
    easeOutElastic: function (t) {
      var c = (2 * Math.PI) / 3;
      return t === 0 ? 0 : t === 1 ? 1
        : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * c) + 1;
    }
  };

  function tween(opts) {
    var duration = opts.duration || 400;
    var easing = EASINGS[opts.easing] || EASINGS.easeInOutCubic;
    var delay = opts.delay || 0;
    var start = null;
    var handle = { cancelled: false };

    // при уменьшенной анимации сразу прыгаем в конечное состояние
    if (reduceQuery.matches) {
      opts.update(1);
      if (opts.complete) opts.complete();
      return handle;
    }

    function frame(now) {
      if (handle.cancelled) return;
      if (start === null) start = now;
      var elapsed = now - start - delay;
      if (elapsed < 0) { requestAnimationFrame(frame); return; }
      var t = Math.min(elapsed / duration, 1);
      opts.update(easing(t));
      if (t < 1) {
        requestAnimationFrame(frame);
      } else if (opts.complete) {
        opts.complete();
      }
    }
    requestAnimationFrame(frame);
    return handle;
  }

  // Публичный мини-API: MT.to(el, {opacity, y, scale, rotate}, {duration, delay, easing})
  // Значения interpolируются от «нулевого» состояния к указанным.
  var MT = {
    tween: tween,
    reduced: function () { return reduceQuery.matches; },
    to: function (el, props, opts) {
      opts = opts || {};
      var startOpacity = parseFloat(getComputedStyle(el).opacity) || 0;
      var targetOpacity = props.opacity !== undefined ? props.opacity : 1;
      return tween({
        duration: opts.duration,
        delay: opts.delay,
        easing: opts.easing,
        update: function (p) {
          var parts = [];
          if ('y' in props) parts.push('translateY(' + (props.y * (1 - p)) + 'px)');
          if ('x' in props) parts.push('translateX(' + (props.x * (1 - p)) + 'px)');
          if ('scale' in props) parts.push('scale(' + (1 + (props.scale - 1) * p) + ')');
          if ('rotate' in props) parts.push('rotate(' + (props.rotate * p) + 'deg)');
          el.style.opacity = String(startOpacity + (targetOpacity - startOpacity) * p);
          if (parts.length) el.style.transform = parts.join(' ');
        },
        complete: opts.complete
      });
    }
  };
  window.MT = MT;

  /* ======================================================================
     2. Тема: сохранение выбора, плавное переключение, синхронизация
     ====================================================================== */
  var THEME_KEY = 'magtech-store-theme';

  function applyTheme(theme, animate) {
    if (animate && !reduceQuery.matches) {
      root.classList.add('theme-animating');
      // класс снимаем после завершения перехода цветов
      clearTimeout(applyTheme._t);
      applyTheme._t = setTimeout(function () {
        root.classList.remove('theme-animating');
      }, 600);
    }
    root.dataset.theme = theme;
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* приватный режим */ }
    document.querySelectorAll('.theme-switch').forEach(function (btn) {
      btn.setAttribute('aria-label', theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему');
      btn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
    });
    // событие нужно карточкам/градиентам, читающим CSS-переменные
    document.dispatchEvent(new CustomEvent('mt:theme', { detail: { theme: theme } }));
  }

  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch (e) { /* noop */ }
    applyTheme(saved || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'), false);

    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.theme-switch');
      if (!btn) return;
      applyTheme(root.dataset.theme === 'dark' ? 'light' : 'dark', true);
    });
  }

  /* ======================================================================
     4. Ripple — волна от точки клика по кнопке
     ====================================================================== */
  function initRipple() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.btn, .icon-btn, .tab-btn, .theme-switch, .wish-btn');
      if (!btn || reduceQuery.matches) return;

      var rect = btn.getBoundingClientRect();
      var size = Math.max(rect.width, rect.height);
      var wave = document.createElement('span');
      wave.className = 'ripple';
      wave.style.width = wave.style.height = size + 'px';
      wave.style.left = (e.clientX - rect.left - size / 2) + 'px';
      wave.style.top = (e.clientY - rect.top - size / 2) + 'px';
      btn.appendChild(wave);
      setTimeout(function () { wave.remove(); }, 700);
    });
  }

  /* ======================================================================
     5. Шапка: компактеется при скролле + верхний прогресс-бар
     ====================================================================== */
  function initHeader() {
    var header = document.querySelector('.header');
    var bar = document.querySelector('.scroll-progress .bar');
    if (!header && !bar) return;

    // реальная высота шапки (двухрядная на десктопе, однострочная при скролле)
    // подставляем в CSS-переменную, чтобы calc(var(--header-h)) для sticky-элементов
    // всегда знал, где заканчивается шапка
    function setHeaderHeight() {
      root.style.setProperty('--header-h', header.offsetHeight + 'px');
    }
    setHeaderHeight();
    window.addEventListener('resize', function () { setHeaderHeight(); }, { passive: true });

    var ticking = false;
    function update() {
      var y = window.scrollY;
      if (header) {
        var compact = y > 24;
        if (header.classList.contains('is-compact') !== compact) {
          header.classList.toggle('is-compact', compact);
          setHeaderHeight();          // ряд меню скрыт/показан — высота изменилась
        }
      }
      if (bar) {
        var max = document.documentElement.scrollHeight - window.innerHeight;
        bar.style.width = (max > 0 ? Math.min(y / max, 1) : 0) * 100 + '%';
      }
      ticking = false;
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { requestAnimationFrame(update); ticking = true; }
    }, { passive: true });
    update();
  }

  /* ======================================================================
     6. Scroll-reveal — элементы выезжают снизу каскадом
     ====================================================================== */
  function initReveal() {
    var items = document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-scale, .reveal-stagger');
    if (!items.length) return;

    if (reduceQuery.matches || !('IntersectionObserver' in window)) {
      items.forEach(function (el) { el.classList.add('visible'); });
      return;
    }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('visible');
        io.unobserve(entry.target);   // анимация показывается один раз
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

    items.forEach(function (el) { io.observe(el); });
  }

  /* ======================================================================
     7. Тост-уведомления: выезжают снизу с прогресс-баром
     ====================================================================== */
  var ICONS = { success: '✓', error: '✕', info: 'ℹ', warning: '!' };

  function toast(message, tag) {
    var box = document.querySelector('.toast-container');
    if (!box) return null;

    var el = document.createElement('div');
    el.className = 'toast toast-' + (tag || 'info');
    el.setAttribute('role', 'status');
    el.innerHTML = '<span class="toast-icon"></span><span class="toast-text"></span><span class="toast-bar"></span>';
    el.querySelector('.toast-icon').textContent = ICONS[tag] || ICONS.info;
    el.querySelector('.toast-text').textContent = message;
    box.appendChild(el);

    requestAnimationFrame(function () {
      requestAnimationFrame(function () { el.classList.add('is-visible'); });
    });

    var life = reduceQuery.matches ? 2500 : 4200;
    var timer = setTimeout(close, life);
    function close() {
      clearTimeout(timer);
      el.classList.remove('is-visible');
      setTimeout(function () { el.remove(); }, 500);
    }
    el.addEventListener('click', close);
    return el;
  }

  // сообщения Django из {% if messages %} превращаем в тосты при загрузке
  function promoteDjangoMessages() {
    var list = document.querySelector('.messages');
    if (!list) return;
    Array.prototype.forEach.call(list.querySelectorAll('.msg'), function (li) {
      var tag = 'info';
      (li.className.match(/msg-(\w+)/) || []).some(function (part) {
        if (part.indexOf('msg-') === 0) { tag = part.slice(4); return true; }
        return false;
      });
      toast(li.textContent.trim(), tag);
    });
    list.remove();
  }

  /* ======================================================================
     8. Переход между страницами: fade-out старой → fade-in новой
     ====================================================================== */
  function initPageTransitions() {
    var main = document.querySelector('main');
    if (!main || reduceQuery.matches) return;

    main.style.opacity = '0';
    main.style.transform = 'translateY(14px)';
    MT.tween({
      duration: 520,
      easing: 'easeOutQuad',
      update: function (p) {
        main.style.opacity = String(p);
        main.style.transform = 'translateY(' + (14 * (1 - p)) + 'px)';
      }
    });

    document.addEventListener('click', function (e) {
      var link = e.target.closest('a');
      if (!link) return;
      var href = link.getAttribute('href');
      // перехватываем только обычную навигацию по тому же документу
      if (!href || href.charAt(0) === '#' || link.target === '_blank' ||
          link.hasAttribute('download') || link.dataset.noTransition !== undefined) return;
      if (link.protocol !== location.protocol || link.host !== location.host) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      if (href === location.pathname + location.search) return;

      e.preventDefault();
      MT.tween({
        duration: 260,
        easing: 'easeOutQuad',
        update: function (p) {
          main.style.opacity = String(1 - p);
          main.style.transform = 'translateY(' + (-12 * p) + 'px)';
        },
        complete: function () { location.href = href; }
      });
    });

    // если пользователь вернулся назад — контент уже виден
    window.addEventListener('pageshow', function (e) {
      if (e.persisted) { main.style.opacity = '1'; main.style.transform = 'none'; }
    });
  }

  /* ======================================================================
     9. Skeleton: показываем заглушки, пока грузятся изображения сетки
     ====================================================================== */
  function initSkeleton() {
    var images = document.querySelectorAll('.grid img[loading="lazy"], .gallery-stage img');
    Array.prototype.forEach.call(images, function (img) {
      if (img.complete && img.naturalWidth) return;
      var holder = document.createElement('div');
      holder.className = 'skeleton';
      holder.style.width = '100%';
      holder.style.aspectRatio = '4 / 3';
      holder.style.borderRadius = 'inherit';
      if (img.parentNode) img.parentNode.insertBefore(holder, img);
      img.style.opacity = '0';
      function done() {
        holder.remove();
        img.style.transition = 'opacity .45s var(--ease)';
        img.style.opacity = '1';
      }
      img.addEventListener('load', done, { once: true });
      img.addEventListener('error', done, { once: true });
    });
  }

  /* ======================================================================
     10. Счётчик корзины: анимированно «накручивается» и подпрыгивает
     ====================================================================== */
  function bumpCartBadge(count) {
    var badge = document.querySelector('.cart-count');
    var link = document.querySelector('[data-cart-open]');
    if (!badge && link) {
      badge = document.createElement('span');
      badge.className = 'cart-count';
      link.appendChild(badge);
    }
    if (!badge) return;

    var from = parseInt(badge.textContent, 10) || 0;
    var target = count === undefined ? from + 1 : count;
    badge.hidden = false;
    MT.tween({
      duration: 620,
      easing: 'easeOutBack',
      update: function (p) { badge.textContent = String(Math.round(from + (target - from) * p)); }
    });
    if (link) {
      link.classList.remove('cart-bounce');
      void link.offsetWidth;              // перезапуск анимации
      link.classList.add('cart-bounce');
    }
  }

  /* ======================================================================
     11. Оверлей затемнения — общий для drawer-панелей
     ====================================================================== */
  function setOverlay(open) {
    var overlay = document.querySelector('.drawer-backdrop');
    if (overlay) overlay.classList.toggle('is-open', open);
    document.body.style.overflow = open ? 'hidden' : '';
  }

  function initOverlay() {
    var overlay = document.querySelector('.drawer-backdrop');
    if (!overlay) return;
    overlay.addEventListener('click', function () {
      document.querySelectorAll('.drawer.is-open, .filters.is-open').forEach(function (el) {
        el.classList.remove('is-open');
      });
      setOverlay(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      document.querySelectorAll('.is-open').forEach(function (el) {
        if (el.classList.contains('drawer') || el.classList.contains('filters') ||
            el.classList.contains('modal-backdrop') || el.classList.contains('select') ||
            el.classList.contains('mega-menu')) {
          el.classList.remove('is-open');
        }
      });
      setOverlay(false);
    });
  }

  /* ======================================================================
     9b. Лоадер: стартовый экран (is-active ставится сразу в HTML, чтобы не
     мигать), плавно убирается после загрузки всех ресурсов
     ====================================================================== */
  function initLoader() {
    var loader = document.querySelector('.loader-overlay');
    if (!loader) return;
    function hide() {
      loader.classList.remove('is-active');
      setTimeout(function () { loader.remove(); }, 600);
    }
    if (document.readyState === 'complete') setTimeout(hide, 200);
    else window.addEventListener('load', function () { setTimeout(hide, 200); });
    setTimeout(hide, 3000);               // страховка: не держать дольше 3 с
  }

  /* ======================================================================
     10. Горячие клавиши витрины (Ctrl+Alt — без конфликтов с браузером)
     ====================================================================== */
  function initHotkeys() {
    var panel = document.getElementById('storeHotkeys');

    function typing() {
      var el = document.activeElement;
      if (!el) return false;
      var tag = el.tagName;
      return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
    }

    function comboOf(e) {
      var code = e.code || '';
      var base;
      if (/^Key[A-Z]$/.test(code)) base = code.slice(3).toLowerCase();
      else if (code === 'Slash') base = '/';
      else if (code === 'Escape') base = 'escape';
      else base = (e.key || '').toLowerCase();
      var mods = [];
      if (e.ctrlKey) mods.push('ctrl');
      if (e.metaKey) mods.push('meta');
      if (e.altKey) mods.push('alt');
      if (e.shiftKey) mods.push('shift');
      return mods.length ? mods.join('+') + '+' + base : base;
    }

    function focusSearch() {
      var input = document.querySelector('[data-store-search], .search input[type="search"]');
      if (!input) return;
      input.focus();
      if (typeof input.select === 'function') input.select();
    }

    function toggleThemeHotkey() {
      applyTheme(root.dataset.theme === 'dark' ? 'light' : 'dark', true);
    }

    function openHelp() {
      if (!panel) return;
      panel.hidden = false;
      document.body.classList.add('hk-open');
      var closeBtn = panel.querySelector('[data-hotkeys-close]');
      if (closeBtn) closeBtn.focus();
    }

    function closeHelp() {
      if (!panel || panel.hidden) return;
      panel.hidden = true;
      document.body.classList.remove('hk-open');
    }

    function isHelpOpen() {
      return panel && !panel.hidden;
    }

    document.addEventListener('click', function (e) {
      if (e.target.closest('[data-hotkeys-open]')) {
        e.preventDefault();
        openHelp();
        return;
      }
      if (e.target.closest('[data-hotkeys-close]')) {
        e.preventDefault();
        closeHelp();
        return;
      }
      if (isHelpOpen() && e.target === panel) closeHelp();
    });

    document.addEventListener('keydown', function (e) {
      if (e.isComposing) return;
      var combo = comboOf(e);

      if (combo === 'escape' && isHelpOpen()) {
        e.preventDefault();
        closeHelp();
        return;
      }

      if (combo === 'ctrl+alt+t') {
        e.preventDefault();
        e.stopPropagation();
        toggleThemeHotkey();
        return;
      }
      if (combo === 'ctrl+alt+k' || combo === 'ctrl+alt+/') {
        e.preventDefault();
        e.stopPropagation();
        focusSearch();
        return;
      }
      if (combo === 'ctrl+alt+h') {
        e.preventDefault();
        e.stopPropagation();
        if (isHelpOpen()) closeHelp(); else openHelp();
        return;
      }

      if (e.ctrlKey || e.metaKey || e.altKey || typing()) return;

      if (combo === '/' ) {
        e.preventDefault();
        focusSearch();
        return;
      }
      if (combo === 'shift+/') {
        e.preventDefault();
        if (isHelpOpen()) closeHelp(); else openHelp();
      }
    }, true);
  }

  /* ---------- инициализация ---------- */
  function boot() {
    initTheme();
    initLoader();
    initRipple();
    initHeader();
    initReveal();
    initOverlay();
    promoteDjangoMessages();
    initPageTransitions();
    initSkeleton();
    initHotkeys();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  // API для других скриптов страницы
  window.MTStore = {
    toast: toast,
    bumpCartBadge: bumpCartBadge,
    setOverlay: setOverlay,
    reveal: initReveal
  };
})();
