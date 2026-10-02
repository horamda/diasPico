/* Estado, avisos y pedidos compartidos por los importadores de Rutas */
window.ImportUI = (() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const ICON = {busy:'', ok:'✓', warn:'!', err:'×', info:'i'};
  let saving = false;

  // kind: info | busy | ok | warn | err
  function status(el, msg, kind = 'info') {
    el.className = 'import-status ' + kind;
    el.setAttribute('aria-live', kind === 'err' ? 'assertive' : 'polite');
    el.innerHTML = `<span class="ico" aria-hidden="true">${kind === 'busy' ? '<span class="spinner"></span>' : ICON[kind]}</span><span>${esc(msg)}</span>`;
  }

  function toast(msg, kind = 'ok') {
    const t = document.createElement('div');
    t.className = 'toast ' + kind; t.setAttribute('role', kind === 'err' ? 'alert' : 'status'); t.textContent = msg;
    document.body.appendChild(t); setTimeout(() => t.remove(), kind === 'err' ? 7000 : 4500);
  }

  function timer() {
    const t0 = performance.now();
    return () => { const s = (performance.now() - t0) / 1000; return s < 1 ? 'menos de 1 s' : s.toLocaleString('es-AR', {maximumFractionDigits: 1}) + ' s'; };
  }

  async function request(url, opts = {}, timeoutMs = 120000) {
    const ctl = new AbortController(), id = setTimeout(() => ctl.abort(), timeoutMs);
    let res;
    try { res = await fetch(url, {credentials: 'same-origin', ...opts, signal: ctl.signal}); }
    catch (e) {
      throw Error(e.name === 'AbortError' ? 'El servidor tardó demasiado en responder. Reintentá en unos minutos.'
        : 'No se pudo conectar con el servidor. Revisá la conexión y reintentá.');
    } finally { clearTimeout(id); }
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) throw Error('La sesión venció. Ingresá nuevamente al portal y repetí el análisis.');
    if (res.status === 413) throw Error('El archivo es demasiado grande (máximo 5 MB).');
    if (!res.ok || !data.ok) throw Error(data.error || `No se pudo completar la operación (error ${res.status}).`);
    return data;
  }

  // Avisa si se intenta cerrar la página mientras se guarda.
  window.addEventListener('beforeunload', e => { if (saving) { e.preventDefault(); e.returnValue = ''; } });
  const guardando = v => { saving = v; };

  return {esc, status, toast, timer, request, guardando};
})();
