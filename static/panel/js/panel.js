(function () {
  const root = document.documentElement;
  const storedTheme = localStorage.getItem('magtech-theme');
  if (storedTheme) root.setAttribute('data-theme', storedTheme);

  document.getElementById('themeToggle')?.addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    localStorage.setItem('magtech-theme', next);
  });

  document.getElementById('menuToggle')?.addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.toggle('open');
  });

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
  });
})();
