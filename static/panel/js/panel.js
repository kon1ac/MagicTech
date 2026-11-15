(function () {
  'use strict';
  const root = document.documentElement;
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

  // ---- тема: хранится на сервере в настройках пользователя (Bench / Studio)
  function paintThemeLabel(theme) {
    const label = theme === 'dark' ? 'Bench' : 'Studio';
    document.querySelectorAll('[data-theme-label]').forEach((el) => { el.textContent = label; });
    const btn = document.getElementById('themeToggle');
    if (btn) {
      btn.setAttribute('aria-label', 'Тема ' + label);
      btn.title = label;
    }
  }
  paintThemeLabel(root.getAttribute('data-theme') || 'light');
  document.getElementById('themeToggle')?.addEventListener('click', (e) => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.classList.add('theme-animating');
    root.setAttribute('data-theme', next);
    paintThemeLabel(next);
    window.setTimeout(() => root.classList.remove('theme-animating'), 220);
    fetch(e.currentTarget.dataset.url, {
      method: 'POST', headers: { 'X-CSRFToken': csrf(), 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'theme=' + next,
    });
  });
  document.getElementById('menuToggle')?.addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.toggle('open');
  });

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

  // ---- командная строка Ctrl+Alt+K
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

  // ---- Горячие клавиши.
  // Ctrl+T/N/… и Alt+T/E/… — браузер / меню. Alt+Shift — смена раскладки Windows.
  // Ctrl+Alt+буква свободно в Chrome/Edge/Opera/Firefox и в Simple Browser VS Code.
  // Резерв: лидер `\` + клавиша. Клавиша из e.code — и при русской раскладке.
  const typing = () => ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  function trigger(keys) {
    const list = Array.isArray(keys) ? keys : [keys];
    for (const key of list) {
      const el = document.querySelector('[data-hotkey="' + key + '"]');
      if (!el) continue;
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) { el.focus(); el.scrollIntoView({ block: 'center' }); }
      else el.click();
      return true;
    }
    return false;
  }
  const go = (url) => () => {
    if (!allowed(url)) { deny(url); return; }
    window.location.href = url;
  };

  let HOTKEY_GUARDS = [];
  try {
    const el = document.getElementById('hotkeyGuards');
    if (el) HOTKEY_GUARDS = JSON.parse(el.textContent) || [];
  } catch (e) { HOTKEY_GUARDS = []; }
  function allowed(url) {
    for (const [prefix, ok] of HOTKEY_GUARDS) {
      if (url.startsWith(prefix)) return ok;
    }
    return true;
  }
  function deny(url) {
    let box = document.getElementById('hotkeyToast');
    if (!box) {
      box = document.createElement('div');
      box.id = 'hotkeyToast';
      box.className = 'hotkey-toast';
      box.setAttribute('role', 'status');
      document.body.appendChild(box);
    }
    box.textContent = 'Недостаточно прав для: ' + url;
    box.classList.add('show');
    clearTimeout(deny._t);
    deny._t = setTimeout(() => box.classList.remove('show'), 2600);
  }

  function focusSearch() {
    const s = document.querySelector('[data-hotkey="/"]');
    if (s) { s.focus(); s.select(); } else openPalette();
  }
  const goReceipt = go('/panel/stock/receipt/');
  function editSelected() {
    const checked = document.querySelector('input.row-check:checked[data-edit-url]');
    if (checked) { go(checked.dataset.editUrl)(); return true; }
    return trigger(['ctrl+alt+e']);
  }
  function toggleTheme() { document.getElementById('themeToggle')?.click(); }

  // 'ctrl+alt+k', 's', 'shift+/'
  function comboOf(e) {
    const code = e.code || '';
    let base;
    if (/^Key[A-Z]$/.test(code)) base = code.slice(3).toLowerCase();
    else if (/^Digit\d$/.test(code)) base = code.slice(5);
    else if (code === 'Slash') base = '/';
    else if (code === 'Backquote') base = '`';
    else if (code === 'Backslash') base = '\\';
    else if (code === 'Space') base = 'space';
    else if (code === 'Escape') base = 'escape';
    else base = (e.key || '').toLowerCase();
    const mods = [];
    if (e.ctrlKey) mods.push('ctrl');
    if (e.metaKey) mods.push('meta');
    if (e.altKey) mods.push('alt');
    if (e.shiftKey) mods.push('shift');
    return mods.length ? mods.join('+') + '+' + base : base;
  }

  const GLOBAL = {
    'ctrl+alt+k': openPalette,
    'ctrl+alt+`': openPalette,
    'ctrl+alt+o': go('/panel/orders/'),
    'ctrl+alt+n': go('/panel/products/new/'),
    'ctrl+alt+g': go('/panel/'),
    'ctrl+alt+e': editSelected,
    'ctrl+alt+t': toggleTheme,
    'ctrl+alt+/': focusSearch,
    'ctrl+alt+h': go('/panel/help/hotkeys/'),
  };
  const SINGLE = {
    '/': focusSearch,
    'shift+/': go('/panel/help/hotkeys/'),
    'g': go('/panel/'),
    's': () => trigger('s'),
    'i': () => { if (!trigger('i')) goReceipt(); },
    'w': () => trigger('w'),
    'p': () => trigger('p'),
  };
  const CHORD = {
    'k': openPalette, 'o': go('/panel/orders/'), 'n': go('/panel/products/new/'),
    'e': editSelected, 'g': go('/panel/'), 't': toggleTheme, 's': () => trigger('s'),
    'i': () => { if (!trigger('i')) goReceipt(); },
    'w': () => trigger('w'), 'p': () => trigger('p'),
    '/': focusSearch, 'shift+/': go('/panel/help/hotkeys/'),
  };
  let chordPending = false, chordTimer;
  function showChordHint(on) {
    let el = document.getElementById('chordHint');
    if (!el && on) {
      el = document.createElement('div');
      el.id = 'chordHint';
      el.className = 'chord-hint';
      el.textContent = 'Ждём вторую клавишу… (k · o · n · e · g · t · s · i · w · p · / · ?)';
      document.body.appendChild(el);
      return;
    }
    if (el && !on) el.remove();
  }

  document.addEventListener('keydown', (e) => {
    if (document.body.dataset.hotkeys === 'off') return;
    if (e.isComposing) return;
    const combo = comboOf(e);

    if (chordPending) {
      let base = combo;
      if (base !== 'shift+/') base = combo.split('+').pop();
      if (base === '/') base = e.shiftKey ? 'shift+/' : '/';
      const action = CHORD[base] || (base === '?' ? CHORD['shift+/'] : null);
      chordPending = false; clearTimeout(chordTimer); showChordHint(false);
      if (action) { e.preventDefault(); e.stopPropagation(); action(); return; }
      if (base === 'escape') return;
    }

    if (combo === '\\' && !typing()) {
      e.preventDefault(); e.stopPropagation();
      chordPending = true; showChordHint(true);
      chordTimer = setTimeout(() => { chordPending = false; showChordHint(false); }, 1500);
      return;
    }

    const withMod = GLOBAL[combo];
    if (withMod) { e.preventDefault(); e.stopPropagation(); withMod(); return; }

    if (e.ctrlKey || e.metaKey || e.altKey || typing()) return;
    const single = SINGLE[combo];
    if (single) { e.preventDefault(); e.stopPropagation(); single(); }
  }, true);
})();
