/* ==========================================================================
   MagicTech Store — слой UI-интеракций (store-ui.js)
   Загружается ПОСЛЕ store.js и использует его ядро: MT.tween, MT.reduced,
   MTStore.toast / bumpCartBadge / setOverlay / reveal.
   Здесь: 3D-наклон карточек, fly-to-cart, drawer корзины, галерея с зумом,
   табы, мега-меню, live-фильтры, двойной ползунок цены, кастомный селект,
   липкий блок покупки, карусель баннеров, модалки, микроанимации.
   Открытие/закрытие панелей — через CSS-классы (.is-open/.is-on), анимацию
   делает store-fx.css; JS-твины остаются только там, где CSS не справляется
   (полёт товара в корзину, счётчик). Никаких внешних библиотек.
   ========================================================================== */
(function () {
  'use strict';

  var MT = window.MT;
  var UI = window.MTUI = {};
  if (!MT) return;                       // без ядра эффекты не имеют смысла

  function on(root, type, sel, handler) { // делегирование событий
    if (!root) return;
    root.addEventListener(type, function (e) {
      var el = e.target.closest(sel);
      if (el && root.contains(el)) handler(e, el);
    });
  }

  /* ======================================================================
     1. 3D-наклон карточек товара (.product-card) вслед за курсором
     Угол небольшой (6°), параллельно двигаем блик --gx/--gy, чтобы подсветка
     края (.product-card::after) шла за курсором. На тач-устройствах не
     активируется.
     ====================================================================== */
  function initTilt() {
    if (MT.reduced.matches || matchMedia('(hover: none)').matches) return;

    var MAX = 6;                          // максимальный угол наклона, градусы

    function move(e) {
      var card = e.currentTarget;
      var r = card.getBoundingClientRect();
      var px = (e.clientX - r.left) / r.width;
      var py = (e.clientY - r.top) / r.height;
      card.style.transform =
        'perspective(900px) rotateX(' + ((0.5 - py) * MAX).toFixed(2) + 'deg)' +
        ' rotateY(' + ((px - 0.5) * MAX).toFixed(2) + 'deg) translateY(-4px)';
      card.style.setProperty('--gx', (px * 100).toFixed(1) + '%');
      card.style.setProperty('--gy', (py * 100).toFixed(1) + '%');
    }

    function leave(e) {
      e.currentTarget.style.transform = '';
    }

    Array.prototype.forEach.call(document.querySelectorAll('.product-card'), function (card) {
      if (card.dataset.tiltOn) return;    // не навешивать дважды после live-фильтров
      card.dataset.tiltOn = '1';
      card.addEventListener('mousemove', move);
      card.addEventListener('mouseleave', leave);
    });
  }

  /* ======================================================================
     2. Fly-to-cart: картинка товара летит в иконку корзины
     Работает на любой форме добавления в корзину. Форма отправляется как
     обычно (Django без JS должен оставаться рабочим), а полёт и счётчик —
     только визуальный слой поверх.
     ====================================================================== */
  function initFlyToCart() {
    var cartTarget = document.querySelector('[data-cart-target]');

    on(document, 'submit', 'form[data-cart-add]', function (e, form) {
      if (MT.reduced.matches || form.dataset.pending) return;
      var card = form.closest('.product-card') || form;
      var img = card.querySelector('img');
      if (!img || !cartTarget) return;

      e.preventDefault();                 // задерживаем отправку на время полёта
      form.dataset.pending = '1';
      fly(img, cartTarget, function () { form.submit(); });
      setTimeout(function () { if (form.dataset.pending) form.submit(); }, 1200);
    });

    function fly(img, target, done) {
      var from = img.getBoundingClientRect();
      var to = target.getBoundingClientRect();

      var ghost = img.cloneNode(true);
      ghost.className = 'fly-ghost';
      ghost.style.left = from.left + 'px';
      ghost.style.top = from.top + 'px';
      ghost.style.width = from.width + 'px';
      ghost.style.height = from.height + 'px';
      document.body.appendChild(ghost);

      var dx = (to.left + to.width / 2) - (from.left + from.width / 2);
      var dy = (to.top + to.height / 2) - (from.top + from.height / 2);

      MT.tween({
        duration: 720,
        easing: 'easeInOutCubic',
        update: function (p) {
          // траектория — дуга: по x линейно, по y с подъёмом вверх
          var lift = -120 * Math.sin(Math.PI * p);
          ghost.style.transform =
            'translate(' + (dx * p) + 'px,' + (dy * p + lift) + 'px) scale(' + (1 - 0.8 * p) + ')';
          ghost.style.opacity = String(1 - 0.35 * p);
        },
        complete: function () {
          ghost.remove();
          done();
        }
      });
    }
  }

  /* ======================================================================
     3. Drawer корзины — выезжающая панель (.drawer, CSS-анимация через
     класс .is-open). Содержимое дотягивается с сервера (?drawer=1 → partial
     корзины) и обновляется после любого изменения количества.
     ====================================================================== */
  var drawer = {
    el: null,
    body: null,

    init: function () {
      var self = this;
      this.el = document.querySelector('.drawer[data-drawer="cart"]');
      if (!this.el) return;
      this.body = this.el.querySelector('.drawer-body');

      on(document, 'click', '[data-cart-open]', function (e) {
        e.preventDefault();
        self.show();
      });
      on(this.el, 'click', '[data-close]', function () { self.hide(); });

      // клик по «В корзину» на витрине: после перезагрузки показываем drawer
      if (/([?&])added=1/.test(location.search)) {
        history.replaceState(null, '', location.pathname);
        setTimeout(function () { self.show(); }, 450);
      }
    },

    isOpen: function () {
      return this.el.classList.contains('is-open');
    },

    show: function () {
      this.el.classList.add('is-open');
      MTStore.setOverlay(true);
      this.load();
    },

    hide: function () {
      this.el.classList.remove('is-open');
      MTStore.setOverlay(false);
    },

    load: function () {
      var self = this;
      // partial отдаёт cart_view по параметру ?drawer=1
      fetch('/cart/?drawer=1', { headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          self.body.innerHTML = html;
        })
        .catch(function () {
          self.body.innerHTML = '<p class="empty">Не удалось загрузить корзину.</p>';
        });
    }
  };

  // изменение количества / удаление внутри drawer — без перезагрузки страницы
  on(document, 'submit', '.drawer form[data-qty]', function (e, form) {
    e.preventDefault();
    var btn = form.querySelector('button[type=submit]');
    if (btn) btn.disabled = true;
    fetch(form.action, {
      method: 'POST',
      body: new FormData(form),
      headers: { 'X-CSRFToken': UI.csrf(), 'X-Requested-With': 'fetch' }
    })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        drawer.body.innerHTML = html;
        UI.refreshBadge();
      })
      .catch(function () { MTStore.toast('Ошибка обновления корзины', 'error'); })
      .finally(function () { if (btn) btn.disabled = false; });
  });

  /* ======================================================================
     4. Обновление счётчика корзины из drawer
     ====================================================================== */
  UI.csrf = function () {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? m[1] : '';
  };

  UI.refreshBadge = function () {
    fetch('/cart/?drawer=1', { headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var count = doc.querySelector('[data-cart-count]');
        if (count) MTStore.bumpCartBadge(parseInt(count.dataset.cartCount, 10) || 0);
      })
      .catch(function () {});
  };

  /* ======================================================================
     5. Галерея товара с зумом по курсору
     Кадры — несколько <img> внутри .gallery-stage, активный — .is-active
     (остальные спрятаны CSS). Клик по сцене — зум (transform-origin следует
     за мышью), миниатюры и стрелки листают.
     ====================================================================== */
  function bindSwipe(el, onLeft, onRight, opts) {
    opts = opts || {};
    var startX = 0, startY = 0, dx = 0, dy = 0, active = false, dragged = false;
    var threshold = opts.threshold || 40;

    function point(e) {
      if (e.touches && e.touches[0]) return e.touches[0];
      if (e.changedTouches && e.changedTouches[0]) return e.changedTouches[0];
      return e;
    }

    el.addEventListener('pointerdown', function (e) {
      if (e.button != null && e.button !== 0) return;
      if (opts.ignore && e.target.closest(opts.ignore)) return;
      active = true;
      dragged = false;
      dx = dy = 0;
      var p = point(e);
      startX = p.clientX;
      startY = p.clientY;
      // иначе браузер уводит на ссылку / native-drag вместо свайпа
      e.preventDefault();
      try { el.setPointerCapture(e.pointerId); } catch (err) {}
      if (opts.onStart) opts.onStart();
    });
    el.addEventListener('pointermove', function (e) {
      if (!active) return;
      var p = point(e);
      dx = p.clientX - startX;
      dy = p.clientY - startY;
      if (Math.abs(dx) > 8 || Math.abs(dy) > 8) dragged = true;
      if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 6) e.preventDefault();
      if (opts.onMove) opts.onMove(dx, dy);
    });
    function end(e) {
      if (!active) return;
      active = false;
      try { el.releasePointerCapture(e.pointerId); } catch (err) {}
      if (opts.onEnd) opts.onEnd(dx, dy, dragged);
      if (Math.abs(dx) >= threshold && Math.abs(dx) > Math.abs(dy)) {
        if (dx < 0) onLeft();
        else onRight();
      }
    }
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
    // клик по слайду после драга не открывает товар
    el.addEventListener('click', function (e) {
      if (dragged) {
        e.preventDefault();
        e.stopPropagation();
        dragged = false;
      }
    }, true);
    return function wasDragged() { return dragged; };
  }

  function initGallery() {
    var root = document.querySelector('[data-gallery]');
    if (!root) return;
    var stage = root.querySelector('.gallery-stage');
    if (!stage) return;
    var imgs = Array.prototype.slice.call(stage.querySelectorAll('img'));
    var thumbs = Array.prototype.slice.call(root.querySelectorAll('.gallery-thumbs button'));
    if (!imgs.length) return;

    function select(n) {
      n = (n + imgs.length) % imgs.length;
      imgs.forEach(function (im, i) { im.classList.toggle('is-active', i === n); });
      thumbs.forEach(function (t, i) { t.classList.toggle('is-active', i === n); });
      stage.classList.remove('is-zoomed');
      return n;
    }

    var current = Math.max(0, imgs.findIndex(function (im) { return im.classList.contains('is-active'); }));
    if (!imgs[current].classList.contains('is-active')) select(current);

    thumbs.forEach(function (t, i) {
      t.addEventListener('click', function () { current = select(i); });
    });
    on(root, 'click', '.gallery-nav.prev', function (e) {
      e.preventDefault(); current = select(current - 1);
    });
    on(root, 'click', '.gallery-nav.next', function (e) {
      e.preventDefault(); current = select(current + 1);
    });

    var swipeDragged = bindSwipe(
      stage,
      function () { current = select(current + 1); },
      function () { current = select(current - 1); },
      { ignore: '.gallery-nav', threshold: 45 }
    );

    // зум: CSS масштабирует img.is-active, мы только ведём точку зума
    stage.addEventListener('click', function (e) {
      if (e.target.closest('.gallery-nav')) return;
      if (swipeDragged()) return;
      stage.classList.toggle('is-zoomed');
    });
    stage.addEventListener('mousemove', function (e) {
      if (!stage.classList.contains('is-zoomed')) return;
      var r = stage.getBoundingClientRect();
      imgs[current].style.transformOrigin =
        (((e.clientX - r.left) / r.width) * 100) + '% ' +
        (((e.clientY - r.top) / r.height) * 100) + '%';
    });
  }

  function initCardGalleries() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-card-gallery]'), function (root) {
      if (root.dataset.galleryReady) return;
      var slides = Array.prototype.slice.call(root.querySelectorAll('.card-gallery-slide'));
      var dots = Array.prototype.slice.call(root.querySelectorAll('.card-gallery-dot'));
      var stage = root.querySelector('.card-gallery-stage');
      if (slides.length < 2 || !stage) return;
      root.dataset.galleryReady = '1';

      var current = Math.max(0, slides.findIndex(function (s) { return s.classList.contains('is-active'); }));

      var idxEl = root.querySelector('[data-card-gallery-idx]');
      function select(n) {
        n = (n + slides.length) % slides.length;
        slides.forEach(function (s, i) {
          var on = i === n;
          s.classList.toggle('is-active', on);
          s.setAttribute('aria-hidden', on ? 'false' : 'true');
          s.tabIndex = on ? 0 : -1;
        });
        dots.forEach(function (d, i) { d.classList.toggle('is-active', i === n); });
        if (idxEl) idxEl.textContent = String(n + 1);
        current = n;
        return n;
      }
      if (!slides[current].classList.contains('is-active')) select(current);

      var prev = root.querySelector('.card-gallery-nav.prev');
      var next = root.querySelector('.card-gallery-nav.next');
      if (prev) prev.addEventListener('click', function (e) {
        e.preventDefault(); e.stopPropagation(); select(current - 1);
      });
      if (next) next.addEventListener('click', function (e) {
        e.preventDefault(); e.stopPropagation(); select(current + 1);
      });

      var swipeDragged = bindSwipe(
        stage,
        function () { select(current + 1); },
        function () { select(current - 1); },
        {
          threshold: 36,
          ignore: '.card-gallery-nav',
          onStart: function () { root.classList.add('is-dragging'); },
          onEnd: function () { root.classList.remove('is-dragging'); }
        }
      );

      // слайды без pointer-events — клик по фото открывает товар (если не было свайпа)
      stage.addEventListener('click', function (e) {
        if (e.target.closest('.card-gallery-nav')) return;
        if (swipeDragged()) {
          e.preventDefault();
          e.stopPropagation();
          return;
        }
        var link = slides[current];
        if (link && link.href) window.location.href = link.href;
      });
    });
  }

  /* ======================================================================
     6. Табы товара: описание / характеристики / отзывы
     Показывает .tab-panel.is-active; hash обновляем, чтобы таб можно было
     продвинуть с вьюхи (#reviews).
     ====================================================================== */
  function initTabs() {
    var root = document.querySelector('[data-tabs]');
    if (!root) return;

    function activate(id) {
      var found = false;
      Array.prototype.forEach.call(root.querySelectorAll('[data-tab]'), function (t) {
        var on = t.dataset.tab === id;
        t.classList.toggle('is-active', on);
        if (on) found = true;
      });
      if (!found) return;
      Array.prototype.forEach.call(root.querySelectorAll('[data-panel]'), function (p) {
        p.classList.toggle('is-active', p.dataset.panel === id);
      });
    }

    on(root, 'click', '[data-tab]', function (e, t) {
      e.preventDefault();
      activate(t.dataset.tab);
      history.replaceState(null, '', '#' + t.dataset.tab);
    });

    var initial = (location.hash || '').slice(1);
    if (initial) activate(initial);
  }

  /* ======================================================================
     7. Мега-меню каталога
     На десктопе CSS открывает его по :hover; для тач-устройств и клавиатуры
     вешаем .is-open на .nav-item по клику по ссылке-триггеру.
     ====================================================================== */
  function initMegaMenu() {
    var items = Array.prototype.slice.call(document.querySelectorAll('.nav-item:has(.mega-menu)'));
    items.forEach(function (item) {
      var trigger = item.querySelector('[data-mega-trigger]');
      if (!trigger) return;
      trigger.addEventListener('click', function (e) {
        // на hover-устройствах меню и так открыто — ведём себя как обычная ссылка
        if (matchMedia('(hover: hover)').matches) return;
        e.preventDefault();
        var was = item.classList.contains('is-open');
        items.forEach(function (i) { i.classList.remove('is-open'); });
        if (!was) item.classList.add('is-open');
      });
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') items.forEach(function (i) { i.classList.remove('is-open'); });
    });
    document.addEventListener('click', function (e) {
      items.forEach(function (i) {
        if (i.classList.contains('is-open') && !i.contains(e.target)) i.classList.remove('is-open');
      });
    });
  }

  /* ======================================================================
     8. Live-фильтры каталога
     Любое изменение в форме фильтров перезапрашивает только сетку товаров:
     на время запроса ставим skeleton, затем подменяем HTML. Без перезагрузки
     страницы, но с сохранением URL (history.pushState), чтобы фильтры можно
     было скопировать или вернуть кнопкой «назад».
     ====================================================================== */
  var filters = {
    init: function () {
      this.form = document.querySelector('[data-filter-form]');
      this.grid = document.querySelector('[data-catalog-grid]');
      if (!this.form || !this.grid) return;
      this.timer = null;
      // селект сортировки лежит в тулбаре, вне формы — слушаем его отдельно
      this.sortSel = document.querySelector('[data-sort-select] select');

      var self = this;
      this.form.addEventListener('change', function () { self.schedule(); });
      this.form.addEventListener('input', function (e) {
        // для текстовых полей и ползунков — с дебаунсом
        if (e.target.matches('input[type=text], input[type=search], input[type=number], input[type=range]')) {
          self.schedule(420);
        }
      });
      this.form.addEventListener('submit', function (e) { e.preventDefault(); self.apply(); });
      if (this.sortSel) this.sortSel.addEventListener('change', function () { self.schedule(); });

      // кнопки пагинации внутри каталога тоже идут через live-запрос
      on(document, 'click', '[data-catalog-pager] a', function (e, a) {
        e.preventDefault();
        self.apply(a.href);
      });

      // чипы сброса фильтра — тоже live, URL уже «шарится» через pushState
      on(document, 'click', '[data-active-filters] a', function (e, a) {
        e.preventDefault();
        self.apply(a.href);
      });

      // история: «назад» должен вернуть предыдущий набор фильтров
      window.addEventListener('popstate', function () { self.apply(location.href, true); });

      this.bindRange();
      this.bindDrawerToggle();
    },

    schedule: function (ms) {
      var self = this;
      clearTimeout(this.timer);
      this.timer = setTimeout(function () { self.apply(); }, ms || 220);
    },

    url: function (href) {
      if (href) return href;
      var params = new URLSearchParams(new FormData(this.form));
      if (this.sortSel) params.set('sort', this.sortSel.value);   // селект вне формы
      // пустые значения и служебные поля не тащим в URL
      Array.prototype.forEach.call(Array.prototype.slice.call(params.keys()), function (k) {
        if (!params.get(k)) params.delete(k);
      });
      params.delete('page');
      var qs = params.toString();
      return location.pathname + (qs ? '?' + qs : '');
    },

    apply: function (href, silent) {
      var self = this;
      var target = this.url(href);
      UI.skeleton(this.grid, 6);

      fetch(target, { headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          var doc = new DOMParser().parseFromString(html, 'text/html');
          var next = doc.querySelector('[data-catalog-grid]');
          var pager = doc.querySelector('[data-catalog-pager]');
          var count = doc.querySelector('[data-result-count]');
          var chips = doc.querySelector('[data-active-filters]');
          var formNext = doc.querySelector('[data-filter-form]');

          UI.skeleton(self.grid, 0);
          if (next) {
            self.grid.innerHTML = next.innerHTML;
            initTilt();
            MTStore.reveal();
          }
          var livePager = document.querySelector('[data-catalog-pager]');
          if (livePager && pager) livePager.innerHTML = pager.innerHTML;
          else if (livePager && !pager) livePager.innerHTML = '';
          var cnt = document.querySelector('[data-result-count]');
          if (cnt && count) cnt.textContent = count.textContent;

          var liveChips = document.querySelector('[data-active-filters]');
          if (liveChips && chips) {
            liveChips.innerHTML = chips.innerHTML;
            liveChips.hidden = chips.hidden || !chips.innerHTML.trim();
          }

          // синхронизируем чекбоксы формы с URL (после чипа / назад)
          if (formNext && self.form) {
            Array.prototype.forEach.call(self.form.querySelectorAll('input[type=checkbox]'), function (inp) {
              var name = inp.name, val = inp.value;
              var match = false;
              Array.prototype.forEach.call(formNext.querySelectorAll('input[type=checkbox]'), function (src) {
                if (src.name === name && src.value === val) match = src.checked;
              });
              inp.checked = match;
            });
            ['price_min', 'price_max'].forEach(function (name) {
              var a = self.form.querySelector('input[name="' + name + '"]');
              var b = formNext.querySelector('input[name="' + name + '"]');
              if (a && b) a.value = b.value;
            });
          }

          if (!silent) history.pushState({}, '', target);
          document.dispatchEvent(new CustomEvent('mt:catalog-updated'));
        })
        .catch(function () {
          UI.skeleton(self.grid, 0);
          MTStore.toast('Фильтры не обновились', 'error');
        });
    },

    /* Двойной ползунок цены: два нативных input[type=range], наложенных друг
       на друга (.range-dual). Рядом лежат текстовые поля .price-range — в них
       пишет Django-форма; ползунки синхронизированы с ними, поэтому без JS
       фильтры работают через обычные поля min/max. */
    bindRange: function () {
      var dual = document.querySelector('[data-price-range]');
      if (!dual) return;
      var lo = dual.querySelector('[data-range-min]');
      var hi = dual.querySelector('[data-range-max]');
      var fill = dual.querySelector('.fill');
      if (!lo || !hi) return;
      var fieldLo = document.querySelector('input[name="price_min"]');
      var fieldHi = document.querySelector('input[name="price_max"]');

      function paint() {
        var a = parseFloat(lo.value), b = parseFloat(hi.value);
        if (a > b) { var t = a; a = b; b = t; }
        var min = parseFloat(lo.min), max = parseFloat(lo.max);
        var span = (max - min) || 1;
        if (fill) {
          fill.style.left = (((a - min) / span) * 100) + '%';
          fill.style.width = (((b - a) / span) * 100) + '%';
        }
        if (fieldLo) fieldLo.value = String(a);
        if (fieldHi) fieldHi.value = String(b);
      }

      // ползунок не должен перескакивать через соседний
      lo.addEventListener('input', function () {
        if (parseFloat(lo.value) > parseFloat(hi.value)) lo.value = hi.value;
        paint();
      });
      hi.addEventListener('input', function () {
        if (parseFloat(hi.value) < parseFloat(lo.value)) hi.value = lo.value;
        paint();
      });

      // стартовые значения — из полей формы (учитывает уже применённый фильтр)
      if (fieldLo && fieldLo.value) lo.value = fieldLo.value;
      if (fieldHi && fieldHi.value) hi.value = fieldHi.value;
      paint();
      // при live-обновлении сетки поля forms не пересобираются — синхронизируем
      document.addEventListener('mt:catalog-updated', function () {
        if (fieldLo && fieldLo.value) lo.value = fieldLo.value;
        if (fieldHi && fieldHi.value) hi.value = fieldHi.value;
        paint();
      });
    },

    /* Выезжающая панель фильтров на мобильном: CSS прячет .filters за экраном
       (transform), класс .is-open возвращает её; затемнение — общий оверлей. */
    bindDrawerToggle: function () {
      var aside = document.querySelector('.filters[data-filters-panel]');
      if (!aside) return;
      on(document, 'click', '[data-open-filters]', function (e) {
        e.preventDefault();
        aside.classList.add('is-open');
        MTStore.setOverlay(true);
      });
      on(aside, 'click', '[data-close]', function () {
        aside.classList.remove('is-open');
        MTStore.setOverlay(false);
      });
    }
  };

  /* Кастомная сортировка (.select): за кнопкой прячем нативный select,
     значение пишет в него — форма остаётся валидной для Django.
     Открытие — класс .select.is-open (показ списка делает CSS). */
  function initCustomSelects() {
    Array.prototype.forEach.call(document.querySelectorAll('.select[data-sort-select]'), function (root) {
      var native = root.querySelector('select');
      var button = root.querySelector('.select-btn');
      var listbox = root.querySelector('.select-list');
      if (!native || !button || !listbox) return;
      var value = button.querySelector('.select-value');

      function paint() {
        if (value) value.textContent = native.options[native.selectedIndex]
          ? native.options[native.selectedIndex].textContent : '';
        Array.prototype.forEach.call(listbox.children, function (li) {
          li.classList.toggle('is-active', li.dataset.value === native.value);
        });
      }

      button.addEventListener('click', function () {
        var open = root.classList.toggle('is-open');
        button.setAttribute('aria-expanded', String(open));
      });

      on(listbox, 'click', '[data-value]', function (e, li) {
        e.preventDefault();
        native.value = li.dataset.value;
        paint();
        root.classList.remove('is-open');
        button.setAttribute('aria-expanded', 'false');
        native.dispatchEvent(new Event('change', { bubbles: true })); // live-фильтры подхватят
      });

      document.addEventListener('click', function (e) {
        if (root.classList.contains('is-open') && !root.contains(e.target)) {
          root.classList.remove('is-open');
          button.setAttribute('aria-expanded', 'false');
        }
      });

      paint();
    });
  }

  /* ======================================================================
     9. Skeleton-заглушка: временно добавляем в сетку карточки-мигалки
     (.skeleton-card из store-fx.css), помечая их data-sk — они удаляются
     при следующем вызове с count = 0.
     ====================================================================== */
  UI.skeleton = function (container, count) {
    if (!container) return;
    if (!count) {
      Array.prototype.forEach.call(container.querySelectorAll('[data-sk]'), function (el) {
        el.remove();
      });
      return;
    }
    var html = '';
    for (var i = 0; i < count; i++) {
      html += '<div class="skeleton-card" data-sk>' +
        '<div class="skeleton skeleton-block"></div>' +
        '<div class="skeleton skeleton-text" style="width:80%"></div>' +
        '<div class="skeleton skeleton-text" style="width:45%"></div>' +
        '<div class="skeleton skeleton-text" style="width:30%"></div>' +
        '</div>';
    }
    container.insertAdjacentHTML('beforeend', html);
  };

  /* ======================================================================
     10. Липкий блок «купить» на странице товара (.sticky-buy).
     Когда основной buybox уходит за верх экрана — снизу выезжает узкая
     панель с ценой и кнопкой (CSS-анимация по классу .is-on).
     ====================================================================== */
  function initStickyBuy() {
    var source = document.querySelector('[data-buy-block]');
    var bar = document.querySelector('.sticky-buy');
    if (!source || !bar) return;

    var observer = new IntersectionObserver(function (entries) {
      var gone = !entries[0].isIntersecting && entries[0].boundingClientRect.top < 0;
      bar.classList.toggle('is-on', gone);
    }, { threshold: 0 });
    observer.observe(source);
  }

  /* ======================================================================
     11. Карусель баннеров (.carousel > .carousel-track > .carousel-slide)
     Автопрокрутка, свайп, точки (.carousel-dot), пауза при наведении.
     Сдвиг трека — CSS-transition, JS только ставит translateX.
     ====================================================================== */
  function initCarousel() {
    var root = document.querySelector('[data-carousel]');
    if (!root) return;
    var track = root.querySelector('.carousel-track');
    var slides = track ? Array.prototype.slice.call(track.children) : [];
    if (slides.length < 2) return;

    var dotsBox = root.querySelector('.carousel-indicators');
    if (!dotsBox) {
      dotsBox = document.createElement('div');
      dotsBox.className = 'carousel-indicators';
      root.appendChild(dotsBox);
    }
    slides.forEach(function (s, i) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'carousel-dot' + (i === 0 ? ' is-active' : '');
      b.setAttribute('aria-label', 'Слайд ' + (i + 1));
      b.addEventListener('click', function () { go(i, true); });
      dotsBox.appendChild(b);
    });

    var index = 0;
    var timer = null;
    var DELAY = 6000;

    function go(n, manual) {
      index = (n + slides.length) % slides.length;
      track.style.transform = 'translateX(-' + (index * 100) + '%)';
      Array.prototype.forEach.call(dotsBox.children, function (d, i) {
        d.classList.toggle('is-active', i === index);
      });
      if (manual) restart();
    }

    function restart() {
      clearInterval(timer);
      if (!MT.reduced.matches) timer = setInterval(function () { go(index + 1); }, DELAY);
    }

    // свайп на тач-экранах
    var startX = null;
    root.addEventListener('touchstart', function (e) { startX = e.touches[0].clientX; }, { passive: true });
    root.addEventListener('touchend', function (e) {
      if (startX === null) return;
      var dx = e.changedTouches[0].clientX - startX;
      if (Math.abs(dx) > 45) go(index + (dx < 0 ? 1 : -1), true);
      startX = null;
    });

    root.addEventListener('mouseenter', function () { clearInterval(timer); });
    root.addEventListener('mouseleave', restart);

    // автопрокрутку не крутим, когда вкладки не видно
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) clearInterval(timer); else restart();
    });

    restart();
  }

  /* ======================================================================
     12. Модалки: .modal-backdrop[id] c .modal внутри.
     Открытие — класс .is-open (CSS делает fade + blur + scale), закрытие —
     кнопка [data-modal-close], клик по подложке или Escape.
     ====================================================================== */
  function initModals() {
    function close(backdrop) {
      backdrop.classList.remove('is-open');
      document.body.style.overflow = '';
    }

    on(document, 'click', '[data-modal-open]', function (e, btn) {
      e.preventDefault();
      var backdrop = document.getElementById(btn.dataset.modalOpen);
      if (!backdrop) return;
      backdrop.classList.add('is-open');
      document.body.style.overflow = 'hidden';
    });

    on(document, 'click', '[data-modal-close]', function (e, btn) {
      var backdrop = btn.closest('.modal-backdrop');
      if (backdrop) close(backdrop);
    });

    // клик по самой подложке (мимо окна)
    on(document, 'click', '.modal-backdrop', function (e, backdrop) {
      if (e.target === backdrop) close(backdrop);
    });

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      var open = document.querySelector('.modal-backdrop.is-open');
      if (open) close(open);
    });
  }

  /* ======================================================================
     13. Микроанимации: сердце «бьётся» (CSS @keyframes heart-beat в
     store.css), класс навешиваем заново при каждом клике.
     ====================================================================== */
  function initMicroFx() {
    on(document, 'click', '[data-beat]', function (e, el) {
      el.classList.remove('heart-beat');
      void el.offsetWidth;                  // сброс анимации
      el.classList.add('heart-beat');
    });
  }

  /* ======================================================================
     14. Счётчик количества (.qty): кнопки −/+ рядом с полем ввода.
     Значение всегда остаётся валидным для формы — Django работает и без JS.
     ====================================================================== */
  function initQty() {
    on(document, 'click', '.qty button', function (e, btn) {
      e.preventDefault();
      var input = btn.parentNode.querySelector('input');
      if (!input) return;
      var step = btn.dataset.step === '+' ? 1 : -1;
      var min = parseInt(input.min, 10) || 1;
      var max = parseInt(input.max, 10) || 999;
      var value = (parseInt(input.value, 10) || min) + step;
      input.value = String(Math.min(max, Math.max(min, value)));
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  }

  /* ======================================================================
     15. Живой поиск с подсказками (SKU / бренд / опечатки)
     ====================================================================== */
  function initSearchSuggest() {
    var form = document.querySelector('[data-search-form]');
    var input = document.querySelector('[data-search-input]');
    var box = document.querySelector('[data-search-suggest]');
    if (!form || !input || !box) return;

    var timer = null;
    var active = -1;
    var items = [];

    function hide() {
      box.hidden = true;
      box.innerHTML = '';
      active = -1;
      items = [];
      input.setAttribute('aria-expanded', 'false');
    }

    function show(html) {
      box.innerHTML = html;
      box.hidden = !html;
      items = Array.prototype.slice.call(box.querySelectorAll('[data-sg-item]'));
      active = -1;
      input.setAttribute('aria-expanded', html ? 'true' : 'false');
    }

    function mark(i) {
      items.forEach(function (el, idx) { el.classList.toggle('is-active', idx === i); });
      active = i;
      if (items[i]) items[i].scrollIntoView({ block: 'nearest' });
    }

    function render(data) {
      var html = '';
      if (data.did_you_mean) {
        html += '<div class="sg-hint">Возможно, вы имели в виду: '
          + '<a href="/?q=' + encodeURIComponent(data.did_you_mean) + '" data-sg-item>'
          + escapeHtml(data.did_you_mean) + '</a></div>';
      }
      if (data.brands && data.brands.length) {
        html += '<div class="search-suggest-group">Бренды</div>';
        data.brands.forEach(function (b) {
          html += '<a class="sg-brand" href="' + escapeAttr(b.url) + '" data-sg-item role="option">'
            + '<span class="sg-name">' + escapeHtml(b.name) + '</span></a>';
        });
      }
      if (data.products && data.products.length) {
        html += '<div class="search-suggest-group">Товары</div>';
        data.products.forEach(function (p) {
          var price = p.price != null
            ? (Math.round(p.price).toLocaleString('ru-RU') + ' ₽') : '';
          html += '<a href="' + escapeAttr(p.url) + '" data-sg-item role="option">'
            + (p.image ? '<img src="' + escapeAttr(p.image) + '" alt="">' : '<span></span>')
            + '<span><div class="sg-name">' + escapeHtml(p.name) + '</div>'
            + '<div class="sg-meta">' + escapeHtml(p.brand || p.sku) + '</div></span>'
            + '<span class="sg-price">' + escapeHtml(price) + '</span></a>';
        });
      }
      if (!html) {
        html = '<div class="sg-empty">Ничего не найдено по «' + escapeHtml(data.q || '') + '»</div>';
      }
      show(html);
    }

    function escapeHtml(s) {
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }
    function escapeAttr(s) { return escapeHtml(s).replace(/'/g, '&#39;'); }

    function fetchSuggest(q) {
      if (!q || q.length < 1) { hide(); return; }
      fetch('/search/suggest/?q=' + encodeURIComponent(q), {
        headers: { 'X-Requested-With': 'fetch', 'Accept': 'application/json' }
      })
        .then(function (r) { return r.json(); })
        .then(render)
        .catch(function () { hide(); });
    }

    input.addEventListener('input', function () {
      clearTimeout(timer);
      var q = input.value.trim();
      timer = setTimeout(function () { fetchSuggest(q); }, 180);
    });
    input.addEventListener('focus', function () {
      if (input.value.trim()) fetchSuggest(input.value.trim());
    });
    input.addEventListener('keydown', function (e) {
      if (box.hidden || !items.length) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        mark(active < items.length - 1 ? active + 1 : 0);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        mark(active > 0 ? active - 1 : items.length - 1);
      } else if (e.key === 'Enter' && active >= 0 && items[active]) {
        e.preventDefault();
        window.location.href = items[active].href;
      } else if (e.key === 'Escape') {
        hide();
      }
    });
    document.addEventListener('click', function (e) {
      if (!form.contains(e.target)) hide();
    });
  }

  /* ======================================================================
     16. boot
     ====================================================================== */
  function boot() {
    initTilt();
    initFlyToCart();
    drawer.init();
    initGallery();
    initCardGalleries();
    initTabs();
    initMegaMenu();
    initCustomSelects();
    filters.init();
    initStickyBuy();
    initCarousel();
    initModals();
    initMicroFx();
    initQty();
    initSearchSuggest();
    document.addEventListener('mt:catalog-updated', function () {
      initCardGalleries();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
