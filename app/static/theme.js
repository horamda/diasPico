(function () {
  const KEY = 'dpo_theme';
  const root = document.documentElement;

  function systemTheme() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark';
  }

  function currentTheme() {
    const saved = localStorage.getItem(KEY);
    return saved === 'light' || saved === 'dark' ? saved : systemTheme();
  }

  function label(theme) {
    return theme === 'light'
      ? { icon: '☀', text: 'Claro', title: 'Cambiar a modo oscuro' }
      : { icon: '☾', text: 'Oscuro', title: 'Cambiar a modo claro' };
  }

  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
    root.style.colorScheme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'light' ? '#eef3f8' : '#0b0d12');
    const btn = document.getElementById('themeToggle');
    if (btn) {
      const data = label(theme);
      btn.title = data.title;
      btn.setAttribute('aria-label', data.title);
      btn.innerHTML = `<span class="theme-icon" aria-hidden="true">${data.icon}</span><span>${data.text}</span>`;
    }
  }

  function toggleTheme() {
    const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    localStorage.setItem(KEY, next);
    applyTheme(next);
  }

  applyTheme(currentTheme());

  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('themeToggle')) return;
    const btn = document.createElement('button');
    btn.id = 'themeToggle';
    btn.type = 'button';
    btn.className = 'theme-toggle';
    btn.addEventListener('click', toggleTheme);
    document.body.appendChild(btn);
    applyTheme(root.getAttribute('data-theme') || currentTheme());
  });
})();
