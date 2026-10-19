(function () {
<<<<<<< HEAD
  'use strict';
  const root = document.documentElement;
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

  // ---- тема: хранится на сервере в настройках пользователя
  document.getElementById('themeToggle')?.addEventListener('click', (e) => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    fetch(e.currentTarget.dataset.url, {
      method: 'POST', headers: { 'X-CSRFToken': csrf(), 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'theme=' + next,
    });
  });
=======
  const root = document.documentElement;
  const storedTheme = localStorage.getItem('magtech-theme');
  if (storedTheme) root.setAttribute('data-theme', storedTheme);

  document.getElementById('themeToggle')?.addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    localStorage.setItem('magtech-theme', next);
  });

>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
  document.getElementById('menuToggle')?.addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.toggle('open');
  });

<<<<<<< HEAD
  // ---- многостолбцовая сортировка: клик — сортировать по колонке, Shift+клик — добавить колонку
  document.querySelectorAll('.sort-link').forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const url = new URL(window.location.href);
      const key = link.dataset.sort;
      let keys = (url.searchParams.get('sort') || '').split(',').filter(Boolean);
      const idx = keys.findIndex((k) => k.replace('-', '') === key);
      const current = idx >= 0 ? keys[idx] : null;
      const toggled = current === key ? '-' + key : key;
      if (e.shiftKey) {
        if (idx >= 0) keys[idx] = toggled; else keys.push(key);
      } else {
        keys = [current ? toggled : key];
      }
      url.searchParams.set('sort', keys.join(','));
      url.searchParams.delete('page');
      window.location.href = url.toString();
    });
  });

  // ---- массовые операции: выбрать все, перенос id в форму
  document.querySelectorAll('[data-check-all]').forEach((box) => {
    box.addEventListener('change', () => {
      document.querySelectorAll('input.row-check').forEach((c) => { c.checked = box.checked; });
      updateBulk();
    });
  });
  function updateBulk() {
    const ids = [...document.querySelectorAll('input.row-check:checked')].map((c) => c.value);
    document.querySelectorAll('[data-bulk-ids]').forEach((input) => { input.value = ids.join(','); });
    document.querySelectorAll('[data-bulk-count]').forEach((el) => { el.textContent = ids.length; });
  }
  document.querySelectorAll('input.row-check').forEach((c) => c.addEventListener('change', updateBulk));
  updateBulk();

  document.querySelectorAll('form.bulk-bar').forEach((form) => {
    form.addEventListener('submit', (e) => {
      const ids = [...document.querySelectorAll('input.row-check:checked')].map((c) => c.value);
      if (!ids.length) { e.preventDefault(); window.alert('Выберите строки в таблице.'); return; }
      form.querySelectorAll('input.bulk-id').forEach((i) => i.remove());
      if (form.querySelector('[data-bulk-ids]')) { updateBulk(); return; }
      ids.forEach((id) => {
        const i = document.createElement('input');
        i.type = 'hidden'; i.name = 'ids'; i.value = id; i.className = 'bulk-id'; form.appendChild(i);
      });
    }, true);
  });

  // ---- подтверждение критических операций
  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (e) => {
      if (!e.defaultPrevented && !window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });

  // ---- командная строка Ctrl+K
  const palette = document.getElementById('palette');
  const input = document.getElementById('paletteInput');
  const list = document.getElementById('paletteResults');
  const commands = JSON.parse(document.getElementById('paletteCommands')?.textContent || '[]');
  let items = [], active = 0, timer;
  function render() {
    list.innerHTML = '';
    items.forEach((it, i) => {
      const li = document.createElement('li');
      li.className = i === active ? 'active' : '';
      const type = document.createElement('small'); type.textContent = it.type;
      const title = document.createElement('span'); title.textContent = it.title;
      li.append(type, title);
      li.addEventListener('click', () => { window.location.href = it.url; });
      list.appendChild(li);
    });
  }
  function openPalette() {
    if (!palette) return;
    palette.hidden = false; input.value = ''; items = commands.slice(0, 8); active = 0; render(); input.focus();
  }
  function closePalette() { if (palette) palette.hidden = true; }
  document.querySelectorAll('[data-open-palette]').forEach((b) => b.addEventListener('click', openPalette));
  palette?.addEventListener('click', (e) => { if (e.target === palette) closePalette(); });
  input?.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    const local = commands.filter((c) => c.title.toLowerCase().includes(q)).slice(0, 5);
    items = local; active = 0; render();
    clearTimeout(timer);
    if (q.length >= 2) {
      timer = setTimeout(() => {
        fetch(input.dataset.url + '?q=' + encodeURIComponent(q)).then((r) => r.json()).then((data) => {
          items = local.concat(data.results); render();
        });
      }, 180);
    }
  });
  input?.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { active = Math.min(active + 1, items.length - 1); render(); e.preventDefault(); }
    if (e.key === 'ArrowUp') { active = Math.max(active - 1, 0); render(); e.preventDefault(); }
    if (e.key === 'Enter' && items[active]) window.location.href = items[active].url;
    if (e.key === 'Escape') closePalette();
  });

  // ---- горячие клавиши (≥ 8): глобальные и контекстные через data-hotkey
  const typing = () => ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  function trigger(key) {
    const el = document.querySelector('[data-hotkey="' + key + '"]');
    if (!el) return false;
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) { el.focus(); el.scrollIntoView({ block: 'center' }); }
    else el.click();
    return true;
  }
  document.addEventListener('keydown', (e) => {
    if (document.body.dataset.hotkeys === 'off') return;
    const k = e.key.toLowerCase();
    const mod = e.ctrlKey || e.metaKey;
    if (mod && k === 'k') { e.preventDefault(); openPalette(); return; }
    if (mod && k === 'o') { e.preventDefault(); window.location.href = '/panel/orders/'; return; }
    if (mod && k === 'n') { e.preventDefault(); window.location.href = '/panel/products/new/'; return; }
    if (mod && k === 'e') {
      const checked = document.querySelector('input.row-check:checked[data-edit-url]');
      if (checked) { e.preventDefault(); window.location.href = checked.dataset.editUrl; return; }
      if (trigger('ctrl+e')) e.preventDefault();
      return;
    }
    if (mod || e.altKey || typing()) return;
    if (e.key === '/') { e.preventDefault(); const s = document.querySelector('[data-hotkey="/"]'); if (s) s.focus(); else openPalette(); return; }
    if (e.key === '?') { window.location.href = '/panel/help/hotkeys/'; return; }
    if (k === 's' && trigger('s')) { e.preventDefault(); return; }
    if (k === 'i') { if (!trigger('i')) window.location.href = '/panel/stock/receipt/'; return; }
    if (k === 'w' && trigger('w')) { e.preventDefault(); return; }
    if (k === 'p' && trigger('p')) { e.preventDefault(); return; }
    if (k === 'g') { window.location.href = '/panel/'; }
=======
  const searchInput = document.getElementById('searchInput');
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !e.ctrlKey && !e.metaKey && document.activeElement?.tagName !== 'INPUT') {
      e.preventDefault();
      searchInput?.focus();
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      searchInput?.focus();
    }
    if (e.key === '?' && !e.ctrlKey) {
      window.location.href = '/panel/help/hotkeys/';
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'o') {
      window.location.href = '/panel/orders/';
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
      window.location.href = '/panel/products/new/';
    }
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
  });
})();
