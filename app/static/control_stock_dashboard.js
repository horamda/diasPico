/* Dashboard de desempeño de control de stock: comparativa por sucursal y por persona.
   Gráficos en HTML/SVG propios; los colores salen de variables CSS de #perfRoot,
   así claro/oscuro se resuelven en la hoja de estilos. */
(function () {
  const SUCURSALES = { '1': 'Casa Central', '2': 'Dolores' };
  const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
  const nf = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 1 });
  const state = { data: null, mes: '', abc: {}, abcPending: {} };

  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = v => (v === null || v === undefined || Number.isNaN(Number(v)) ? '–' : nf.format(Number(v)));
  const pct = v => (v === null || v === undefined ? '–' : `${nf.format(Number(v))}%`);
  const mesCorto = mes => { const [y, m] = String(mes).split('-'); return `${MESES[Number(m) - 1] || m} ${String(y).slice(2)}`; };
  const sucColor = suc => `var(--p-s${suc === '2' ? 2 : 1})`;

  /* ── Tooltip compartido ─────────────────────────────────────────── */
  let tip;
  function tooltip() {
    if (!tip) {
      tip = document.createElement('div');
      tip.className = 'perf-tip';
      tip.setAttribute('role', 'tooltip');
      tip.hidden = true;
      document.body.appendChild(tip);
    }
    return tip;
  }
  function showTip(evt, html) {
    const el = tooltip();
    el.innerHTML = html;
    el.hidden = false;
    const pad = 12;
    const rect = el.getBoundingClientRect();
    let x = evt.clientX + pad;
    let y = evt.clientY + pad;
    if (x + rect.width > window.innerWidth - 8) x = evt.clientX - rect.width - pad;
    if (y + rect.height > window.innerHeight - 8) y = evt.clientY - rect.height - pad;
    el.style.left = `${Math.max(8, x)}px`;
    el.style.top = `${Math.max(8, y)}px`;
  }
  function hideTip() { if (tip) tip.hidden = true; }
  function bindTips(root) {
    root.querySelectorAll('[data-tip]').forEach(node => {
      const html = () => node.getAttribute('data-tip');
      node.addEventListener('pointermove', e => showTip(e, html()));
      node.addEventListener('pointerleave', hideTip);
      node.addEventListener('focus', () => {
        const r = node.getBoundingClientRect();
        showTip({ clientX: r.left + r.width / 2, clientY: r.top }, html());
      });
      node.addEventListener('blur', hideTip);
    });
  }
  const tipRow = (label, value) => `<div class="perf-tip-row"><span>${esc(label)}</span><b>${esc(value)}</b></div>`;
  const tipKey = suc => `<span class="perf-dot" style="background:${sucColor(suc)}"></span>`;

  /* ── Escalas y ejes ─────────────────────────────────────────────── */
  function niceMax(value) {
    if (!value || value <= 0) return 1;
    const exp = Math.pow(10, Math.floor(Math.log10(value)));
    const f = value / exp;
    const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
    return nice * exp;
  }
  const ticks = (max, n = 4) => Array.from({ length: n + 1 }, (_, i) => (max / n) * i);
  // Ancho real de cada panel de una grilla de "small multiples": el SVG se dibuja a ese
  // ancho (sin escalar por viewBox) para que el texto mantenga su tamaño en pantalla.
  function anchoPanel(box, minimo = 240) {
    const cs = getComputedStyle(box);
    const cols = cs.gridTemplateColumns.split(' ').filter(Boolean).length || 1;
    const gap = parseFloat(cs.columnGap) || 0;
    return Math.max(minimo, Math.floor((box.clientWidth - gap * (cols - 1)) / cols));
  }

  /* ── Comparativa por sucursal ───────────────────────────────────── */
  function delta(actual, previo, { invert = false, unit = '' } = {}) {
    if (actual === null || actual === undefined || previo === null || previo === undefined || !previo) return '';
    const diff = actual - previo;
    if (Math.abs(diff) < 0.05) return '<span class="perf-delta flat">= mes anterior</span>';
    const mejor = invert ? diff < 0 : diff > 0;
    const arrow = diff > 0 ? '▲' : '▼';
    return `<span class="perf-delta ${mejor ? 'up' : 'down'}" title="Comparado con el mes anterior">${arrow} ${nf.format(Math.abs(diff))}${unit}</span>`;
  }

  function renderCompare() {
    const d = state.data;
    const previo = {};
    const mesPrevio = (() => { const [y, m] = d.mes.split('-').map(Number); const i = y * 12 + m - 2; return `${Math.floor(i / 12)}-${String(i % 12 + 1).padStart(2, '0')}`; })();
    d.tendencia.filter(t => t.mes === mesPrevio).forEach(t => { previo[t.sucursal] = t; });
    $('perfCompare').innerHTML = d.sucursales.map(s => {
      const p = previo[s.sucursal] || {};
      const abc = state.abc[s.sucursal];
      const abcPct = abc ? Number(abc.cumplimiento_pct || 0) : null;
      const cobertura = d.dias_habiles ? Math.round((s.dias / d.dias_habiles) * 100) : 0;
      return `<article class="perf-suc" style="--p-key:${sucColor(s.sucursal)}">
        <header><span class="perf-swatch"></span><h3>${esc(s.sucursal_nombre)}</h3><small>${num(s.personas)} persona(s)</small></header>
        <div class="perf-hero"><strong>${num(s.articulos)}</strong><span>artículos contados ${delta(s.articulos, p.articulos)}</span></div>
        <dl class="perf-metrics">
          <div><dt>Controles</dt><dd>${num(s.controles)}</dd><small>${num(s.dias)} de ${num(d.dias_habiles)} días hábiles (${cobertura}%)</small></div>
          <div><dt>Artículos por hora</dt><dd>${num(s.articulos_por_hora)}</dd><small>${delta(s.articulos_por_hora, p.articulos_por_hora)}</small></div>
          <div><dt>Minutos por control</dt><dd>${num(s.minutos_por_control)}</dd><small>${delta(s.minutos_por_control, p.minutos_por_control, { invert: true })}</small></div>
          <div><dt>Dispersión vs sistema</dt><dd>${pct(s.dispersion_pct)}</dd><small>${delta(s.dispersion_pct, p.dispersion_pct, { invert: true, unit: ' pts' })}</small></div>
        </dl>
        <div class="perf-meter" aria-label="Cumplimiento ABC">
          <div class="perf-meter-head"><span>Cumplimiento ABC</span><b>${abcPct === null ? '<span class="perf-loading">calculando…</span>' : pct(abcPct)}</b></div>
          <div class="perf-meter-track"><span style="width:${abcPct === null ? 0 : Math.min(100, abcPct)}%"></span></div>
          ${abc ? `<small>${num(abc.controles_pendientes)} controles pendientes · ${num(abc.articulos_vencidos)} artículos fuera de frecuencia</small>` : ''}
        </div>
      </article>`;
    }).join('');
  }

  /* ── Barras horizontales: artículos por persona ─────────────────── */
  function renderBarras() {
    const personas = state.data.personas;
    const box = $('perfArticulos');
    if (!personas.length) { box.innerHTML = '<p class="perf-empty">Sin controles de responsables registrados en el mes.</p>'; return; }
    const max = niceMax(Math.max(...personas.map(p => p.articulos)));
    box.innerHTML = `<div class="perf-bars" role="list">${personas.map(p => {
      const w = (p.articulos / max) * 100;
      const tipHtml = `<b>${tipKey(p.sucursal)}${esc(p.persona)}</b>${tipRow('Sucursal', p.sucursal_nombre)}${tipRow('Artículos', num(p.articulos))}${tipRow('Del equipo', pct(p.participacion_pct))}${tipRow('Controles', num(p.controles))}`;
      return `<div class="perf-bar-row" role="listitem" tabindex="0" data-tip="${esc(tipHtml)}" aria-label="${esc(`${p.persona}, ${p.sucursal_nombre}: ${p.articulos} artículos`)}">
        <div class="perf-bar-name"><span>${esc(p.persona)}</span><small>${esc(p.sucursal_nombre)}</small></div>
        <div class="perf-bar-track"><span class="perf-bar" style="width:${w}%;background:${sucColor(p.sucursal)}"></span></div>
        <div class="perf-bar-value">${num(p.articulos)}<small>${pct(p.participacion_pct)}</small></div>
      </div>`;
    }).join('')}</div>`;
    bindTips(box);
  }

  /* ── Dispersión: productividad (x) vs dispersión (y) ────────────── */
  function renderScatter() {
    const box = $('perfScatter');
    const pts = state.data.personas.filter(p => p.articulos_por_hora !== null && p.dispersion_pct !== null);
    if (!pts.length) { box.innerHTML = '<p class="perf-empty">Faltan controles con horario para calcular la productividad.</p>'; return; }
    const W = Math.max(280, box.clientWidth || 480);
    const H = Math.round(Math.min(340, Math.max(240, W * 0.62)));
    const m = { t: 16, r: 18, b: 42, l: 46 };
    const xMax = niceMax(Math.max(...pts.map(p => p.articulos_por_hora)) * 1.12);
    const yMax = Math.min(100, niceMax(Math.max(...pts.map(p => p.dispersion_pct)) * 1.12));
    const x = v => m.l + (v / xMax) * (W - m.l - m.r);
    const y = v => H - m.b - (v / yMax) * (H - m.t - m.b);
    const tot = state.data.sucursales.reduce((a, s) => ({ art: a.art + s.articulos, disp: a.disp + s.con_dispersion, min: a.min + s.minutos }), { art: 0, disp: 0, min: 0 });
    const prodProm = tot.min ? tot.art / (tot.min / 60) : null;
    const dispProm = tot.art ? (tot.disp / tot.art) * 100 : null;
    let svg = `<svg class="perf-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Productividad contra dispersión por persona">`;
    ticks(xMax).forEach(t => { svg += `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${m.t}" y2="${H - m.b}"/><text class="tick" x="${x(t)}" y="${H - m.b + 16}" text-anchor="middle">${nf.format(t)}</text>`; });
    ticks(yMax).forEach(t => { svg += `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/><text class="tick" x="${m.l - 8}" y="${y(t) + 4}" text-anchor="end">${nf.format(t)}%</text>`; });
    if (prodProm) svg += `<line class="ref" x1="${x(prodProm)}" x2="${x(prodProm)}" y1="${m.t}" y2="${H - m.b}"/><text class="ref-label" x="${x(prodProm) + 4}" y="${m.t + 10}">prom. ${nf.format(prodProm)}/h</text>`;
    if (dispProm !== null) svg += `<line class="ref" x1="${m.l}" x2="${W - m.r}" y1="${y(dispProm)}" y2="${y(dispProm)}"/><text class="ref-label" x="${m.l + 4}" y="${y(dispProm) - 5}">prom. ${nf.format(dispProm)}%</text>`;
    svg += `<text class="axis-title" x="${(m.l + W - m.r) / 2}" y="${H - 6}" text-anchor="middle">Artículos por hora →</text>`;
    svg += `<text class="axis-title" transform="translate(12 ${(m.t + H - m.b) / 2}) rotate(-90)" text-anchor="middle">Dispersión vs sistema</text>`;
    pts.forEach(p => {
      const cx = x(p.articulos_por_hora), cy = y(p.dispersion_pct);
      const tipHtml = `<b>${tipKey(p.sucursal)}${esc(p.persona)}</b>${tipRow('Sucursal', p.sucursal_nombre)}${tipRow('Artículos por hora', num(p.articulos_por_hora))}${tipRow('Dispersión', pct(p.dispersion_pct))}${tipRow('Artículos', num(p.articulos))}`;
      const anchor = cx > W * 0.7 ? 'end' : 'start';
      const dx = anchor === 'end' ? -11 : 11;
      svg += `<g class="pt" tabindex="0" data-tip="${esc(tipHtml)}" aria-label="${esc(`${p.persona}: ${p.articulos_por_hora} artículos por hora, ${p.dispersion_pct}% de dispersión`)}">
        <circle class="hit" cx="${cx}" cy="${cy}" r="16"/>
        <circle class="dot" cx="${cx}" cy="${cy}" r="6.5" style="fill:${sucColor(p.sucursal)}"/>
        <text class="pt-label" x="${cx + dx}" y="${cy + 4}" text-anchor="${anchor}">${esc(p.persona.split(' ')[0])}</text></g>`;
    });
    svg += '</svg>';
    box.innerHTML = svg;
    bindTips(box);
  }

  /* ── Tendencia: tres paneles chicos, una línea por sucursal ─────── */
  function lineChart(W, title, key, fmtValue, note) {
    const filas = state.data.tendencia;
    const meses = [...new Set(filas.map(t => t.mes))];
    const valores = filas.map(t => t[key]).filter(v => v !== null && v !== undefined);
    const H = 170, m = { t: 14, r: 16, b: 26, l: 44 };
    const yMax = niceMax(Math.max(1, ...valores) * 1.1);
    const step = meses.length > 1 ? (W - m.l - m.r) / (meses.length - 1) : 0;
    const x = i => m.l + i * step;
    const y = v => H - m.b - (v / yMax) * (H - m.t - m.b);
    let svg = `<svg class="perf-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)} por mes y sucursal">`;
    ticks(yMax, 3).forEach(t => { svg += `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/><text class="tick" x="${m.l - 6}" y="${y(t) + 4}" text-anchor="end">${fmtValue(t, true)}</text>`; });
    meses.forEach((mes, i) => { svg += `<text class="tick" x="${x(i)}" y="${H - 8}" text-anchor="middle">${mesCorto(mes)}</text>`; });
    ['1', '2'].forEach(suc => {
      const serie = meses.map(mes => filas.find(t => t.mes === mes && t.sucursal === suc)?.[key] ?? null);
      let d = '';
      serie.forEach((v, i) => { if (v === null) return; d += `${d && serie[i - 1] !== null ? 'L' : 'M'}${x(i)} ${y(v)} `; });
      if (d) svg += `<path class="line" d="${d}" style="stroke:${sucColor(suc)}"/>`;
      serie.forEach((v, i) => { if (v !== null) svg += `<circle class="mark" cx="${x(i)}" cy="${y(v)}" r="4.5" style="fill:${sucColor(suc)}"/>`; });
    });
    meses.forEach((mes, i) => {
      const rows = ['1', '2'].map(suc => filas.find(t => t.mes === mes && t.sucursal === suc));
      const tipHtml = `<b>${esc(title)} · ${mesCorto(mes)}</b>` + rows.map(r => `<div class="perf-tip-row"><span>${tipKey(r.sucursal)}${esc(r.sucursal_nombre)}</span><b>${r[key] === null ? 'sin datos' : esc(fmtValue(r[key]))}</b></div>`).join('');
      const half = step / 2 || (W - m.l - m.r) / 2;
      svg += `<rect class="col-hit" tabindex="0" x="${x(i) - half}" y="${m.t}" width="${half * 2}" height="${H - m.t - m.b}" data-tip="${esc(tipHtml)}"><title>${esc(mesCorto(mes))}</title></rect>`;
    });
    svg += '</svg>';
    return `<figure class="perf-mini"><figcaption>${esc(title)}${note ? `<small>${esc(note)}</small>` : ''}</figcaption>${svg}</figure>`;
  }
  function renderTendencia() {
    const box = $('perfTendencia');
    const W = anchoPanel(box);
    box.innerHTML = [
      lineChart(W, 'Artículos contados', 'articulos', (v, axis) => (axis ? nf.format(Math.round(v)) : nf.format(v))),
      lineChart(W, 'Artículos por hora', 'articulos_por_hora', v => nf.format(v)),
      lineChart(W, 'Dispersión vs sistema', 'dispersion_pct', v => `${nf.format(v)}%`, 'menos es mejor'),
    ].join('');
    bindTips(box);
  }

  /* ── Actividad diaria: columnas por día, un panel por sucursal ──── */
  function renderDiario() {
    const d = state.data;
    const [y, m] = d.mes.split('-').map(Number);
    const dias = new Date(y, m, 0).getDate();
    const max = niceMax(Math.max(1, ...d.diario.map(r => r.articulos)));
    const box = $('perfDiario');
    const W = anchoPanel(box, 260);
    box.innerHTML = ['1', '2'].map(suc => {
      const H = 160, mg = { t: 10, r: 6, b: 22, l: 34 };
      const slot = (W - mg.l - mg.r) / dias;
      const bw = Math.max(2, slot - 2);
      const yy = v => H - mg.b - (v / max) * (H - mg.t - mg.b);
      let svg = `<svg class="perf-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Artículos contados por día en ${esc(SUCURSALES[suc])}">`;
      ticks(max, 2).forEach(t => { svg += `<line class="grid" x1="${mg.l}" x2="${W - mg.r}" y1="${yy(t)}" y2="${yy(t)}"/><text class="tick" x="${mg.l - 5}" y="${yy(t) + 4}" text-anchor="end">${nf.format(t)}</text>`; });
      for (let day = 1; day <= dias; day++) {
        const fecha = `${d.mes}-${String(day).padStart(2, '0')}`;
        const dow = new Date(y, m - 1, day).getDay();
        const bx = mg.l + (day - 1) * slot + (slot - bw) / 2;
        if (dow === 0 || dow === 6) svg += `<rect class="weekend" x="${mg.l + (day - 1) * slot}" y="${mg.t}" width="${slot}" height="${H - mg.t - mg.b}"/>`;
        const row = d.diario.find(r => r.fecha === fecha && r.sucursal === suc);
        if (row && row.articulos > 0) {
          const top = yy(row.articulos);
          const h = H - mg.b - top;
          const r = Math.min(3, bw / 2, h);
          const path = `M${bx} ${H - mg.b}V${top + r}Q${bx} ${top} ${bx + r} ${top}H${bx + bw - r}Q${bx + bw} ${top} ${bx + bw} ${top + r}V${H - mg.b}Z`;
          const tipHtml = `<b>${tipKey(suc)}${day}/${m} · ${esc(SUCURSALES[suc])}</b>${tipRow('Artículos', num(row.articulos))}` + Object.entries(row.personas).map(([n, v]) => tipRow(n, num(v))).join('');
          svg += `<path class="col" tabindex="0" d="${path}" style="fill:${sucColor(suc)}" data-tip="${esc(tipHtml)}"/>`;
        }
        if (day === 1 || day % 5 === 0) svg += `<text class="tick" x="${bx + bw / 2}" y="${H - 7}" text-anchor="middle">${day}</text>`;
      }
      svg += `<line class="baseline" x1="${mg.l}" x2="${W - mg.r}" y1="${H - mg.b}" y2="${H - mg.b}"/></svg>`;
      const total = d.diario.filter(r => r.sucursal === suc).reduce((a, r) => a + r.articulos, 0);
      return `<figure class="perf-mini"><figcaption><span class="perf-swatch" style="background:${sucColor(suc)}"></span>${esc(SUCURSALES[suc])}<small>${num(total)} artículos · fines de semana sombreados</small></figcaption>${svg}</figure>`;
    }).join('');
    bindTips(box);
  }

  /* ── Tabla por persona ──────────────────────────────────────────── */
  function renderTabla() {
    const d = state.data;
    $('perfTabla').innerHTML = d.personas.length ? `<table class="perf-table"><thead><tr>
        <th>Persona</th><th>Sucursal</th><th class="num">Días</th><th class="num">Controles</th><th class="num">Artículos</th>
        <th class="num">% del equipo</th><th class="num">Art./hora</th><th class="num">Min./control</th><th class="num">Dispersión</th><th class="num">Correcciones</th>
      </tr></thead><tbody>${d.personas.map(p => `<tr>
        <td><span class="perf-swatch" style="background:${sucColor(p.sucursal)}"></span>${esc(p.persona)}</td><td>${esc(p.sucursal_nombre)}</td>
        <td class="num">${num(p.dias)}</td><td class="num">${num(p.controles)}</td><td class="num">${num(p.articulos)}</td>
        <td class="num">${pct(p.participacion_pct)}</td><td class="num">${num(p.articulos_por_hora)}</td><td class="num">${num(p.minutos_por_control)}</td>
        <td class="num">${pct(p.dispersion_pct)}</td><td class="num">${num(p.correcciones)}</td></tr>`).join('')}</tbody></table>` : '<p class="perf-empty">Sin datos para el mes.</p>';
    const ex = d.excluidos || [];
    $('perfExcluidos').textContent = ex.length
      ? `No se incluyen ${ex.reduce((a, r) => a + r.controles, 0)} control(es) de nombres que no figuran en Responsables: ${ex.map(r => r.responsable).join(', ')}.`
      : '';
  }

  function renderAll() {
    if (!state.data) return;
    $('perfPeriodo').textContent = `${mesCorto(state.data.mes)} · tendencia desde ${mesCorto(state.data.desde)}`;
    renderCompare();
    renderBarras();
    renderScatter();
    renderTendencia();
    renderDiario();
    renderTabla();
  }

  /* ── Cumplimiento ABC: lo calcula el resumen mensual (más lento) ─── */
  function setAbc(sucursal, mes, kpis) {
    if (mes !== state.mes || !kpis) return;
    state.abc[String(sucursal)] = kpis;
    if (state.data) renderCompare();
  }
  async function pedirAbc(sucursal, mes) {
    const key = `${mes}:${sucursal}`;
    if (state.abcPending[key]) return;
    state.abcPending[key] = true;
    try {
      const res = await fetch(`/api/control-stock/resumen-mensual?mes=${encodeURIComponent(mes)}&sucursal=${encodeURIComponent(sucursal)}`);
      const body = await res.json();
      if (res.ok && body.ok !== false) setAbc(sucursal, mes, body.kpis);
    } catch (_) { /* el resto del tablero sigue funcionando */ }
  }

  async function load(mes, sucursalPrincipal) {
    state.mes = mes;
    state.abc = {};
    state.abcPending = {};
    const status = $('perfStatus');
    status.textContent = 'Cargando desempeño…';
    status.className = 'perf-note';
    // La sucursal principal la pide loadResumenMensual; acá solo la otra.
    Object.keys(SUCURSALES).filter(s => s !== String(sucursalPrincipal)).forEach(s => pedirAbc(s, mes));
    try {
      const res = await fetch(`/api/control-stock/desempeno?mes=${encodeURIComponent(mes)}&meses=4`);
      const body = await res.json();
      if (!res.ok || body.ok === false) throw new Error(body.error || `Error ${res.status}`);
      if (mes !== state.mes) return;
      state.data = body;
      status.textContent = '';
      renderAll();
    } catch (err) {
      status.textContent = `No se pudo cargar el desempeño: ${err.message || err}`;
      status.className = 'perf-note err';
    }
  }

  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (state.data) { renderScatter(); renderTendencia(); renderDiario(); } }, 150);
  });
  window.addEventListener('scroll', hideTip, { passive: true });

  window.perfDashboard = { load, setAbc };
})();
