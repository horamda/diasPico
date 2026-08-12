// ─── CONFIG ──────────────────────────────────────────────────
const API   = window.location.origin;
const MESES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
const DC    = ['Do','Lu','Ma','Mi','Ju','Vi','Sa'];

let vY = new Date().getFullYear(), vM = new Date().getMonth();
let selDay = null, picoSet = new Set(), diasData = [], mesKpis = {};
let umbral = 1.20, metrica = 'bultos';
let cfg = JSON.parse(localStorage.getItem('pico_cfg') || '{}');
let _drawerAbort = null;
let _mesAbort = null;
let _loadMesSeq = 0;
let _paramsAbort = null;
let _loadParamsSeq = 0;
let _histAbort = null;
let _loadHistSeq = 0;
let _ventaDiaAbort = null;
let _loadVentaDiaSeq = 0;
let _ventaAnualAbort = null;
let _loadVentaAnualSeq = 0;
let _expAbort = null;
let _loadExpSeq = 0;
let _hlAbort = null;
let _loadHlSeq = 0;
let _dropAbort = null;
let _loadDropSeq = 0;
let historicoChart = null;
let historicoPicosChart = null;
let historicoVolumenChart = null;
let rechazoPctCharts = {};
let ventaAnualChart = null;
let ventaDiaData = null;
let ventaDiaCmpCharts = {};
let ventaDiaEvoCharts = {};
let ventaDiaDistCharts = {};
let experienciaData = null;
let experienciaCharts = {};
let experienciaMap = null;
let experienciaMapLayer = null;
let dropDiarioChart = null;
let dropMensualChart = null;
let planActualId = null;
let planEscenarioActivoId = null;
let planEscenariosData = [];
let planCharts = {};
let dropsizeObjetivos = [];
let kpiObjetivos = [];

// ─── HELPERS ─────────────────────────────────────────────────
const mesPad = () => `${vY}-${String(vM + 1).padStart(2, '0')}`;
const dk     = (y, m, d) => `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
const fmtN   = v => v == null ? '—' : Number(v).toLocaleString('es-AR');
const fmtM   = v => v == null ? '—' : '$' + Number(v).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
const fmtPct = v => (Number(v) || 0).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) + '%';
const esc    = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const jsEsc  = v => String(v ?? '').replace(/['\\]/g, c => ({ "'": "\\'", '\\': '\\\\' }[c]));

const fmtDrop = v => Number(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmt1 = v => Number(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const fmtPct1 = v => `${fmt1(v)}%`;
const fmtDelta = v => v == null ? '—' : `${v > 0 ? '+' : ''}${fmtPct(v)}`;
const MES_CORTO = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

function dayDetailText(value, fallback = 'Sin dato') {
  if (value === null || value === undefined) return fallback;
  const s = String(value).trim();
  if (!s || s === '?' || s === '¿') return fallback;
  return s ? esc(s) : fallback;
}

function dayDetailTime(value, fallback = 'Sin hora') {
  if (value === null || value === undefined) return fallback;
  const s = String(value).trim();
  if (!s || s === '?' || s === '¿') return fallback;
  const m = s.match(/\b(\d{2}:\d{2})(?::\d{2})?\b/);
  return esc(m ? m[1] : s);
}

const chartValueLabels = {
  id: 'chartValueLabels',
  afterDatasetsDraw(chart, _args, opts = {}) {
    const ctx = chart.ctx;
    const datasets = chart.data.datasets || [];
    ctx.save();
    ctx.font = opts.font || '600 10px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = opts.shadowColor || 'rgba(0,0,0,.55)';
    ctx.shadowBlur = opts.shadowBlur ?? 3;
    ctx.shadowOffsetY = opts.shadowOffsetY ?? 1;
    datasets.forEach((ds, dsIndex) => {
      if (ds.showLabels === false) return;
      const meta = chart.getDatasetMeta(dsIndex);
      if (!meta || meta.hidden) return;
      const color = ds.labelColor || ds.borderColor || '#e8eaf0';
      const totalPoints = Array.isArray(ds.data) ? ds.data.length : 0;
      const maxLabels = Number(opts.maxLabelsPerDataset || ds.maxLabelsPerDataset || 0);
      const step = maxLabels > 0 && totalPoints > maxLabels ? Math.ceil(totalPoints / maxLabels) : 1;
      meta.data.forEach((element, index) => {
        const raw = ds.data?.[index];
        if (raw == null || Number.isNaN(Number(raw))) return;
        if (opts.hideZero && Number(raw) === 0) return;
        if (step > 1 && index % step !== 0 && index !== totalPoints - 1) return;
        const pos = element.tooltipPosition();
        const label = ds.valueFormatter ? ds.valueFormatter(raw) : fmtN(Math.round(raw));
        if (!label) return;
        ctx.fillStyle = Array.isArray(color) ? color[index] : color;
        const isBar = chart.config?.type === 'bar' || ds.type === 'bar';
        const isHorizontalBar = isBar && chart.options?.indexAxis === 'y';
        if (isHorizontalBar) {
          const props = element.getProps ? element.getProps(['x', 'y', 'base'], true) : pos;
          const positive = Number(raw) >= 0;
          let x = Number(props.x ?? pos.x) + (positive ? 8 : -8);
          let align = positive ? 'left' : 'right';
          if (chart.chartArea) {
            if (x > chart.chartArea.right - 8) {
              x = Number(props.x ?? pos.x) - 8;
              align = 'right';
            } else if (x < chart.chartArea.left + 8) {
              x = Number(props.x ?? pos.x) + 8;
              align = 'left';
            }
          }
          ctx.textAlign = align;
          ctx.textBaseline = 'middle';
          ctx.fillText(label, x, Number(props.y ?? pos.y));
          return;
        }
        ctx.textAlign = 'center';
        const y = isBar ? pos.y - 8 : (pos.y <= 18 ? pos.y + 14 : pos.y - 12);
        ctx.fillText(label, pos.x, y);
      });
    });
    ctx.restore();
  },
};

function metricSummaryLabel(metric) {
  return ({
    bultos: 'Bultos desp.',
    hectolitros: 'HL desp.',
    pallets: 'Pallets mes',
    up: 'UP mes',
    pedidos: 'PDV atendidos',
    clientes: 'Clientes mes',
  })[metric] || 'Total mes';
}

function metricSummaryValue(kpis, metric) {
  if (metric === 'pedidos' || metric === 'clientes') return fmtN(kpis?.[metric] ?? 0);
  return fmtN(Math.round(kpis?.[metric] ?? 0));
}

function isTabVisible(id) {
  const el = document.getElementById(id);
  return !!el && el.style.display !== 'none';
}

async function refreshPicoDependentViews() {
  await loadMes();
  loadHistorico();
  if (isTabVisible('tab-venta-dia')) loadVentaDia();
  if (isTabVisible('tab-venta-anual')) loadVentaAnual();
  if (isTabVisible('tab-comparativo')) loadComparativo();
  if (isTabVisible('tab-experiencia')) loadExperienciaClientes();
  if (isTabVisible('tab-dotacion')) loadDotacion();
  if (isTabVisible('tab-analisis')) { loadAnalisisHl(); loadRechazosRankings(); }
  if (isTabVisible('tab-dropsize')) loadDropsize();
  if (isTabVisible('tab-planificacion')) loadPlanificacion();
  if (isTabVisible('tab-config')) loadKpiObjetivos();
}

function _kpiProyeccion(kAnt) {
  return {
    bultos: kAnt.bultos ?? 0,
    hectolitros: kAnt.hectolitros ?? 0,
    pallets: kAnt.pallets ?? 0,
    up: kAnt.up ?? 0,
    pedidos: kAnt.pedidos ?? 0,
    clientes: kAnt.clientes ?? 0,
    importe: kAnt.importe ?? 0,
    camiones: kAnt.camiones ?? 0,
    dias: kAnt.dias ?? 0,
    rechazo_bultos: kAnt.rechazo_bultos ?? 0,
    rechazo_bultos_parcial: kAnt.rechazo_bultos_parcial ?? 0,
    rechazo_bultos_total: kAnt.rechazo_bultos_total ?? 0,
    rechazo_hl: kAnt.rechazo_hl ?? 0,
    rechazo_hl_parcial: kAnt.rechazo_hl_parcial ?? 0,
    rechazo_hl_total: kAnt.rechazo_hl_total ?? 0,
    rechazo_pedidos: kAnt.rechazo_pedidos ?? 0,
    pct_rechazo_bultos: kAnt.pct_rechazo_bultos ?? 0,
    pct_rechazo_hl: kAnt.pct_rechazo_hl ?? 0,
    pct_rechazo_pedidos: kAnt.pct_rechazo_pedidos ?? 0,
    rmcyo_bultos: kAnt.rmcyo_bultos ?? 0,
    rmcyo_hl: kAnt.rmcyo_hl ?? 0,
    rmcyo_pedidos: kAnt.rmcyo_pedidos ?? 0,
    rmcyo_rechazo_bultos: kAnt.rmcyo_rechazo_bultos ?? 0,
    rmcyo_rechazo_hl: kAnt.rmcyo_rechazo_hl ?? 0,
    rmcyo_pct_rechazo_hl: kAnt.rmcyo_pct_rechazo_hl ?? 0,
    rmcyo_pct_rechazo_bultos: kAnt.rmcyo_pct_rechazo_bultos ?? 0,
    rmcyo_pct_rechazo_pedidos: kAnt.rmcyo_pct_rechazo_pedidos ?? 0,
    objetivos: kAnt.objetivos || {},
  };
}

async function api(path, options = {}) {
  const timeoutMs = options.timeout ?? 30000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const fetchOptions = {
    ...options,
    signal: options.signal || controller.signal
  };
  try {
    const r = await fetch(API + path, fetchOptions);
    clearTimeout(timeoutId);
    if (!r.ok) {
      let msg = 'HTTP ' + r.status;
      try { const j = await r.json(); if (j && j.error) msg = j.error; } catch (_) {}
      throw new Error(msg);
    }
    return r.json();
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError' && !options.signal) {
      throw new Error('Timeout ' + timeoutMs + 'ms');
    }
    throw err;
  }
}

function load(id)       { document.getElementById(id).innerHTML = '<div class="loading"><div class="spinner"></div>Cargando...…</div>'; }
function errBox(id, msg){ document.getElementById(id).innerHTML = `<div class="err-box">âš  ${msg}</div>`; }

// ─── INIT ────────────────────────────────────────────────────
function resizeDashboardVisuals() {
  const chartSets = [
    ventaDiaCmpCharts,
    ventaDiaEvoCharts,
    ventaDiaDistCharts,
    experienciaCharts,
    planCharts,
  ];
  const charts = [historicoChart, historicoPicosChart, historicoVolumenChart, ventaAnualChart, dropDiarioChart, dropMensualChart];
  chartSets.forEach(set => {
    Object.values(set || {}).forEach(chart => {
      if (chart) charts.push(chart);
    });
  });
  charts.forEach(chart => {
    if (chart && typeof chart.resize === 'function') chart.resize();
  });
  if (experienciaMap && typeof experienciaMap.invalidateSize === 'function') {
    experienciaMap.invalidateSize();
  }
}

function applyCalendarSidebarState(hidden) {
  const layout = document.getElementById('mainLayout');
  const btn = document.getElementById('toggleCalendarBtn');
  if (layout) layout.classList.toggle('calendar-collapsed', hidden);
  if (btn) {
    btn.classList.toggle('is-collapsed', hidden);
    btn.setAttribute('aria-pressed', hidden ? 'true' : 'false');
    btn.textContent = hidden ? 'Mostrar calendario' : 'Ocultar calendario';
    btn.title = hidden ? 'Mostrar calendario lateral' : 'Ocultar calendario lateral';
  }
  window.dispatchEvent(new Event('resize'));
  setTimeout(resizeDashboardVisuals, 260);
}

function initCalendarSidebarToggle() {
  applyCalendarSidebarState(localStorage.getItem('pico_calendar_hidden') === '1');
}

function toggleCalendarSidebar() {
  const hidden = !document.getElementById('mainLayout')?.classList.contains('calendar-collapsed');
  localStorage.setItem('pico_calendar_hidden', hidden ? '1' : '0');
  applyCalendarSidebarState(hidden);
}

window.onload = async () => {
  const hoy = new Date();
  document.getElementById('hdrFecha').textContent = `${hoy.getDate()} ${MESES[hoy.getMonth()]} ${hoy.getFullYear()}`;
  initCalendarSidebarToggle();
  restoreConfig();
  initDropsizeFilters();
  initVentaDiaFilters();
  initVentaAnualDefaults();
  initKpiObjetivosDefaults();
  initPlanificacionDefaults();
  initAusentismoDefaults();
  await loadSucursales();
  await loadParams();
  renderCal();
  await loadMes();
  loadHistorico();
  loadArticulosCount();
  loadPeriodosCriticos();
};

function restoreConfig() {
  if (cfg.equiposUrl)     document.getElementById('cfgEquiposUrl').value     = cfg.equiposUrl;
  if (cfg.disponiblesUrl) document.getElementById('cfgDisponiblesUrl').value = cfg.disponiblesUrl;
  if (cfg.dotacionEntregaUrl && document.getElementById('cfgDotacionEntregaUrl')) document.getElementById('cfgDotacionEntregaUrl').value = cfg.dotacionEntregaUrl;
  if (cfg.dotacionRecargasUrl && document.getElementById('cfgDotacionRecargasUrl')) document.getElementById('cfgDotacionRecargasUrl').value = cfg.dotacionRecargasUrl;
  if (cfg.feriadosUrl)    document.getElementById('inputFeriadosUrl').value   = cfg.feriadosUrl;
}

// ─── SUCURSALES ───────────────────────────────────────────────
function initKpiObjetivosDefaults() {
  const desde = document.getElementById('kpiObjDesde');
  const hasta = document.getElementById('kpiObjHasta');
  if (desde && !desde.value) desde.value = `${vY}-01-01`;
  if (hasta && !hasta.value) hasta.value = `${vY}-12-31`;
}

function initPlanificacionDefaults() {
  const hoy = new Date();
  const anio = document.getElementById('planAnio');
  const mes = document.getElementById('planMes');
  const anioBase = document.getElementById('planAnioBase');
  if (anio && !anio.value) anio.value = hoy.getFullYear();
  if (mes && !mes.value) mes.value = hoy.getMonth() + 1;
  if (anioBase && !anioBase.value) anioBase.value = hoy.getFullYear() - 1;
}

function initAusentismoDefaults() {
  const anio = document.getElementById('ausAnio');
  const mes = document.getElementById('ausMes');
  const suc = document.getElementById('ausSucursal');
  if (anio && !anio.value) anio.value = vY;
  if (mes && !mes.value) mes.value = vM + 1;
  if (suc && !suc.value) suc.value = 'TODAS';
}

async function loadSucursales() {
  const selUp  = document.getElementById('uploadSucursal');
  const sel    = document.getElementById('selSucursal');
  const selVentaDia = document.getElementById('ventaDiaSucursal');
  const selVentaAnual = document.getElementById('ventaAnualSucursal');
  const selExp = document.getElementById('expSucursal');
  const selCfg = document.getElementById('cfgSucursal');
  const selEv  = document.getElementById('evSucursal');
  const selDrop = document.getElementById('dropSucursal');
  const selDropObj = document.getElementById('dropObjSucursal');
  const selKpiObj = document.getElementById('kpiObjSucursal');
  const selPlan = document.getElementById('planSucursal');
  const selAus = document.getElementById('ausSucursal');
  try {
    const data = await api('/api/sucursales'); // [{value, label}, ...]
    data.forEach(({ value, label }) => {
      const txt = `${value} — ${label}`;
      selUp.add(new Option(txt, value));
      sel.add(new Option(txt, value));
      if (selVentaDia && !selVentaDia.querySelector(`option[value="${value}"]`)) selVentaDia.add(new Option(txt, value));
      if (selVentaAnual && !selVentaAnual.querySelector(`option[value="${value}"]`)) selVentaAnual.add(new Option(txt, value));
      if (selExp && !selExp.querySelector(`option[value="${value}"]`)) selExp.add(new Option(txt, value));
      selCfg.add(new Option(txt, value));
      selEv.add(new Option(txt, value));
      if (selDrop) selDrop.add(new Option(txt, value));
      if (selDropObj) selDropObj.add(new Option(txt, value));
      if (selKpiObj) selKpiObj.add(new Option(txt, value));
      if (selPlan) selPlan.add(new Option(txt, value));
      if (selAus && !selAus.querySelector(`option[value="${value}"]`)) selAus.add(new Option(txt, value));
      const selFlota = document.getElementById('flotaSucursal');
      if (selFlota && !selFlota.querySelector(`option[value="${value}"]`)) selFlota.add(new Option(txt, value));
    });
  } catch (e) {}
  if (selVentaDia && sel) selVentaDia.value = sel.value;
  if (selVentaAnual && sel) selVentaAnual.value = sel.value;
  if (selExp && sel) selExp.value = sel.value;
  await loadCatalogoPlanificacion();
}

function fillPlanSelect(select, items, allLabel = null) {
  if (!select) return;
  const current = select.value;
  select.innerHTML = '';
  if (allLabel) select.add(new Option(allLabel, 'TODAS'));
  items.forEach(item => select.add(new Option(item.label, item.value)));
  if ([...select.options].some(o => o.value === current)) select.value = current;
}

async function loadCatalogoPlanificacion() {
  const empresaSel = document.getElementById('planEmpresa');
  if (!empresaSel) return;
  try {
    const empresas = await fetchPlanJson('/api/catalogo/empresas?activa=1');
    const items = (empresas.data || []).map(e => ({
      value: String(e.id),
      label: e.nombre_fantasia ? `${e.id} - ${e.nombre_fantasia}` : `${e.id} - ${e.razon_social}`,
    }));
    if (items.length) fillPlanSelect(empresaSel, items);
    await loadCatalogoSucursalesPlanificacion();
  } catch (e) {
    // La API externa es opcional; si no esta configurada se conserva el catalogo local.
  }
}

async function loadCatalogoSucursalesPlanificacion() {
  const empresaSel = document.getElementById('planEmpresa');
  const sucSel = document.getElementById('planSucursal');
  if (!empresaSel || !sucSel) return;
  try {
    const qs = new URLSearchParams({ activa: '1' });
    if (empresaSel.value) qs.set('empresa_id', empresaSel.value);
    const sucursales = await fetchPlanJson('/api/catalogo/sucursales?' + qs.toString());
    const items = (sucursales.data || []).map(s => ({
      value: String(s.id),
      label: `${s.id} - ${s.nombre}`,
    }));
    if (items.length) fillPlanSelect(sucSel, items, 'Todas');
  } catch (e) {}
}

async function loadParams(applyMetric = true) {
  const seq = ++_loadParamsSeq;
  if (_paramsAbort) _paramsAbort.abort();
  _paramsAbort = new AbortController();

  try {
    const suc = getSuc();
    const p = await api(`/api/parametros?sucursal=${suc}`, { signal: _paramsAbort.signal });
    if (seq !== _loadParamsSeq || suc !== getSuc()) return;
    const u = p.umbral_pct || 1.20;
    const m = p.metrica    || 'bultos';
    document.getElementById('sliderUmbral').value = u;
    document.getElementById('cfgUmbral').value    = u;
    document.getElementById('cfgMetrica').value   = m;
    if (applyMetric) {
      document.getElementById('selMetrica').value = m;
      metrica = m;
    }
    onUmbralChange(u);
  } catch (e) {
    if (e.name === 'AbortError') return;
  }
}

function getSuc() { return document.getElementById('selSucursal').value; }

// ─── CALENDAR ────────────────────────────────────────────────
function renderCal() {
  const now = new Date();
  document.getElementById('calLbl').textContent = `${MESES[vM]} ${vY}`;
  const g = document.getElementById('calGrid');
  g.innerHTML = '';
  DC.forEach(d => {
    const e = document.createElement('div');
    e.className = 'cal-dname';
    e.textContent = d;
    g.appendChild(e);
  });
  const first = new Date(vY, vM, 1).getDay();
  const days  = new Date(vY, vM + 1, 0).getDate();
  for (let i = 0; i < first; i++) {
    const e = document.createElement('div');
    e.className = 'cal-day empty';
    g.appendChild(e);
  }
  for (let d = 1; d <= days; d++) {
    const k  = dk(vY, vM, d);
    const dd = diasData.find(x => x.fecha === k);
    const isToday = d === now.getDate() && vM === now.getMonth() && vY === now.getFullYear();
    const e = document.createElement('div');
    let cls = 'cal-day';
    if (selDay === k)       cls += ' selected';
    else if (dd?.es_pico)   cls += ' pico';
    if (dd?.es_feriado)     cls += ' feriado';
    if (dd?.es_evento)      cls += ' evento';
    if (isToday)            cls += ' today';
    if (dd)                 cls += ' has-data';
    if (dd?.es_problema_nds)               cls += ' nds-problema';
    if (dd?.es_proyeccion)                 cls += ' proyeccion';
    if (dd?.dot?.tiene_s2)                 cls += ' dot-s2';
    else if (dd?.dot?.tiene_datos)         cls += ' dot-s1only';
    e.className  = cls;
    e.textContent = d;
    const dotTip = dd?.dot?.tiene_datos
      ? ` — Dot: S1:${dd.dot.s1?.personas ?? 0}p` + (dd.dot.tiene_s2 ? ` / S2:${dd.dot.s2?.personas ?? 0}p` : ' (sin S2)')
      : '';
    e.title = dd
      ? `${dd.bultos} bultos — ${dd.hectolitros} hl` +
        ` — NDS: ${dd.nds ?? 100}%` +
        (dd.ausentismo > 0 ? ` — Ausentismo: ${dd.ausentismo}` : '') +
        ` — Rec: ${dd.pct_rechazo_pedidos ?? 0}% PDV / ${dd.pct_rechazo_bultos ?? 0}% blt / ${dd.pct_rechazo_hl ?? 0}% hl` +
        dotTip +
        (dd.es_feriado ? ` — ${dd.feriado_tipo || 'Feriado'}: ${dd.feriado_desc}` : '') +
        (dd.es_evento  ? ` — Evento: ${dd.evento_desc}` : '')
      : '';
    e.onclick = () => selectDay(k);
    g.appendChild(e);
  }
}

async function changeMonth(dir) {
  vM += dir;
  if (vM > 11) { vM = 0; vY++; }
  if (vM < 0)  { vM = 11; vY--; }
  picoSet = new Set(); diasData = []; mesKpis = {};
  renderCal();
  await loadMes();
  loadArticulosCount();
  loadPeriodosCriticos();
  if (document.getElementById('tab-dropsize')?.style.display !== 'none') {
    document.getElementById('dropMes').value = mesPad();
    setDropsizeDatesFromMes(false);
    loadDropsize();
  }
}

// ─── CARGA PRINCIPAL ─────────────────────────────────────────
async function loadMes() {
  const seq = ++_loadMesSeq;
  if (_mesAbort) _mesAbort.abort();
  _mesAbort = new AbortController();

  load('kpiGrid'); load('tablaDias');
  destroyRechazoPctCharts();
  try {
    const u    = document.getElementById('sliderUmbral').value;
    const m    = document.getElementById('selMetrica').value;
    const mes  = mesPad();
    const suc  = getSuc();
    const data = await api(
      `/api/picos/calendario?sucursal=${suc}&mes=${mes}&umbral=${u}&metrica=${m}`,
      { signal: _mesAbort.signal }
    );
    if (seq !== _loadMesSeq || mes !== mesPad() || suc !== getSuc() || m !== document.getElementById('selMetrica').value || u !== document.getElementById('sliderUmbral').value) return;

    diasData = data.dias || [];
    const diasAnt = data.dias_anterior || [];
    const kAnt    = data.kpis_anterior || null;
    const anioAnt = diasAnt[0]?.fecha_ant?.slice(0, 4) ?? String(vY - 1);
    // Un mes es proyecci?n si no tiene ventas reales (puede tener feriados con bultos=0)
    const tieneVentas = diasData.some(d => (d.bultos || 0) > 0 || (d.hectolitros || 0) > 0);
    const esProyeccion = !tieneVentas && diasAnt.length > 0;

    if (esProyeccion) {
      // Indexar feriados/eventos del mes actual para superponerlos en el calendario
      const feriadosActuales = {};
      diasData.forEach(d => { if (d.es_feriado || d.es_evento) feriadosActuales[d.fecha] = d; });
      // Mes futuro sin ventas: usar a?o anterior como proyecci?n de referencia
      diasData = diasAnt.map(d => {
        const fechaActual = d.fecha_ant.replace(/^\d{4}/, String(vY));
        const fer = feriadosActuales[fechaActual] || {};
        return {
          fecha:           fechaActual,
          fecha_ant:       d.fecha_ant,
          bultos:          d.bultos,
          hectolitros:     d.hectolitros,
          pallets:         d.pallets ?? 0,
          up:              d.up ?? 0,
          pedidos:         d.pedidos ?? 0,
          importe:         d.importe ?? 0,
          camiones_salidos: d.camiones_salidos ?? 0,
          clientes_unicos: d.clientes,
          nds:             d.nds,
          metrica_val:     d.metrica_val,
          ausentismo:      0,
          es_pico:         d.es_pico,
          es_feriado:      fer.es_feriado  ?? false,
          feriado_desc:    fer.feriado_desc ?? '',
          feriado_tipo:    fer.feriado_tipo ?? '',
          es_evento:       fer.es_evento   ?? false,
          evento_desc:     fer.evento_desc  ?? '',
          es_proyeccion:   true,
          dot:             { tiene_datos: false },
          rechazo_bultos: d.rechazo_bultos ?? 0,
          rechazo_bultos_parcial: d.rechazo_bultos_parcial ?? 0,
          rechazo_bultos_total: d.rechazo_bultos_total ?? 0,
          rechazo_hl: d.rechazo_hl ?? 0,
          rechazo_hl_parcial: d.rechazo_hl_parcial ?? 0,
          rechazo_hl_total: d.rechazo_hl_total ?? 0,
          rechazo_pedidos: d.rechazo_pedidos ?? 0,
          rmcyo_bultos: d.rmcyo_bultos ?? 0,
          rmcyo_hl: d.rmcyo_hl ?? 0,
          rmcyo_pedidos: d.rmcyo_pedidos ?? 0,
          rmcyo_rechazo_bultos: d.rmcyo_rechazo_bultos ?? 0,
          rmcyo_rechazo_hl: d.rmcyo_rechazo_hl ?? 0,
          rmcyo_rechazo_pedidos: d.rmcyo_rechazo_pedidos ?? 0,
          pct_rechazo_bultos: d.pct_rechazo_bultos ?? 0,
          pct_rechazo_hl: d.pct_rechazo_hl ?? 0,
          pct_rechazo_pedidos: d.pct_rechazo_pedidos ?? 0,
        };
      });
    }
    picoSet = new Set(diasData.filter(d => d.es_pico).map(d => d.fecha));
    renderCal();

    // Sidebar stats
    const k = data.kpis || {};
    const camionesSheets = diasData.reduce((s,d)=>s+(d.dot?.tiene_datos?d.dot.total_camiones:0),0);
    if (!esProyeccion && camionesSheets > 0) k.camiones = camionesSheets;
    mesKpis = (esProyeccion && kAnt) ? kAnt : k;
    document.getElementById('sPicos').textContent     = esProyeccion
      ? diasData.filter(d => d.es_pico).length
      : (data.picos_count ?? diasData.filter(d => d.es_pico).length);
    document.getElementById('sMetricLbl').textContent = metricSummaryLabel(m);
    document.getElementById('sMetricVal').textContent = (esProyeccion && kAnt)
      ? metricSummaryValue(kAnt, m)
      : metricSummaryValue(k, m);
    document.getElementById('sCamiones').textContent  = (esProyeccion && kAnt)
      ? fmtN(kAnt.camiones ?? 0)
      : fmtN(k.camiones ?? 0);
    document.getElementById('sClientes').textContent  = (esProyeccion && kAnt)
      ? fmtN(kAnt.clientes ?? 0)
      : fmtN(k.clientes ?? 0);
    // Próximos feriados / eventos
    document.getElementById('sUmbral').textContent    = data.umbral_val;

    // Próximos feriados / eventos
    const proximos = data.proximos_eventos || (data.proximo_feriado ? [data.proximo_feriado] : []);
    const pfBox = document.getElementById('proximoFeriadoBox');
    const pfList = document.getElementById('sPfList');
    if (proximos.length && pfBox && pfList) {
      pfBox.style.display = '';
      pfList.innerHTML = proximos.slice(0, 3).map(item => {
        const dias = Number(item.dias_restantes ?? 0);
        const diasTxt = dias === 0 ? 'HOY' : dias === 1 ? 'mañana' : `${dias} días`;
        const color = dias <= 3 ? 'var(--red)' : dias <= 7 ? 'var(--acc)' : 'var(--grn)';
        const origen = item.origen === 'evento' ? 'evento' : 'feriado';
        const scope = item.origen === 'evento' && item.sucursal && item.sucursal !== 'TODAS'
          ? ` · ${item.sucursal}`
          : item.tipo === 'local'
            ? ' · local'
            : item.origen === 'feriado'
              ? ' · nacional'
              : '';
        return `<div style="border-top:1px solid rgba(255,255,255,.08);padding-top:7px">
          <div style="display:flex;align-items:flex-start;gap:8px">
            <div style="font-size:18px;font-weight:700;font-family:var(--mono);color:${color};min-width:58px">${esc(diasTxt)}</div>
            <div style="min-width:0">
              <div style="font-size:10px;color:var(--muted);font-family:var(--mono)">${esc(item.fecha)} · ${esc(origen)}${esc(scope)}</div>
              <div style="font-size:11px;color:var(--txt);font-weight:600;line-height:1.25;margin-top:2px">${esc(item.descripcion)}</div>
            </div>
          </div>
        </div>`;
      }).join('');
    } else if (pfBox) {
      pfBox.style.display = 'none';
    }

    // KPIs y tabla de días
    renderKpiGrid((esProyeccion && kAnt) ? _kpiProyeccion(kAnt) : k);
    if (esProyeccion && kAnt) {
      const banner = document.createElement('div');
      banner.style.cssText = 'background:rgba(245,166,35,.12);border:1px solid rgba(245,166,35,.38);border-radius:6px;padding:8px 12px;margin-bottom:12px;font-size:11px;color:var(--acc)';
      banner.textContent = `\u{1f52e} Proyecci\u00f3n basada en ${MESES[vM]} ${anioAnt} y los d\u00edas marcados como PICO lo fueron ese a\u00f1o`;
      const grid = document.getElementById('kpiGrid');
      grid.insertBefore(banner, grid.firstChild);
    }
    renderTablaDias();
    renderRechazoPctCharts();
  } catch (e) {
    if (e.name === 'AbortError') return;
    errBox('kpiGrid', 'Error al cargar datos: ' + e.message);
    destroyRechazoPctCharts();
    document.getElementById('sPicos').textContent = 'ERR';
  }
}

function kpiMetricCard(label, value, color = 'grn', badge = '', valueStyle = '') {
  const styleAttr = valueStyle ? ` style="${valueStyle}"` : '';
  return `<div class="kpi ${color}"><div class="kpi-lbl">${esc(label)}</div><div class="kpi-val ${color}"${styleAttr}>${value}</div>${badge}</div>`;
}

function kpiBand(title, tone, cards, spanAll = false) {
  const items = (cards || []).filter(Boolean);
  if (!items.length) return '';
  return `<div class="kpi-band ${tone}${spanAll ? ' span-all' : ''}">
    <div class="kpi-band-head">
      <span class="kpi-band-title">${esc(title)}</span>
      <span class="kpi-band-meta">${items.length} indicadores</span>
    </div>
    <div class="kpi-band-grid">${items.join('')}</div>
  </div>`;
}

function kpiGroup(title, bands) {
  const content = (bands || []).filter(Boolean).join('');
  if (!content) return '';
  return `<section class="kpi-group">
    <div class="kpi-section">${esc(title)}</div>
    <div class="kpi-group-body">${content}</div>
  </section>`;
}

function renderKpiGridLegacy(d) {
  renderKpiGrid(d);
}

function renderKpiGrid(d) {
  const groups = [
    kpiGroup('Bultos', [
      kpiBand('Positivos', 'good', [
        kpiMetricCard('Bultos despachados', fmtN(Math.round(d.bultos ?? 0)), 'grn'),
        kpiMetricCard('RMCYO bultos', fmtN(Math.round(d.rmcyo_bultos ?? 0)), 'grn'),
      ]),
      kpiBand('Rechazos', 'bad', [
        kpiMetricCard('Bultos rechazados', fmt1(d.rechazo_bultos ?? 0), 'red'),
        kpiMetricCard('% rechazo bultos', fmtPct1(d.pct_rechazo_bultos ?? 0), 'red', kpiGoalBadge(d.objetivos?.pct_rechazo_bultos)),
        kpiMetricCard('Bultos con rechazo parcial', fmt1(d.rechazo_bultos_parcial ?? 0), 'red'),
        kpiMetricCard('Bultos con rechazo completo', fmt1(d.rechazo_bultos_total ?? 0), 'red'),
        kpiMetricCard('RMCYO bultos rechazados', fmt1(d.rmcyo_rechazo_bultos ?? 0), 'red'),
        kpiMetricCard('% RMCYO rechazo bultos', fmtPct1(d.rmcyo_pct_rechazo_bultos ?? 0), 'red', kpiGoalBadge(d.objetivos?.rmcyo_pct_rechazo_bultos)),
      ]),
    ]),
    kpiGroup('Hectolitros', [
      kpiBand('Positivos', 'good', [
        kpiMetricCard('HL despachados', fmtN(Math.round(d.hectolitros ?? 0)), 'grn'),
        kpiMetricCard('RMCYO HL', fmtN(Math.round(d.rmcyo_hl ?? 0)), 'grn'),
      ]),
      kpiBand('Rechazos', 'bad', [
        kpiMetricCard('HL rechazados', fmt1(d.rechazo_hl ?? 0), 'red'),
        kpiMetricCard('% rechazo HL', fmtPct1(d.pct_rechazo_hl ?? 0), 'red', kpiGoalBadge(d.objetivos?.pct_rechazo_hl)),
        kpiMetricCard('HL con rechazo parcial', fmt1(d.rechazo_hl_parcial ?? 0), 'red'),
        kpiMetricCard('HL con rechazo completo', fmt1(d.rechazo_hl_total ?? 0), 'red'),
        kpiMetricCard('RMCYO HL rechazados', fmt1(d.rmcyo_rechazo_hl ?? 0), 'red'),
        kpiMetricCard('% RMCYO rechazo HL', fmtPct1(d.rmcyo_pct_rechazo_hl ?? 0), 'red', kpiGoalBadge(d.objetivos?.rmcyo_pct_rechazo_hl)),
      ]),
    ]),
    kpiGroup('PDV', [
      kpiBand('Positivos', 'good', [
        kpiMetricCard('PDV atendidos', fmtN(d.pedidos ?? 0), 'grn'),
        kpiMetricCard('PDV únicos', fmtN(d.clientes ?? 0), 'grn'),
        kpiMetricCard('RMCYO PDV', fmtN(d.rmcyo_pedidos ?? 0), 'grn'),
      ]),
      kpiBand('Rechazos', 'bad', [
        kpiMetricCard('PDV rechazados', fmtN(d.rechazo_pedidos ?? 0), 'red'),
        kpiMetricCard('% rechazo PDV', fmtPct1(d.pct_rechazo_pedidos ?? 0), 'red', kpiGoalBadge(d.objetivos?.pct_rechazo_pedidos)),
        kpiMetricCard('RMCYO PDV rechazados', fmtN(d.rmcyo_rechazo_pedidos ?? 0), 'red'),
        kpiMetricCard('% RMCYO rechazo PDV', fmtPct1(d.rmcyo_pct_rechazo_pedidos ?? 0), 'red', kpiGoalBadge(d.objetivos?.rmcyo_pct_rechazo_pedidos)),
      ]),
    ]),
    kpiGroup('Pallets y UP', [
      kpiBand('Positivos', 'good', [
        kpiMetricCard('Pallets', fmtN(Math.round(d.pallets ?? 0)), 'grn'),
        kpiMetricCard('UP', fmtN(Math.round(d.up ?? 0)), 'grn'),
      ], true),
    ]),
    kpiGroup('Operación', [
      kpiBand('Positivos', 'good', [
        kpiMetricCard('Importe total', fmtM(d.importe), 'grn', '', 'font-size:15px'),
        kpiMetricCard('Salidas de camiones', fmtN(d.camiones ?? 0), 'grn'),
        kpiMetricCard('Días con datos', fmtN(d.dias ?? 0), 'grn'),
      ], true),
    ]),
  ];
  document.getElementById('kpiGrid').innerHTML = groups.join('');
}

function _renderTablaDiasProyeccion() {
  const anioAnt = diasData[0]?.fecha_ant?.slice(0, 4) ?? (vY - 1);
  const totalBultos = diasData.reduce((s, d) => s + (d.bultos || 0), 0);
  const totalHl     = diasData.reduce((s, d) => s + (d.hectolitros || 0), 0);
  const totalPicos  = diasData.filter(d => d.es_pico).length;
  let html = `<div style="background:rgba(245,166,35,.12);border:1px solid rgba(245,166,35,.38);border-radius:6px;padding:8px 12px;margin-bottom:10px;font-size:12px;color:var(--acc)">
    🔮 Proyección basada en <strong>${MESES[vM]} ${anioAnt}</strong> y los días marcados como PICO lo fueron ese año
  </div>
  <div style="overflow-x:auto"><table class="rtbl"><thead><tr>
    <th>Fecha ${vY}</th>
    <th>Bultos (${anioAnt})</th>
    <th>HL (${anioAnt})</th>
    <th>PDV únicos (${anioAnt})</th>
    <th>NDS</th>
    <th>Pico</th>
  </tr></thead><tbody>`;
  diasData.forEach(d => {
    const tagPico = d.es_pico
      ? '<span class="tag pico">PICO</span>'
      : '<span class="tag ok">Normal</span>';
    html += `<tr${d.es_pico ? ' style="background:rgba(245,166,35,.07)"' : ''}>
      <td>${d.fecha}</td>
      <td style="font-family:var(--mono);text-align:right">${fmtN(Math.round(d.bultos || 0))}</td>
      <td style="font-family:var(--mono);text-align:right">${fmt1(d.hectolitros || 0)}</td>
      <td style="font-family:var(--mono);text-align:right">${fmtN(d.clientes_unicos || 0)}</td>
      <td style="font-family:var(--mono);text-align:right">${fmt1(d.nds)}%</td>
      <td>${tagPico}</td>
    </tr>`;
  });
  html += `<tr style="background:var(--surf3);font-weight:700">
    <td>TOTAL</td>
    <td style="font-family:var(--mono);text-align:right;color:var(--grn)">${fmtN(Math.round(totalBultos))}</td>
    <td style="font-family:var(--mono);text-align:right;color:var(--grn)">${fmt1(totalHl)}</td>
    <td></td><td></td>
    <td style="color:var(--acc)">${totalPicos} pico${totalPicos !== 1 ? 's' : ''}</td>
  </tr></tbody></table></div>`;
  document.getElementById('tablaDias').innerHTML = html;
}

function renderTablaDias() {
  if (!diasData.length) {
    document.getElementById('tablaDias').innerHTML = '<div class="empty"><div class="icon">📅</div>Sin datos para este mes</div>';
    return;
  }
  if (diasData[0]?.es_proyeccion) { _renderTablaDiasProyeccion(); return; }
  let html = `<table class="rtbl"><thead><tr>
    <th>Fecha</th><th>Bultos</th><th>HL</th><th>Pallets</th><th>UP</th><th>PDV atendidos</th><th>PDV únicos</th>
    <th>NDS</th><th>Ausentismo</th>
    <th>% rechazo PDV</th><th>% rechazo blt.</th><th>% rechazo HL</th><th>Salidas</th>
    <th>Dot. S1</th><th>Dot. S2</th>
    <th>Pico</th><th>Feriado</th><th>Evento</th>
  </tr></thead><tbody>`;
  diasData.forEach(d => {
    const tagPico    = d.es_pico
      ? `<span class="tag pico">PICO</span>`
      : `<span class="tag ok">Normal</span>`;
    const tagFeriado = d.es_feriado
      ? (() => {
          const t = (d.feriado_tipo || '').toLowerCase();
          const lbl = t === 'nacional'    ? 'Feriado AR'
                    : t === 'inamovible'  ? 'Feriado AR'
                    : t === 'puente'      ? 'Puente'
                    : t === 'trasladable' ? 'Trasladable'
                    : 'Feriado AR';
          return `<span class="tag fer" title="${d.feriado_desc || ''}">${lbl}</span>`;
        })()
      : `<span style="color:var(--muted);font-size:11px">?</span>`;
    const tagEvento  = d.es_evento
      ? `<span class="tag evento" title="${d.evento_desc || ''}">? Evento</span>`
      : `<span style="color:var(--muted);font-size:11px">?</span>`;
    html += `<tr style="cursor:pointer" onclick="selectDay('${d.fecha}')">
      <td style="font-family:var(--mono)">${d.fecha}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(d.bultos))}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(d.hectolitros))}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(d.pallets || 0))}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(d.up || 0))}</td>
      <td style="font-family:var(--mono)">${fmtN(d.pedidos)}</td>
      <td style="font-family:var(--mono)">${fmtN(d.clientes_unicos || 0)}</td>
      <td style="font-family:var(--mono);font-weight:${(d.nds ?? 100) < 85 ? '700' : '400'};color:${(d.nds ?? 100) < 85 ? 'var(--red)' : (d.nds ?? 100) < 95 ? 'var(--acc)' : 'var(--grn)'}">${d.nds ?? 100}%</td>
      <td style="font-family:var(--mono);color:${(d.ausentismo || 0) >= 3 ? 'var(--red)' : (d.ausentismo || 0) > 0 ? 'var(--acc)' : 'var(--muted)'}">${d.ausentismo || 0}</td>
      <td style="font-family:var(--mono);color:${(d.pct_rechazo_pedidos ?? 0) > 5 ? 'var(--red)' : 'var(--grn)'}">${d.pct_rechazo_pedidos ?? 0}%</td>
      <td style="font-family:var(--mono);color:${(d.pct_rechazo_bultos ?? 0) > 5 ? 'var(--red)' : 'var(--grn)'}">${d.pct_rechazo_bultos ?? 0}%</td>
      <td><span class="pct-pill ${(d.pct_rechazo_hl ?? 0) > 5 ? 'bad' : 'ok'}">${fmtPct1(d.pct_rechazo_hl ?? 0)}</span></td>
      <td style="font-family:var(--mono)">${d.dot?.tiene_datos ? d.dot.total_camiones : d.camiones_salidos}</td>
      <td style="font-family:var(--mono)">${d.dot?.s1 ? `${d.dot.s1.personas}p` : '<span style="color:var(--muted)">?</span>'}</td>
      <td style="font-family:var(--mono)">${d.dot?.tiene_s2 ? `<span style="color:var(--grn);font-weight:600">${d.dot.s2?.personas ?? 0}p</span>` : '<span style="color:var(--muted)">?</span>'}</td>
      <td>${tagPico}</td>
      <td>${tagFeriado}</td>
      <td>${tagEvento}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('tablaDias').innerHTML = html;
}

function destroyRechazoPctCharts() {
  Object.values(rechazoPctCharts || {}).forEach(chart => {
    if (chart && typeof chart.destroy === 'function') chart.destroy();
  });
  rechazoPctCharts = {};
}

function renderRechazoPctCharts() {
  const cont = document.getElementById('rechazoPctCharts');
  if (!cont) return;
  destroyRechazoPctCharts();
  if (!window.Chart || !diasData.length || diasData[0]?.es_proyeccion) {
    cont.style.display = 'none';
    return;
  }
  cont.style.display = 'grid';

  const labels = diasData.map(d => String(d.fecha || '').slice(8, 10));
  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    layout: { padding: { top: 10, right: 6, bottom: 0, left: 0 } },
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: items => {
            const idx = items?.[0]?.dataIndex ?? 0;
            return diasData[idx]?.fecha || '';
          },
          label: ctx => `${ctx.dataset.label}: ${fmtPct1(ctx.parsed.y || 0)}`,
        },
      },
      chartValueLabels: { hideZero: true },
    },
    scales: {
      x: {
        ticks: { color: '#9aa4b2', maxRotation: 0, autoSkip: true, maxTicksLimit: 10 },
        grid: { display: false },
      },
      y: {
        beginAtZero: true,
        ticks: { color: '#9aa4b2', callback: value => `${value}%` },
        grid: { color: 'rgba(255,255,255,.07)' },
      },
    },
  };

  const configs = [
    { id: 'rechazoPdvChart', key: 'pct_rechazo_pedidos', label: '% rechazo PDV', color: '#e05c5c' },
    { id: 'rechazoBultosChart', key: 'pct_rechazo_bultos', label: '% rechazo bultos', color: '#f5a623' },
    { id: 'rechazoHlChart', key: 'pct_rechazo_hl', label: '% rechazo HL', color: '#a78bfa' },
  ];

  configs.forEach(cfg => {
    const el = document.getElementById(cfg.id);
    if (!el) return;
    rechazoPctCharts[cfg.id] = new Chart(el.getContext('2d'), {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: cfg.label,
          data: diasData.map(d => Number(d[cfg.key] || 0)),
          borderColor: cfg.color,
          backgroundColor: `${cfg.color}22`,
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: .25,
          fill: true,
          valueFormatter: raw => fmtPct1(raw || 0),
        }],
      },
      plugins: [chartValueLabels],
      options: baseOptions,
    });
  });
}

async function selectDay(k) {
  selDay = k;
  renderCal();
  openDrawer(k);
}

// // ? HIST?RICO ────────────────────────────────────────────────
async function loadHistorico() {
  const seq = ++_loadHistSeq;
  if (_histAbort) _histAbort.abort();
  _histAbort = new AbortController();

  if (historicoChart) {
    historicoChart.destroy();
    historicoChart = null;
  }
  if (historicoPicosChart) {
    historicoPicosChart.destroy();
    historicoPicosChart = null;
  }
  if (historicoVolumenChart) {
    historicoVolumenChart.destroy();
    historicoVolumenChart = null;
  }
  load('barHistorico'); load('picosAnualHistorico'); load('tablaHistorico');
  const nValue = document.getElementById('selPeriodoHist').value;
  const n = Number(nValue || 0);
  const suc = getSuc();
  const m = document.getElementById('selMetrica').value;
  const u = document.getElementById('sliderUmbral').value;
  try {
    const fetchMonths = Math.max(24, n || 0);
    const data  = await api(`/api/picos/historico?sucursal=${encodeURIComponent(suc)}&meses=${fetchMonths}&umbral=${u}&metrica=${m}`, { signal: _histAbort.signal });
    if (seq !== _loadHistSeq || suc !== getSuc() || nValue !== document.getElementById('selPeriodoHist').value || m !== document.getElementById('selMetrica').value || u !== document.getElementById('sliderUmbral').value) return;
    const meses = data.meses || [];
    const visibles = n > 0 && n < meses.length ? meses.slice(-n) : meses;
    if (!meses.length) {
      document.getElementById('barHistorico').innerHTML = '<div class="empty"><div class="icon">📊</div>Sin datos históricos</div>';
      document.getElementById('tablaHistorico').innerHTML = '<div class="empty"><div class="icon">📋</div>Sin datos para la tabla</div>';
      await loadHistoricoPicosAnual(seq, suc, m, u, meses);
      await loadHistoricoVolumenAnual(seq, suc, m, u, meses);
      return;
    }
    document.getElementById('barHistorico').innerHTML = '<div class="chart-wrap" style="height:280px"><canvas id="histChart"></canvas></div>';
    historicoChart = renderHistoricoChart(
      visibles.map(x => x.mes.slice(2)),
      visibles.map(x => Number(x[m] || 0)),
      m,
      visibles.map(x => Number(x.dias_pico || 0))
    );
    await loadHistoricoPicosAnual(seq, suc, m, u, meses);
    await loadHistoricoVolumenAnual(seq, suc, m, u, meses);

    let html = `<table class="rtbl"><thead><tr>
      <th>Mes</th><th>Bultos</th><th>HL</th><th>Pallets</th><th>UP</th><th>PDV atendidos</th><th>PDV únicos</th>
      <th>% rechazo PDV</th><th>% rechazo blt.</th><th>% rechazo HL</th><th>Salidas</th><th>Días</th><th>Días pico</th>
    </tr></thead><tbody>`;
    visibles.forEach(x => {
      const picoTitle = `Métrica: ${metricSummaryLabel(x.metrica_pico || m)} | Prom.: ${fmtN(Math.round(x.promedio_pico || 0))} | Umbral: ${fmtN(Math.round(x.umbral_pico || 0))}`;
      html += `<tr>
        <td style="font-family:var(--mono)">${x.mes}</td>
        <td style="font-family:var(--mono)">${fmtN(Math.round(x.bultos))}</td>
        <td style="font-family:var(--mono)">${fmtN(Math.round(x.hectolitros))}</td>
        <td style="font-family:var(--mono)">${fmtN(Math.round(x.pallets || 0))}</td>
        <td style="font-family:var(--mono)">${fmtN(Math.round(x.up || 0))}</td>
        <td style="font-family:var(--mono)">${fmtN(x.pedidos)}</td>
        <td style="font-family:var(--mono)">${fmtN(x.clientes || 0)}</td>
        <td style="font-family:var(--mono);color:${(x.pct_rechazo_pedidos ?? 0) > 5 ? 'var(--red)' : 'var(--grn)'}">${x.pct_rechazo_pedidos ?? 0}%</td>
        <td style="font-family:var(--mono);color:${(x.pct_rechazo_bultos ?? 0) > 5 ? 'var(--red)' : 'var(--grn)'}">${x.pct_rechazo_bultos ?? 0}%</td>
        <td style="font-family:var(--mono);color:${(x.pct_rechazo_hl ?? 0) > 5 ? 'var(--red)' : 'var(--grn)'}">${x.pct_rechazo_hl ?? 0}%</td>
        <td style="font-family:var(--mono)">${x.camiones_sheets || x.camiones}</td>
        <td style="font-family:var(--mono)">${x.dias}</td>
        <td title="${esc(picoTitle)}"><span class="tag pico">${fmtN(x.dias_pico || 0)}</span></td>
      </tr>`;
    });
    html += '</tbody></table>';
    document.getElementById('tablaHistorico').innerHTML = html;
  } catch (e) { if (e.name === 'AbortError') return; errBox('barHistorico', 'Error: ' + e.message); }
}

function renderHistoricoChart(labels, values, metric, picos = []) {
  if (!window.Chart) return historicoChart;
  const el = document.getElementById('histChart');
  if (!el) return historicoChart;
  if (historicoChart) historicoChart.destroy();

  const metricColors = {
    bultos: '#f5a623',
    hectolitros: '#a78bfa',
    pallets: '#4caf82',
    up: '#5b8dee',
    pedidos: '#e05c5c',
    clientes: '#5b8dee',
  };
  const color = metricColors[metric] || '#f5a623';

  return new Chart(el.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: metricSummaryLabel(metric),
        data: values,
        borderColor: color,
        backgroundColor: color + '22',
        borderWidth: 2,
        pointRadius: 4,
        pointHoverRadius: 6,
        tension: .28,
        fill: true,
        yAxisID: 'y',
        labelColor: color,
        valueFormatter: raw => fmtN(Math.round(raw || 0)),
      }, {
        type: 'bar',
        label: 'Días pico',
        data: picos,
        borderColor: '#f5a623',
        backgroundColor: 'rgba(245,166,35,.28)',
        borderWidth: 1,
        borderRadius: 4,
        yAxisID: 'yPicos',
        labelColor: '#f5a623',
        valueFormatter: raw => fmtN(Math.round(raw || 0)),
      }],
    },
    plugins: [chartValueLabels],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 18 } },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#e8eaf0', boxWidth: 10 } },
        chartValueLabels: { hideZero: true },
        tooltip: {
          callbacks: {
            label: ctx => ctx.dataset.yAxisID === 'yPicos'
              ? `${ctx.dataset.label}: ${fmtN(Math.round(ctx.parsed.y || 0))} d?as`
              : `${ctx.dataset.label}: ${fmtN(Math.round(ctx.parsed.y || 0))}`,
          },
        },
      },
      scales: {
        x: { ticks: { color: '#6b7080', maxRotation: 0 }, grid: { color: 'rgba(42,46,58,.35)' } },
        y: {
          beginAtZero: true,
          ticks: { color: '#6b7080', callback: value => fmtN(Math.round(value)) },
          grid: { color: 'rgba(42,46,58,.35)' },
        },
        yPicos: {
          position: 'right',
          beginAtZero: true,
          suggestedMax: Math.max(5, ...picos) + 1,
          ticks: { color: '#f5a623', precision: 0 },
          grid: { drawOnChartArea: false },
        },
      },
    },
  });
}

async function loadHistoricoPicosAnual(seq, suc, metric, umbralValue, mesesBase = null) {
  const cont = document.getElementById('picosAnualHistorico');
  if (!cont) return;
  cont.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando comparación anual…</div>';
  try {
    const meses = Array.isArray(mesesBase)
      ? mesesBase
      : (await api(
          `/api/picos/historico?sucursal=${encodeURIComponent(suc)}&meses=24&umbral=${umbralValue}&metrica=${metric}`,
          { signal: _histAbort.signal }
        )).meses || [];
    if (
      seq !== _loadHistSeq ||
      suc !== getSuc() ||
      metric !== document.getElementById('selMetrica').value ||
      umbralValue !== document.getElementById('sliderUmbral').value
    ) return;
    if (!meses.length) {
      cont.innerHTML = '<div class="empty"><div class="icon">📈</div>Sin datos para comparar años</div>';
      return;
    }
    cont.innerHTML = '<div class="chart-wrap" style="height:260px"><canvas id="histPicosChart"></canvas></div>';
    historicoPicosChart = renderHistoricoPicosAnualChart(meses);
  } catch (e) {
    if (e.name === 'AbortError') return;
    errBox('picosAnualHistorico', 'Error al cargar comparación anual: ' + e.message);
  }
}

function buildHistoricoAnualComparison(meses, metric) {
  const years = [...new Set((meses || []).map(x => Number(String(x.mes).slice(0, 4))).filter(Boolean))].sort((a, b) => a - b);
  if (years.length < 2) return null;
  const anioActual = years[years.length - 1];
  const anioAnterior = years.includes(anioActual - 1) ? anioActual - 1 : years[years.length - 2];
  const prev = Array(12).fill(null);
  const curr = Array(12).fill(null);

  (meses || []).forEach(x => {
    const [yy, mm] = String(x.mes || '').split('-').map(Number);
    if (!yy || !mm || mm < 1 || mm > 12) return;
    const value = Number(x[metric] || 0);
    if (yy === anioAnterior) prev[mm - 1] = value;
    if (yy === anioActual) curr[mm - 1] = value;
  });

  return { anioAnterior, anioActual, prev, curr };
}

async function loadHistoricoVolumenAnual(seq, suc, metric, umbralValue, mesesBase = null) {
  const cont = document.getElementById('volumenAnualHistorico');
  if (!cont) return;
  const meta = document.getElementById('volumenAnualMeta');
  if (meta) meta.textContent = `Métrica: ${metricSummaryLabel(metric)}`;
  cont.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando... comparación anual...</div>';
  try {
    const meses = Array.isArray(mesesBase)
      ? mesesBase
      : (await api(
          `/api/picos/historico?sucursal=${encodeURIComponent(suc)}&meses=24&umbral=${umbralValue}&metrica=${metric}`,
          { signal: _histAbort.signal }
        )).meses || [];
    if (
      seq !== _loadHistSeq ||
      suc !== getSuc() ||
      metric !== document.getElementById('selMetrica').value ||
      umbralValue !== document.getElementById('sliderUmbral').value
    ) return;
    const comp = buildHistoricoAnualComparison(meses, metric);
    if (!comp) {
      cont.innerHTML = '<div class="empty"><div class="icon">📈</div>Sin datos suficientes para comparar años</div>';
      return;
    }
    cont.innerHTML = '<div class="chart-wrap" style="height:260px"><canvas id="histVolumenChart"></canvas></div>';
    historicoVolumenChart = renderHistoricoVolumenAnualChart(comp, metric);
  } catch (e) {
    if (e.name === 'AbortError') return;
    errBox('volumenAnualHistorico', 'Error al cargar comparación anual: ' + e.message);
  }
}

function renderHistoricoVolumenAnualChart(comp, metric) {
  if (!window.Chart) return historicoVolumenChart;
  const el = document.getElementById('histVolumenChart');
  if (!el) return historicoVolumenChart;
  if (historicoVolumenChart) historicoVolumenChart.destroy();

  const maxVal = Math.max(5, ...comp.prev.filter(v => v != null), ...comp.curr.filter(v => v != null));
  const metricLabel = metricSummaryLabel(metric);

  return new Chart(el.getContext('2d'), {
    type: 'line',
    data: {
      labels: MES_CORTO,
      datasets: [{
        label: `${metricLabel} ${comp.anioAnterior}`,
        data: comp.prev,
        borderColor: '#5b8dee',
        backgroundColor: 'rgba(91,141,238,.15)',
        pointBackgroundColor: '#5b8dee',
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
        tension: .25,
        spanGaps: true,
        labelColor: '#8fb3ff',
        valueFormatter: raw => fmtN(Math.round(raw || 0)),
      }, {
        label: `${metricLabel} ${comp.anioActual}`,
        data: comp.curr,
        borderColor: '#f5a623',
        backgroundColor: 'rgba(245,166,35,.16)',
        pointBackgroundColor: '#f5a623',
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
        tension: .25,
        spanGaps: true,
        labelColor: '#f5a623',
        valueFormatter: raw => fmtN(Math.round(raw || 0)),
      }],
    },
    plugins: [chartValueLabels],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 20 } },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#e8eaf0', boxWidth: 10 } },
        chartValueLabels: { hideZero: false },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${fmtN(Math.round(ctx.parsed.y || 0))}`,
          },
        },
      },
      scales: {
        x: { ticks: { color: '#6b7080' }, grid: { color: 'rgba(42,46,58,.35)' } },
        y: {
          beginAtZero: true,
          suggestedMax: maxVal + 1,
          ticks: { color: '#6b7080', callback: value => fmtN(Math.round(value)) },
          grid: { color: 'rgba(42,46,58,.35)' },
        },
      },
    },
  });
}

function renderHistoricoPicosAnualChart(meses) {
  if (!window.Chart) return historicoPicosChart;
  const el = document.getElementById('histPicosChart');
  if (!el) return historicoPicosChart;
  if (historicoPicosChart) historicoPicosChart.destroy();

  const anios = [...new Set((meses || []).map(x => Number(String(x.mes).slice(0, 4))).filter(Boolean))];
  if (!anios.length) return historicoPicosChart;
  const anioActual = Math.max(...anios);
  const anioAnterior = anioActual - 1;
  const byYearMonth = {};
  meses.forEach(x => {
    const [yy, mm] = String(x.mes).split('-').map(Number);
    if (!yy || !mm) return;
    byYearMonth[`${yy}-${mm}`] = Number(x.dias_pico || 0);
  });
  const prevFull = Array.from({ length: 12 }, (_, i) => byYearMonth[`${anioAnterior}-${i + 1}`] ?? null);
  const currFull = Array.from({ length: 12 }, (_, i) => byYearMonth[`${anioActual}-${i + 1}`] ?? null);
  const labels = MES_CORTO;
  const prev = prevFull;
  const curr = currFull;
  const maxPicos = Math.max(5, ...prev.filter(v => v != null), ...curr.filter(v => v != null));

  return new Chart(el.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: `Días pico a?o anterior (${anioAnterior})`,
        data: prev,
        borderColor: '#5b8dee',
        backgroundColor: 'rgba(91,141,238,.15)',
        pointBackgroundColor: '#5b8dee',
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
        tension: .25,
        spanGaps: true,
        labelColor: '#8fb3ff',
        valueFormatter: raw => fmtN(Math.round(raw || 0)),
      }, {
        label: `Días pico a?o actual (${anioActual})`,
        data: curr,
        borderColor: '#f5a623',
        backgroundColor: 'rgba(245,166,35,.16)',
        pointBackgroundColor: '#f5a623',
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
        tension: .25,
        spanGaps: true,
        labelColor: '#f5a623',
        valueFormatter: raw => fmtN(Math.round(raw || 0)),
      }],
    },
    plugins: [chartValueLabels],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 20 } },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#e8eaf0', boxWidth: 10 } },
        chartValueLabels: { hideZero: false },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${fmtN(Math.round(ctx.parsed.y || 0))} d?as`,
          },
        },
      },
      scales: {
        x: { ticks: { color: '#6b7080' }, grid: { color: 'rgba(42,46,58,.35)' } },
        y: {
          beginAtZero: true,
          suggestedMax: maxPicos + 1,
          ticks: { color: '#6b7080', precision: 0 },
          grid: { color: 'rgba(42,46,58,.35)' },
        },
      },
    },
  });
}

function ventaDiaFormat(metric, value) {
  if (value == null || Number.isNaN(Number(value))) return '?';
  if (metric === 'pallets') return fmtDrop(value);
  if (metric === 'hectolitros') return fmt1(value);
  if (metric === 'salidas') return fmtN(Math.round(value));
  return fmtN(Math.round(value));
}

function ventaDiaHeatmapIntFormat(value) {
  if (value == null || Number.isNaN(Number(value))) return '?';
  return fmtN(Math.round(value));
}

function ventaDiaHeatmapMetricLabel(metric) {
  return ({
    hectolitros: 'Hectolitros',
    salidas: 'Salidas',
    bultos: 'Bultos',
    pallets: 'Pallets',
    personas: 'Personas',
  })[metric] || 'Hectolitros';
}


function getIsoWeekInfo(date = new Date()) {
  const target = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = target.getUTCDay() || 7;
  target.setUTCDate(target.getUTCDate() + 4 - dayNum);
  const isoYear = target.getUTCFullYear();
  const yearStart = new Date(Date.UTC(isoYear, 0, 1));
  const week = Math.ceil((((target - yearStart) / 86400000) + 1) / 7);
  return { year: isoYear, week };
}

function initVentaDiaFilters() {
  const periodo = document.getElementById('ventaDiaPeriodo');
  if (periodo && !periodo.dataset.init) {
    periodo.value = 'rango';
    periodo.dataset.init = '1';
  }

  const hoy = new Date();
  const year = hoy.getFullYear();
  const hoyIso = `${year}-${String(hoy.getMonth() + 1).padStart(2, '0')}-${String(hoy.getDate()).padStart(2, '0')}`;
  const yearStartIso = `${year}-01-01`;
  const iso = getIsoWeekInfo(hoy);
  const anio = document.getElementById('ventaDiaAnio');
  if (anio && !anio.value) anio.value = iso.year;

  const mes = document.getElementById('ventaDiaMes');
  if (mes && !mes.value) mes.value = mesPad();

  const semana = document.getElementById('ventaDiaSemana');
  if (semana && !semana.value) semana.value = iso.week;

  const desde = document.getElementById('ventaDiaDesde');
  if (desde && !desde.value) desde.value = yearStartIso;

  const hasta = document.getElementById('ventaDiaHasta');
  if (hasta && !hasta.value) hasta.value = hoyIso;

  updateVentaDiaPeriodoUI();
}

function syncVentaDiaMonthFilter() {
  const mesEl = document.getElementById('ventaDiaMes');
  if (!mesEl) return '';
  if (!/^\d{4}-\d{2}$/.test(mesEl.value || '')) {
    mesEl.value = mesPad();
  }
  return mesEl.value;
}

function updateVentaDiaFilterHint() {
  const box = document.getElementById('ventaDiaFilterHint');
  if (!box) return;

  const tipo = document.getElementById('ventaDiaPeriodo')?.value || 'todo';
  const anio = document.getElementById('ventaDiaAnio')?.value || getIsoWeekInfo().year;
  const semana = document.getElementById('ventaDiaSemana')?.value || getIsoWeekInfo().week;
  const mes = document.getElementById('ventaDiaMes')?.value || '';
  const desde = document.getElementById('ventaDiaDesde')?.value || '';
  const hasta = document.getElementById('ventaDiaHasta')?.value || '';
  const mesParts = mes.split('-');
  const mesLabel = mesParts.length === 2 && mesParts[0] && mesParts[1] && MESES[Number(mesParts[1]) - 1]
    ? `${MESES[Number(mesParts[1]) - 1]} ${mesParts[0]}`
    : 'mes seleccionado';
  const fmtHintDate = value => value ? value.split('-').reverse().join('/') : 'sin definir';
  const labels = {
    todo: 'Todo el histórico: usa el mes con mayor acumulado dentro del filtro activo.',
    mes: `Mes ${mesLabel}: usa el mes seleccionado y no necesita año separado.`,
    anio: `Año ISO ${anio}: compara el año completo y toma el mes con mayor acumulado para el mapa de calor.`,
    semana: `Semana ISO ${semana}: cruza la semana seleccionada con el año ISO ${anio}.`,
    rango: `Rango ${fmtHintDate(desde)} a ${fmtHintDate(hasta)}: toma el mes con mayor acumulado dentro del rango.`,
  };

  box.textContent = labels[tipo] || labels.todo;
}

function reloadVentaDiaIfVisible() {
  if (!isTabVisible('tab-venta-dia')) return;
  const periodo = document.getElementById('ventaDiaPeriodo')?.value || 'todo';
  const anio = document.getElementById('ventaDiaAnio')?.value || '';
  const semana = document.getElementById('ventaDiaSemana')?.value || '';
  const desde = document.getElementById('ventaDiaDesde')?.value || '';
  const hasta = document.getElementById('ventaDiaHasta')?.value || '';

  if (periodo === 'anio' && !anio) return;
  if (periodo === 'semana' && (!anio || !semana)) return;
  if (periodo === 'rango' && (!desde || !hasta)) return;

  loadVentaDia();
}

function updateVentaDiaPeriodoUI() {
  const tipo = document.getElementById('ventaDiaPeriodo')?.value || 'todo';
  const mapping = {
    mes: ['ventaDiaMesField'],
    anio: ['ventaDiaAnioField'],
    semana: ['ventaDiaAnioField', 'ventaDiaSemanaField'],
    rango: ['ventaDiaDesdeField', 'ventaDiaHastaField'],
    todo: [],
  };
  ['ventaDiaMesField', 'ventaDiaAnioField', 'ventaDiaSemanaField', 'ventaDiaDesdeField', 'ventaDiaHastaField'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  (mapping[tipo] || []).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = '';
  });

  if (tipo === 'mes') {
    syncVentaDiaMonthFilter();
  } else if (tipo === 'anio' || tipo === 'semana') {
    const iso = getIsoWeekInfo();
    const anio = document.getElementById('ventaDiaAnio');
    if (anio && !anio.value) anio.value = iso.year;
    const semana = document.getElementById('ventaDiaSemana');
    if (tipo === 'semana' && semana && !semana.value) semana.value = iso.week;
  }

  updateVentaDiaFilterHint();
}

function onVentaDiaPeriodoChange() {
  updateVentaDiaPeriodoUI();
  reloadVentaDiaIfVisible();
}

function onVentaDiaFilterChange() {
  updateVentaDiaFilterHint();
  reloadVentaDiaIfVisible();
}

function ventaDiaQueryParams(extra = {}) {
  const params = new URLSearchParams();
  params.set('sucursal', document.getElementById('ventaDiaSucursal')?.value || getSuc());
  params.set('umbral', document.getElementById('sliderUmbral')?.value || '1.20');
  params.set('metrica', document.getElementById('selMetrica')?.value || 'bultos');

  const periodo = document.getElementById('ventaDiaPeriodo')?.value || 'todo';
  params.set('periodo_tipo', periodo);

  if (periodo === 'mes') {
    params.set('mes', syncVentaDiaMonthFilter());
  } else if (periodo === 'anio') {
    const anio = document.getElementById('ventaDiaAnio')?.value;
    if (anio) {
      params.set('anio', anio);
      params.set('anio_comparativo', anio);
    }
  } else if (periodo === 'semana') {
    const anio = document.getElementById('ventaDiaAnio')?.value;
    const semana = document.getElementById('ventaDiaSemana')?.value;
    if (anio) {
      params.set('anio', anio);
      params.set('anio_comparativo', anio);
    }
    if (semana) params.set('semana', semana);
  } else if (periodo === 'rango') {
    const desde = document.getElementById('ventaDiaDesde')?.value;
    const hasta = document.getElementById('ventaDiaHasta')?.value;
    if (desde) params.set('desde', desde);
    if (hasta) params.set('hasta', hasta);
  }

  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });

  return params;
}

function destroyVentaDiaCharts() {
  Object.values(ventaDiaCmpCharts).forEach(ch => { if (ch) ch.destroy(); });
  Object.values(ventaDiaEvoCharts).forEach(ch => { if (ch) ch.destroy(); });
  Object.values(ventaDiaDistCharts).forEach(ch => { if (ch) ch.destroy(); });
  ventaDiaCmpCharts = {};
  ventaDiaEvoCharts = {};
  ventaDiaDistCharts = {};
}

function renderVentaDiaChart(canvasId, currentChart, config) {
  const el = document.getElementById(canvasId);
  if (!el || typeof Chart === 'undefined') return null;
  if (currentChart) currentChart.destroy();

  return new Chart(el.getContext('2d'), {
    type: config.type || 'line',
    data: {
      labels: config.labels || [],
      datasets: config.datasets || [],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      layout: { padding: { top: 8 } },
      plugins: {
        legend: {
          labels: {
            color: '#e8eaf0',
            boxWidth: 10,
            usePointStyle: !!config.usePointStyle,
          },
        },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ventaDiaFormat(config.metric, ctx.parsed.y)}`,
            title: items => {
              const label = items?.[0]?.label || '';
              return label ? [`Semana ISO ${label}`] : [];
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: '#6b7080',
            maxTicksLimit: 13,
          },
          grid: { color: 'rgba(42,46,58,.25)' },
        },
        y: {
          beginAtZero: true,
          ticks: {
            color: '#6b7080',
            callback: value => ventaDiaFormat(config.metric, value),
          },
          grid: { color: 'rgba(42,46,58,.25)' },
        },
      },
    },
  });
}

const VENTA_DIA_DONUT_COLORS = [
  '#5b8dee',
  '#4cbe8a',
  '#f2a93b',
  '#a78bfa',
  '#f87171',
  '#14b8a6',
  '#ec4899',
  '#84cc16',
];

function ventaDiaMetricBreakdown(metricData) {
  const rows = (metricData?.filas || []).filter(row => !row.es_total);
  const items = rows
    .map(row => ({
      label: row.sucursal || row.sucursal_id || '?',
      value: Number(row.total || 0),
    }))
    .filter(item => item.value > 0)
    .sort((a, b) => b.value - a.value);

  if (items.length <= 6) return items;

  const top = items.slice(0, 5);
  const others = items.slice(5).reduce((acc, item) => acc + item.value, 0);
  if (others > 0) top.push({ label: 'Otros', value: others });
  return top;
}

function renderVentaDiaDoughnut(canvasId, currentChart, metricKey, items) {
  const el = document.getElementById(canvasId);
  if (!el || typeof Chart === 'undefined') return null;
  if (currentChart) currentChart.destroy();

  const labels = items.map(item => item.label);
  const values = items.map(item => item.value);
  const colors = labels.map((_, idx) => VENTA_DIA_DONUT_COLORS[idx % VENTA_DIA_DONUT_COLORS.length]);
  const total = values.reduce((acc, v) => acc + Number(v || 0), 0);

  return new Chart(el.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderColor: 'rgba(15,23,42,.95)',
        borderWidth: 2,
        hoverOffset: 6,
        spacing: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      layout: { padding: { top: 8, bottom: 8 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              const raw = Number(ctx.raw || 0);
              const pct = total > 0 ? (raw / total) * 100 : 0;
              return `${ctx.label}: ${ventaDiaFormat(metricKey, raw)} (${fmtPct(pct)})`;
            },
          },
        },
      },
    },
  });
}

function renderVentaDiaDistribucion(data) {
  const configs = [
    ['hectolitros', 'Hectolitros', 'ventaDiaDistribucionHectolitros'],
    ['bultos', 'Bultos', 'ventaDiaDistribucionBultos'],
    ['pallets', 'Pallets', 'ventaDiaDistribucionPallets'],
  ];

  configs.forEach(([metricKey, metricLabel, boxId]) => {
    const box = document.getElementById(boxId);
    if (!box) return;

    const metricData = data?.metricas?.[metricKey];
    const items = ventaDiaMetricBreakdown(metricData);
    if (!items.length) {
      box.innerHTML = '<div class="empty"><div class="icon">📊</div>Sin datos para mostrar la distribucion</div>';
      return;
    }

    const total = items.reduce((acc, item) => acc + Number(item.value || 0), 0);
    let html = `<div class="sec" style="margin-bottom:8px">${esc(metricLabel)}</div>`;
    html += '<div class="vd-donut-shell">';
    html += `<div class="chart-wrap vd-donut-wrap"><canvas id="ventaDiaDistribucionCanvas${metricKey.charAt(0).toUpperCase() + metricKey.slice(1)}"></canvas></div>`;
    html += '<div class="vd-donut-legend">';
    items.forEach((item, idx) => {
      const color = VENTA_DIA_DONUT_COLORS[idx % VENTA_DIA_DONUT_COLORS.length];
      const pct = total > 0 ? (Number(item.value || 0) / total) * 100 : 0;
      html += `
        <div class="vd-donut-item">
          <span class="vd-donut-swatch" style="background:${color}"></span>
          <span class="vd-donut-name">${esc(item.label)}</span>
          <span class="vd-donut-value">${ventaDiaFormat(metricKey, item.value)} | ${fmtPct(pct)}</span>
        </div>
      `;
    });
    html += '</div></div>';
    box.innerHTML = html;

    const canvasId = `ventaDiaDistribucionCanvas${metricKey.charAt(0).toUpperCase() + metricKey.slice(1)}`;
    ventaDiaDistCharts[metricKey] = renderVentaDiaDoughnut(canvasId, ventaDiaDistCharts[metricKey], metricKey, items);
  });
}

function renderVentaDiaTable(metricKey, metricLabel, metricData) {
  const filas = metricData?.filas || [];
  const total = metricData?.total || null;
  if (!filas.length) {
    return `<div class="empty"><div class="icon">📉</div>Sin datos para ${esc(metricLabel).toLowerCase()}</div>`;
  }

  const dias = (ventaDiaData?.dias_semana || []).map(d => d.label || '');
  let html = `<div class="sec" style="margin-bottom:10px">${esc(metricLabel)}</div>`;
  html += '<div style="overflow-x:auto"><table class="rtbl"><thead><tr><th>Sucursal</th>';
  dias.forEach(dia => { html += `<th style="text-align:right">${esc(dia)}</th>`; });
  html += '<th style="text-align:right">Total</th></tr></thead><tbody>';

  filas.forEach(row => {
    html += `<tr>
      <td>${esc(row.sucursal || row.sucursal_id || '?')}</td>
      ${(row.dias || []).map(v => `<td style="font-family:var(--mono);text-align:right">${ventaDiaFormat(metricKey, v)}</td>`).join('')}
      <td style="font-family:var(--mono);text-align:right;font-weight:600">${ventaDiaFormat(metricKey, row.total)}</td>
    </tr>`;
  });

  if (total) {
    html += `<tr style="background:rgba(238,242,255,.38);font-weight:700">
      <td>Total</td>
      ${(total.dias || []).map(v => `<td style="font-family:var(--mono);text-align:right">${ventaDiaFormat(metricKey, v)}</td>`).join('')}
      <td style="font-family:var(--mono);text-align:right">${ventaDiaFormat(metricKey, total.total)}</td>
    </tr>`;
  }

  html += '</tbody></table></div>';
  return html;
}

function renderVentaDiaCharts(data) {
  const comp = data?.comparativo_semanal || {};
  const metricas = comp.metricas || {};
  const semanas = (comp.semanas || []).map(s => String(s));
  const yearLabel = comp.anio ? String(comp.anio) : 'Anio seleccionado';
  const prevLabel = comp.anio_anterior ? String(comp.anio_anterior) : 'Anio anterior';
  const metrics = [
    ['hectolitros', 'Hectolitros'],
    ['bultos', 'Bultos'],
    ['pallets', 'Pallets'],
  ];

  metrics.forEach(([metricKey, metricLabel]) => {
    const suffix = metricKey.charAt(0).toUpperCase() + metricKey.slice(1);
    const m = metricas[metricKey] || {};
    const actual = m.actual || [];
    const anterior = m.anterior || [];
    const evoCanvas = `ventaDiaEvo${suffix}`;
    const cmpCanvas = `ventaDiaCmp${suffix}`;

    ventaDiaCmpCharts[metricKey] = renderVentaDiaChart(cmpCanvas, ventaDiaCmpCharts[metricKey], {
      metric: metricKey,
      type: 'line',
      labels: semanas,
      usePointStyle: true,
      datasets: [
        {
          label: yearLabel,
          data: actual,
          borderColor: '#5b8dee',
          backgroundColor: 'rgba(91,141,238,.12)',
          pointBackgroundColor: '#5b8dee',
          pointBorderColor: '#5b8dee',
          pointRadius: 1.5,
          borderWidth: 2.5,
          tension: 0.25,
          fill: false,
          order: 1,
        },
        {
          label: prevLabel,
          data: anterior,
          borderColor: '#f2a93b',
          backgroundColor: 'rgba(242,169,59,.08)',
          pointBackgroundColor: '#f2a93b',
          pointBorderColor: '#f2a93b',
          pointRadius: 0,
          pointHoverRadius: 3,
          borderWidth: 2,
          borderDash: [6, 4],
          tension: 0.18,
          fill: false,
          order: 2,
        },
      ],
    });

    ventaDiaEvoCharts[metricKey] = renderVentaDiaChart(evoCanvas, ventaDiaEvoCharts[metricKey], {
      metric: metricKey,
      type: 'line',
      labels: semanas,
      datasets: [
        {
          label: yearLabel,
          data: actual,
          backgroundColor: 'rgba(76,190,138,.16)',
          borderColor: '#4cbe8a',
          borderWidth: 2.5,
          fill: true,
          pointRadius: 1.8,
          pointHoverRadius: 4,
          pointBorderWidth: 0,
          tension: 0.35,
          cubicInterpolationMode: 'monotone',
        },
      ],
    });
  });
}

function renderVentaDiaComparativoKpis(data) {
  const box = document.getElementById('ventaDiaComparativoKpis');
  if (!box) return;

  const comp = data?.comparativo_semanal || {};
  const metricas = comp.metricas || {};
  const yearLabel = comp.anio ? String(comp.anio) : 'Anio seleccionado';
  const prevLabel = comp.anio_anterior ? String(comp.anio_anterior) : 'Anio anterior';
  const metrics = [
    ['hectolitros', 'Hectolitros', 'pur'],
    ['bultos', 'Bultos', 'blu'],
    ['pallets', 'Pallets', 'grn'],
  ];

  if (!Object.keys(metricas).length) {
    box.innerHTML = '<div class="empty"><div class="icon">📊</div>Sin datos comparativos para mostrar</div>';
    return;
  }

  let html = '<div class="vd-kpi-grid">';
  metrics.forEach(([metricKey, metricLabel, colorClass]) => {
    const m = metricas[metricKey] || {};
    const actual = m.total_actual;
    const anterior = m.total_anterior;
    const varPct = m.variacion_pct;
    const trendColor = varPct == null ? 'var(--muted)' : (varPct >= 0 ? 'var(--grn)' : 'var(--red)');
    const trendText = varPct == null ? 'n/d' : fmtDelta(varPct);
    html += `
      <div class="kpi ${colorClass}" style="min-height:110px">
        <div class="kpi-lbl">${esc(metricLabel)}</div>
        <div class="kpi-val ${colorClass}" style="font-size:24px">${ventaDiaFormat(metricKey, actual)}</div>
        <div style="margin-top:6px;font-size:11px;color:var(--muted);line-height:1.35">
          ${esc(yearLabel)}: <span style="color:var(--txt);font-weight:600">${ventaDiaFormat(metricKey, actual)}</span><br>
          ${esc(prevLabel)}: <span style="color:var(--txt);font-weight:600">${ventaDiaFormat(metricKey, anterior)}</span><br>
          <span style="color:${trendColor};font-weight:700">Cambio: ${trendText}</span>
        </div>
      </div>
    `;
  });
  html += '</div>';
  box.innerHTML = html;
}

const VENTA_DIA_HEATMAP_STOPS = [
  [0.00, [15, 23, 42]],
  [0.16, [28, 42, 72]],
  [0.34, [37, 99, 235]],
  [0.54, [14, 165, 233]],
  [0.72, [34, 197, 94]],
  [0.86, [234, 179, 8]],
  [1.00, [249, 115, 22]],
];

function ventaDiaHeatmapLerp(a, b, t) {
  return a + ((b - a) * t);
}

function ventaDiaHeatmapRgbToCss(rgb, alpha = 1) {
  return `rgba(${Math.round(rgb[0])},${Math.round(rgb[1])},${Math.round(rgb[2])},${alpha})`;
}

function ventaDiaHeatmapLuma(rgb) {
  return (0.2126 * rgb[0]) + (0.7152 * rgb[1]) + (0.0722 * rgb[2]);
}

function ventaDiaHeatmapPalette(ratio) {
  const t = Math.max(0, Math.min(1, ratio));
  for (let i = 0; i < VENTA_DIA_HEATMAP_STOPS.length - 1; i++) {
    const [stopA, rgbA] = VENTA_DIA_HEATMAP_STOPS[i];
    const [stopB, rgbB] = VENTA_DIA_HEATMAP_STOPS[i + 1];
    if (t <= stopB || i === VENTA_DIA_HEATMAP_STOPS.length - 2) {
      const local = stopB === stopA ? 0 : (t - stopA) / (stopB - stopA);
      return [
        ventaDiaHeatmapLerp(rgbA[0], rgbB[0], local),
        ventaDiaHeatmapLerp(rgbA[1], rgbB[1], local),
        ventaDiaHeatmapLerp(rgbA[2], rgbB[2], local),
      ];
    }
  }
  return VENTA_DIA_HEATMAP_STOPS[VENTA_DIA_HEATMAP_STOPS.length - 1][1];
}

function ventaDiaHeatmapColor(value, min, max) {
  const num = Number(value || 0);
  if (!Number.isFinite(num) || num <= 0) {
    return {
      bg: 'rgba(15,23,42,.94)',
      fg: 'var(--muted)',
      border: 'rgba(255,255,255,.08)',
      zero: true,
    };
  }

  const range = max - min;
  const raw = range > 0 ? Math.max(0, Math.min(1, (num - min) / range)) : 0.72;
  const ratio = Math.pow(raw, 0.62);
  const rgb = ventaDiaHeatmapPalette(ratio);
  const fg = ventaDiaHeatmapLuma(rgb) > 145 ? '#0f172a' : '#f8fafc';
  return {
    bg: ventaDiaHeatmapRgbToCss(rgb),
    fg,
    border: 'rgba(255,255,255,.08)',
    zero: false,
  };
}

function renderVentaDiaHeatmapBox(boxId, heatmap) {
  const box = document.getElementById(boxId);
  if (!box) return;

  if (!heatmap || !Array.isArray(heatmap.data) || !heatmap.data.length) {
    box.innerHTML = '<div class="empty"><div class="icon">🗓️</div>Sin datos acumulados para el mapa de calor</div>';
    return;
  }

  const metric = heatmap.metrica || 'hectolitros';
  const metricLabel = heatmap.metrica_label || ventaDiaHeatmapMetricLabel(metric);
  const metricSuffix = ({
    salidas: 'acumuladas',
    personas: 'acumuladas',
  })[metric] || 'acumulados';
  const dias = heatmap.dias || [];
  const semanas = heatmap.semanas || heatmap.data.map((_, idx) => idx + 1);
  const minVal = Number(heatmap.min_val || 0);
  const maxVal = Number(heatmap.max_val || 0);

  let html = `
    <div class="vd-heatmap-meta">
      <div class="vd-heatmap-caption">${esc(metricLabel)} ${esc(heatmap.agregacion === 'acumulado' ? metricSuffix : (heatmap.agregacion || metricSuffix))} en ${esc(heatmap.periodo_label || 'el mes seleccionado')}</div>
      <div class="vd-heatmap-legend">
        <span class="vd-heatmap-scale-label">Bajo</span>
        <span class="vd-heatmap-scale-bar"></span>
        <span class="vd-heatmap-scale-label">Alto</span>
        <span class="vd-heatmap-scale-label">Escala: ${ventaDiaHeatmapIntFormat(minVal)} - ${ventaDiaHeatmapIntFormat(maxVal)}</span>
      </div>
    </div>
    <div class="vd-heatmap-shell">
      <table class="vd-heatmap-table">
        <thead>
          <tr>
            <th class="vd-heatmap-week-head"><span class="vd-heatmap-week-full">Semana</span><span class="vd-heatmap-week-short">S</span></th>
  `;

  dias.forEach(dia => {
    html += `<th>${esc(dia.label || dia)}</th>`;
  });

  html += '</tr></thead><tbody>';

  semanas.forEach((semana, idx) => {
    const fila = heatmap.data[idx] || [];
    html += `<tr><td class="vd-heatmap-rowlabel"><span class="vd-heatmap-week-full">Semana </span><span class="vd-heatmap-week-short">S</span><span class="vd-heatmap-week-num">${esc(semana)}</span></td>`;
    fila.forEach((value, diaIdx) => {
      const num = Number(value || 0);
      const paint = ventaDiaHeatmapColor(num, minVal, maxVal);
      const dia = dias[diaIdx] || {};
      const diaLabel = typeof dia === 'string' ? dia : (dia.label || dia.nombre || `Dia ${diaIdx + 1}`);
      const title = `Semana ${semana} - ${diaLabel}`;
      html += `
        <td class="vd-heatmap-cell ${paint.zero ? 'vd-heatmap-zero' : ''}">
          <div class="vd-heatmap-value" title="${esc(title)}" style="background:${paint.bg};color:${paint.fg};border-color:${paint.border}">
            ${ventaDiaHeatmapIntFormat(num)}
          </div>
        </td>`;
    });
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  box.innerHTML = html;
}

function renderVentaDiaHeatmaps(data) {
  const heatmaps = data?.heatmaps || {};
  renderVentaDiaHeatmapBox('ventaDiaHeatmapHectolitros', heatmaps.hectolitros || data?.heatmap || null);
  renderVentaDiaHeatmapBox('ventaDiaHeatmapSalidas', heatmaps.salidas || null);
  renderVentaDiaHeatmapBox('ventaDiaHeatmapPersonas', heatmaps.personas || null);
}

function renderVentaDiaHeatmap(data) {
  renderVentaDiaHeatmapBox('ventaDiaHeatmap', data?.heatmap || null);
}

function renderVentaDiaInsights(insights) {
  const box = document.getElementById('ventaDiaInsights');
  if (!box) return;

  if (!Array.isArray(insights) || !insights.length) {
    box.innerHTML = '<div class="empty"><div class="icon">ℹ️</div>Sin alertas relevantes para el período</div>';
    return;
  }

  const borderByType = {
    danger: '#d85a30',
    warning: '#ef9f27',
    info: '#378add',
    success: '#4cbe8a',
  };

  let html = '<div style="display:grid;gap:10px">';
  insights.forEach(item => {
    const tipo = item?.tipo || 'info';
    const border = borderByType[tipo] || borderByType.info;
    html += `
      <div style="border:1px solid rgba(255,255,255,.06);border-left:4px solid ${border};border-radius:12px;padding:12px 14px;background:rgba(12,18,32,.45)">
        <div style="display:flex;align-items:flex-start;gap:10px">
          <div style="font-size:18px;line-height:1">${esc(item.icono || 'ℹ️')}</div>
          <div style="min-width:0">
            <div style="font-weight:700;font-size:13px;color:var(--txt);margin-bottom:4px">${esc(item.titulo || 'Insight')}</div>
            <div style="font-size:12px;color:var(--muted);line-height:1.45">${esc(item.texto || '')}</div>
          </div>
        </div>
      </div>
    `;
  });
  html += '</div>';
  box.innerHTML = html;
}

function onPeriodoChange() {
  loadHistorico();
  if (document.getElementById('tab-analisis').style.display !== 'none') loadAnalisisHl();
  if (document.getElementById('tab-dropsize')?.style.display !== 'none') loadDropsize();
}

async function loadVentaDia() {
  const seq = ++_loadVentaDiaSeq;
  if (_ventaDiaAbort) _ventaDiaAbort.abort();
  _ventaDiaAbort = new AbortController();

  initVentaDiaFilters();
  destroyVentaDiaCharts();

  load('ventaDiaHectolitros');
  load('ventaDiaBultos');
  load('ventaDiaPallets');
  load('ventaDiaComparativoKpis');
  load('ventaDiaDistribucionHectolitros');
  load('ventaDiaDistribucionBultos');
  load('ventaDiaDistribucionPallets');
  load('ventaDiaHeatmapHectolitros');
  load('ventaDiaHeatmapSalidas');
  load('ventaDiaHeatmapPersonas');
  load('ventaDiaInsights');

  try {
    const params = ventaDiaQueryParams();
    const query = params.toString();
    const data = await api(`/api/picos/venta-dia?${query}`, { signal: _ventaDiaAbort.signal });
    if (seq !== _loadVentaDiaSeq || query !== ventaDiaQueryParams().toString()) return;

    ventaDiaData = data || {};
    const filtros = data.filtros || {};
    const comp = data.comparativo_semanal || {};
    const heatmaps = data.heatmaps || {};
    const heatmapHectolitros = heatmaps.hectolitros || data.heatmap || {};
    const heatmapSalidas = heatmaps.salidas || {};
    const heatmapPersonas = heatmaps.personas || {};
    const heatmapPeriod = heatmapHectolitros.periodo_label || heatmapSalidas.periodo_label || heatmapPersonas.periodo_label || 'sin mes';
    const meta = document.getElementById('ventaDiaMeta');
    if (meta) {
      meta.textContent = `Sucursal: ${filtros.sucursal_label || getSuc()} | Período: ${data.periodo || 'Todo el histórico'} | Comparativo ISO: ${comp.anio || filtros.anio || '?'} vs ${comp.anio_anterior || '?'} | Mapas de calor: ${heatmapPeriod} | Hectolitros, Salidas y Personas con el mismo filtro.`;
    }

    const metricas = data.metricas || {};
    document.getElementById('ventaDiaHectolitros').innerHTML = renderVentaDiaTable('hectolitros', 'Hectolitros', metricas.hectolitros);
    document.getElementById('ventaDiaBultos').innerHTML = renderVentaDiaTable('bultos', 'Bultos', metricas.bultos);
    document.getElementById('ventaDiaPallets').innerHTML = renderVentaDiaTable('pallets', 'Pallets', metricas.pallets);
    renderVentaDiaComparativoKpis(data);
    renderVentaDiaDistribucion(data);
    renderVentaDiaCharts(data);
    renderVentaDiaHeatmaps(data);
    renderVentaDiaInsights(data.insights || []);
  } catch (e) {
    if (e.name === 'AbortError') return;
    errBox('ventaDiaHectolitros', 'Error: ' + e.message);
    errBox('ventaDiaBultos', 'Error: ' + e.message);
    errBox('ventaDiaPallets', 'Error: ' + e.message);
    errBox('ventaDiaComparativoKpis', 'Error: ' + e.message);
    errBox('ventaDiaDistribucionHectolitros', 'Error: ' + e.message);
    errBox('ventaDiaDistribucionBultos', 'Error: ' + e.message);
    errBox('ventaDiaDistribucionPallets', 'Error: ' + e.message);
    errBox('ventaDiaHeatmapHectolitros', 'Error: ' + e.message);
    errBox('ventaDiaHeatmapSalidas', 'Error: ' + e.message);
    errBox('ventaDiaHeatmapPersonas', 'Error: ' + e.message);
    errBox('ventaDiaInsights', 'Error: ' + e.message);
    const meta = document.getElementById('ventaDiaMeta');
    if (meta) meta.textContent = `Error al cargar venta diaria: ${e.message}`;
  }
}

function experienciaStateLabel(state) {
  return ({
    bueno: 'Bueno',
    neutro: 'Neutro',
    malo: 'Malo',
    sin_dato: 'Sin dato',
  })[state] || 'Sin dato';
}

function experienciaStateColor(state) {
  return ({
    bueno: '#4cbe8a',
    neutro: '#f5a623',
    malo: '#e05c5c',
    sin_dato: '#7a8191',
  })[state] || '#7a8191';
}

function experienciaMetricLabel(metric) {
  return ({
    nps: 'NPS',
    rmd: 'RMD',
    combinado: 'NPS + RMD',
  })[metric] || 'NPS';
}

function experienciaMetricValue(row, metric) {
  if (metric === 'rmd') {
    const value = row?.rmd_promedio ?? row?.rmd_valor;
    return value == null ? null : Number(value);
  }
  if (metric === 'combinado') {
    const nps = row?.nps_indice_promedio ?? row?.nps_indice;
    const rmd = row?.rmd_promedio ?? row?.rmd_valor;
    const npsNorm = nps == null ? null : (Number(nps) + 100) / 2;
    const rmdNorm = rmd == null ? null : (Number(rmd) / 5) * 100;
    const vals = [npsNorm, rmdNorm].filter(v => v != null && !Number.isNaN(v));
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  }
  const value = row?.nps_indice_promedio ?? row?.nps_indice;
  return value == null ? null : Number(value);
}

function experienciaMetricFormat(metric, value) {
  if (metric === 'rmd') return experienciaScoreText(value, 2);
  if (metric === 'combinado') return `${experienciaScoreText(value, 0)}%`;
  return experienciaScoreText(value, 1);
}

function experienciaScoreText(value, decimals = 1) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  const num = Number(value);
  return num.toLocaleString('es-AR', {
    minimumFractionDigits: Math.abs(num % 1) > 0.0001 && decimals > 0 ? 1 : 0,
    maximumFractionDigits: decimals,
  });
}

function experienciaQtyText(value, decimals = 1) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  const num = Number(value);
  return num.toLocaleString('es-AR', {
    minimumFractionDigits: Math.abs(num % 1) > 0.0001 && decimals > 0 ? 1 : 0,
    maximumFractionDigits: decimals,
  });
}

function experienciaIntText(value) {
  return value == null || Number.isNaN(Number(value))
    ? '-'
    : Math.round(Number(value)).toLocaleString('es-AR', { maximumFractionDigits: 0 });
}

function experienciaPctText(value) {
  return value == null || Number.isNaN(Number(value))
    ? '-'
    : `${Number(value).toLocaleString('es-AR', { maximumFractionDigits: 0 })}%`;
}

function experienciaMetricAxis(metric, data) {
  if (metric === 'rmd') return { min: 0, max: 5 };
  if (metric === 'combinado') return { min: 0, max: 100 };
  return { min: -100, max: 100 };
}

function experienciaMetricRows(rows, metric) {
  return (rows || []).filter(row => experienciaMetricValue(row, metric) != null);
}

function experienciaMetricExplanation(metric) {
  if (metric === 'combinado') {
    return 'NPS + RMD: NPS se normaliza de -100..100 a 0..100; RMD se normaliza de 1..5 a 20..100; el valor final es el promedio de indicadores disponibles. Estado combinado: malo si NPS o RMD es malo; neutro si alguno es neutro; bueno si ambos son buenos.';
  }
  if (metric === 'nps') return 'NPS: % promotores - % detractores. Escala -100 a 100.';
  if (metric === 'rmd') return 'RMD: promedio de calificacion 1 a 5.';
  return '';
}

function selectedOptionText(id, fallback = '-') {
  const el = document.getElementById(id);
  const opt = el?.selectedOptions?.[0];
  return (opt?.textContent || fallback || '-').trim();
}

function fillSelectPreserving(id, items, allValue, allLabel) {
  const el = document.getElementById(id);
  if (!el) return;
  const current = el.value || allValue;
  el.innerHTML = '';
  el.add(new Option(allLabel, allValue));
  (items || []).forEach(item => {
    const value = item?.value ?? item;
    const label = item?.label ?? item?.value ?? item;
    if (value == null) return;
    if ([...el.options].some(opt => opt.value === String(value))) return;
    el.add(new Option(label, value));
  });
  el.value = [...el.options].some(opt => opt.value === current) ? current : allValue;
}

function experienciaFilterLabelText(filtros = {}, periodoLabel = null) {
  const metric = filtros.metrica || document.getElementById('expMetrica')?.value || 'nps';
  const estado = filtros.estado || document.getElementById('expEstado')?.value || 'TODOS';
  return [
    `Período: ${periodoLabel || document.getElementById('expPeriodo')?.value || '-'}`,
    `Sucursal: ${selectedOptionText('expSucursal', filtros.sucursal || 'TODAS')}`,
    `Métrica: ${experienciaMetricLabel(metric)}`,
    `Localidad: ${filtros.localidad && filtros.localidad !== 'TODAS' ? filtros.localidad : selectedOptionText('expLocalidad', 'Todas')}`,
    `Canal: ${filtros.tipo_negocio && filtros.tipo_negocio !== 'TODAS' ? filtros.tipo_negocio : selectedOptionText('expTipoNegocio', 'Todos')}`,
    `Estado: ${estado === 'TODOS' ? 'Todos' : experienciaStateLabel(estado)}`,
  ].join(' | ');
}

function experienciaQueryParams() {
  const params = new URLSearchParams();
  const suc = document.getElementById('expSucursal')?.value || getSuc();
  const periodo = document.getElementById('expPeriodo')?.value || '';
  const localidad = document.getElementById('expLocalidad')?.value || 'TODAS';
  const tipo = document.getElementById('expTipoNegocio')?.value || 'TODAS';
  const estado = document.getElementById('expEstado')?.value || 'TODOS';
  const metrica = document.getElementById('expMetrica')?.value || 'nps';
  params.set('sucursal', suc);
  params.set('metrica', metrica);
  if (periodo) params.set('periodo', periodo);
  if (localidad && localidad !== 'TODAS') params.set('localidad', localidad);
  if (tipo && tipo !== 'TODAS') params.set('tipo_negocio', tipo);
  if (estado && estado !== 'TODOS') params.set('estado', estado);
  return params;
}

function experienciaFillSelect(id, items, allValue, allLabel) {
  const el = document.getElementById(id);
  if (!el) return;
  const current = el.value || allValue;
  el.innerHTML = '';
  el.add(new Option(allLabel, allValue));
  (items || []).forEach(item => {
    const value = item.value ?? item;
    const label = item.label ?? item.value ?? item;
    if (value != null && ![...el.options].some(opt => opt.value === String(value))) {
      el.add(new Option(label, value));
    }
  });
  el.value = [...el.options].some(opt => opt.value === current) ? current : allValue;
}

function syncExperienciaFilters(data) {
  const periodo = document.getElementById('expPeriodo');
  if (periodo && !periodo.value && data?.periodo?.value) periodo.value = data.periodo.value;
  const disponibles = data?.filtros_disponibles || {};
  experienciaFillSelect('expLocalidad', disponibles.localidades || [], 'TODAS', 'Todas');
  experienciaFillSelect('expTipoNegocio', disponibles.tipos_negocio || [], 'TODAS', 'Todos');
}

function destroyExperienciaCharts() {
  Object.values(experienciaCharts).forEach(chart => { if (chart) chart.destroy(); });
  experienciaCharts = {};
}

function renderExperienciaKpis(data) {
  const el = document.getElementById('expKpis');
  if (!el) return;
  const r = data?.resumen || {};
  const evalTxt = `${fmtN(r.clientes_evaluados || 0)} / ${fmtN(r.clientes || 0)}`;
  const metric = r.metrica || data?.filtros?.metrica || 'nps';
  const metricLabel = r.metrica_label || experienciaMetricLabel(metric);
  const metricValue = experienciaMetricFormat(metric, experienciaMetricValue(r, metric));
  const gpsTxt = `${fmtN(r.con_gps || 0)} / ${fmtN(r.clientes || 0)}`;
  el.innerHTML = `
    <div class="kpi blu"><div class="kpi-lbl">Clientes evaluados</div><div class="kpi-val blu">${evalTxt}</div></div>
    <div class="kpi pur"><div class="kpi-lbl">${esc(metricLabel)}</div><div class="kpi-val pur">${metricValue}</div></div>
    <div class="kpi ora"><div class="kpi-lbl">HL del mes</div><div class="kpi-val ora">${experienciaQtyText(r.hl_mes || 0, 1)}</div></div>
    <div class="kpi blu"><div class="kpi-lbl">Pedidos del mes</div><div class="kpi-val blu">${experienciaIntText(r.pedidos_mes || 0)}</div></div>
    <div class="kpi grn"><div class="kpi-lbl">Cobertura NPS / RMD</div><div class="kpi-val grn">${fmtN(r.clientes_nps || 0)} / ${fmtN(r.clientes_rmd || 0)}</div></div>
    <div class="kpi ora"><div class="kpi-lbl">Localidades</div><div class="kpi-val ora">${fmtN(r.localidades || 0)}</div></div>
    <div class="kpi blu"><div class="kpi-lbl">GPS cubierto</div><div class="kpi-val blu">${gpsTxt}</div></div>
  `;
}

function renderExperienciaSemaforo(data) {
  const el = document.getElementById('expSemaforo');
  if (!el) return;
  const r = data?.resumen || {};
  const total = Math.max(1, Number(r.bueno || 0) + Number(r.neutro || 0) + Number(r.malo || 0) + Number(r.sin_dato || 0));
  const rows = [
    ['bueno', r.bueno || 0],
    ['neutro', r.neutro || 0],
    ['malo', r.malo || 0],
    ['sin_dato', r.sin_dato || 0],
  ];
  let html = '<div class="exp-score-list">';
  rows.forEach(([state, value]) => {
    const pct = Number(value || 0) / total * 100;
    html += `
      <div class="exp-score-row">
        <div class="exp-score-label">${experienciaStateLabel(state)}</div>
        <div class="exp-score-track"><div class="exp-score-fill ${state}" style="width:${Math.max(2, pct)}%"></div></div>
        <div class="exp-score-value">${experienciaPctText(pct)}</div>
      </div>
    `;
  });
  html += '</div>';
  html += `
    <div style="margin-top:14px;display:grid;gap:8px">
      <div class="mini"><span class="lbl">NPS con dato</span><span class="val">${fmtN(r.clientes_nps || 0)}</span></div>
      <div class="mini"><span class="lbl">Respuestas NPS</span><span class="val">${fmtN(r.nps_respuestas || 0)}</span></div>
      <div class="mini"><span class="lbl">RMD con dato</span><span class="val">${fmtN(r.clientes_rmd || 0)}</span></div>
      <div class="mini"><span class="lbl">Sin GPS</span><span class="val" style="color:${(r.sin_gps || 0) ? 'var(--acc)' : 'var(--grn)'}">${fmtN(r.sin_gps || 0)}</span></div>
    </div>
  `;
  el.innerHTML = html;
}

function resetExperienciaLeafletMap() {
  if (experienciaMap) {
    experienciaMap.remove();
    experienciaMap = null;
    experienciaMapLayer = null;
  }
}

function experienciaClientePopupRows(clientes) {
  const rows = clientes || [];
  if (!rows.length) return '<div style="color:#7f8aa3;font-size:11px;margin-top:6px">Sin clientes evaluados para esta métrica.</div>';
  return `
    <div style="margin-top:8px;max-height:240px;overflow:auto;border:1px solid rgba(91,141,238,.18);border-radius:10px">
      <table style="width:100%;border-collapse:collapse;font-size:10.5px">
        <thead>
          <tr style="background:rgba(91,141,238,.12);color:#8aa3d4">
            <th style="text-align:left;padding:5px 6px">Cliente</th>
            <th style="text-align:right;padding:5px 6px">NPS</th>
            <th style="text-align:right;padding:5px 6px">RMD</th>
            <th style="text-align:right;padding:5px 6px">Conjunto</th>
            <th style="text-align:right;padding:5px 6px">HL</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(row => `
            <tr>
              <td style="padding:5px 6px;border-top:1px solid rgba(255,255,255,.06)">
                <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${experienciaStateColor(row.estado)};margin-right:5px"></span>
                <strong>${esc(row.descripcion_cliente || row.cliente || '-')}</strong>
                <div style="color:#7f8aa3">${esc(row.cliente || '-')} | ${esc(row.tipo_negocio || '-')} | ${experienciaIntText(row.pedidos_mes ?? row.pedidos_ytd ?? 0)} pedidos mes | Venta ${fmtM(row.venta_mes ?? row.venta_ytd ?? 0)}</div>
              </td>
              <td style="padding:5px 6px;border-top:1px solid rgba(255,255,255,.06);text-align:right;font-family:var(--mono)">${experienciaMetricFormat('nps', experienciaMetricValue(row, 'nps'))}</td>
              <td style="padding:5px 6px;border-top:1px solid rgba(255,255,255,.06);text-align:right;font-family:var(--mono)">${experienciaScoreText(row.rmd_valor, 2)}</td>
              <td style="padding:5px 6px;border-top:1px solid rgba(255,255,255,.06);text-align:right;font-family:var(--mono)">${experienciaMetricFormat('combinado', experienciaMetricValue(row, 'combinado'))}</td>
              <td style="padding:5px 6px;border-top:1px solid rgba(255,255,255,.06);text-align:right;font-family:var(--mono)">${experienciaQtyText(row.hl_mes ?? row.hl_ytd ?? 0, 1)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function renderExperienciaLeafletMap(el, rows, data) {
  if (typeof L === 'undefined') return false;
  el.classList.add('leaflet-ready');
  if (!experienciaMap) {
    el.innerHTML = '';
    experienciaMap = L.map(el, { zoomControl: true, attributionControl: true, doubleClickZoom: false }).setView([-36.1, -57.8], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap',
    }).addTo(experienciaMap);
    experienciaMapLayer = L.layerGroup().addTo(experienciaMap);
  }
  experienciaMapLayer.clearLayers();

  const maxClientes = Math.max(...rows.map(row => Number(row.clientes || 0)), 1);
  const bounds = [];
  const metric = data?.resumen?.metrica || data?.filtros?.metrica || 'nps';
  const metricLabel = data?.resumen?.metrica_label || experienciaMetricLabel(metric);
  rows.forEach(row => {
    const lat = Number(row.latitud);
    const lng = Number(row.longitud);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    const state = row.estado || 'sin_dato';
    const radius = Math.max(8, Math.min(28, 8 + Math.sqrt(Number(row.clientes || 0) / maxClientes) * 24));
    const color = experienciaStateColor(state);
    const metricValue = experienciaMetricValue(row, metric);
    const npsValue = experienciaMetricValue(row, 'nps');
    const rmdValue = experienciaMetricValue(row, 'rmd');
    const comboValue = experienciaMetricValue(row, 'combinado');
    const peores = row.clientes_peores || [];
    const muestraTotal = Number(row.clientes_muestra_total || row.clientes || 0);
    const muestraLabel = muestraTotal > peores.length ? `Mostrando ${fmtN(peores.length)} peores de ${fmtN(muestraTotal)} clientes` : `Clientes de la localidad`;
    const popup = `
      <strong>${esc(row.localidad || '-')}</strong><br>
      ${esc(row.sucursal_nombre || row.sucursal_id || '-')}<br>
      Estado ${esc(metricLabel)}: <strong>${esc(experienciaStateLabel(state))}</strong><br>
      ${esc(metricLabel)}: ${esc(experienciaMetricFormat(metric, metricValue))}<br>
      Clientes evaluados: ${fmtN(row.clientes_evaluados || 0)} / ${fmtN(row.clientes || 0)}<br>
      Mes: ${experienciaQtyText(row.hl_mes || 0, 1)} HL | ${experienciaIntText(row.pedidos_mes || 0)} pedidos | Venta ${fmtM(row.venta_mes || 0)}<br>
      Ubicacion: ${row.geo_fuente === 'localidad' ? 'centro de localidad' : 'GPS clientes'}<br>
      NPS: ${experienciaMetricFormat('nps', npsValue)} | RMD: ${experienciaMetricFormat('rmd', rmdValue)} | Conjunto: ${experienciaMetricFormat('combinado', comboValue)}
      <div style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,.1)">
        <strong>${esc(muestraLabel)}</strong>
        ${experienciaClientePopupRows(peores)}
      </div>
    `;
    const marker = L.circleMarker([lat, lng], {
      radius,
      color: 'rgba(255,255,255,.82)',
      weight: 2,
      fillColor: color,
      fillOpacity: .82,
    });
    marker.bindTooltip('Doble click para ver clientes', { direction: 'top', opacity: .92, sticky: true });
    marker.on('dblclick', function (evt) {
      if (evt?.originalEvent) L.DomEvent.stop(evt.originalEvent);
      L.popup({ maxWidth: 720, minWidth: 520 })
        .setLatLng([lat, lng])
        .setContent(popup)
        .openOn(experienciaMap);
    });
    marker.addTo(experienciaMapLayer);
    bounds.push([lat, lng]);
  });

  if (bounds.length) experienciaMap.fitBounds(bounds, { padding: [24, 24], maxZoom: 10 });
  setTimeout(() => experienciaMap && experienciaMap.invalidateSize(), 60);
  return true;
}

function renderExperienciaMapFallback(el, rows, data) {
  resetExperienciaLeafletMap();
  el.classList.remove('leaflet-ready');
  const lats = rows.map(row => Number(row.latitud));
  const lngs = rows.map(row => Number(row.longitud));
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs), maxLng = Math.max(...lngs);
  const latSpan = Math.max(maxLat - minLat, 0.000001);
  const lngSpan = Math.max(maxLng - minLng, 0.000001);
  const maxClientes = Math.max(...rows.map(row => Number(row.clientes || 0)), 1);
  const metric = data?.resumen?.metrica || data?.filtros?.metrica || 'nps';
  const metricLabel = data?.resumen?.metrica_label || experienciaMetricLabel(metric);
  const topLabels = new Set(
    [...rows].sort((a, b) => Number(b.clientes || 0) - Number(a.clientes || 0)).slice(0, 10)
      .map(row => `${row.sucursal_id}|${row.localidad}`)
  );

  let html = '';
  rows.forEach(row => {
    const x = 6 + ((Number(row.longitud) - minLng) / lngSpan) * 88;
    const y = 94 - ((Number(row.latitud) - minLat) / latSpan) * 88;
    const size = Math.round(14 + Math.sqrt(Number(row.clientes || 0) / maxClientes) * 30);
    const state = row.estado || 'sin_dato';
    const peor = (row.clientes_peores || [])[0];
    const peorTxt = peor ? ` | peor: ${peor.descripcion_cliente || peor.cliente} (${metricLabel} ${experienciaMetricFormat(metric, peor.metrica_valor)})` : '';
    const title = `${row.localidad} | ${row.sucursal_nombre || row.sucursal_id} | ${fmtN(row.clientes_evaluados || 0)} evaluados | ${metricLabel} ${experienciaMetricFormat(metric, experienciaMetricValue(row, metric))}${peorTxt}`;
    html += `
      <div class="exp-map-point ${state}" title="${esc(title)}" style="left:${x}%;top:${y}%;width:${size}px;height:${size}px">
        ${fmtN(row.clientes || 0)}
      </div>
    `;
    if (topLabels.has(`${row.sucursal_id}|${row.localidad}`)) {
      html += `<div class="exp-map-label" style="left:${x}%;top:calc(${y}% + ${Math.round(size / 2) + 5}px)">${esc(row.localidad || '-')}</div>`;
    }
  });
  el.innerHTML = html;
}

function renderExperienciaMap(data) {
  const el = document.getElementById('expMap');
  if (!el) return;
  const rows = (data?.mapa_localidades || [])
    .filter(row => row.latitud != null && row.longitud != null);

  if (!rows.length) {
    resetExperienciaLeafletMap();
    el.classList.remove('leaflet-ready');
    el.innerHTML = '<div class="exp-map-empty">Sin coordenadas GPS para los filtros seleccionados.</div>';
    return;
  }

  if (!renderExperienciaLeafletMap(el, rows, data)) {
    renderExperienciaMapFallback(el, rows, data);
  }
}

function renderExperienciaCharts(data) {
  destroyExperienciaCharts();
  if (typeof Chart === 'undefined') return;

  const resumen = data?.resumen || {};
  const metric = resumen.metrica || data?.filtros?.metrica || 'nps';
  const metricLabel = resumen.metrica_label || experienciaMetricLabel(metric);
  const axis = experienciaMetricAxis(metric, data);
  const locTitle = document.getElementById('expLocalidadChartTitle');
  const tipoTitle = document.getElementById('expTipoChartTitle');
  if (locTitle) locTitle.textContent = `${metricLabel} por localidad`;
  if (tipoTitle) tipoTitle.textContent = `${metricLabel} por canal`;

  const stateLabels = ['Bueno', 'Neutro', 'Malo', 'Sin dato'];
  const stateKeys = ['bueno', 'neutro', 'malo', 'sin_dato'];
  const stateValues = stateKeys.map(key => Number(resumen[key] || 0));
  const stateTotal = stateValues.reduce((acc, value) => acc + Number(value || 0), 0);
  const stateCanvas = document.getElementById('expEstadoChart');
  if (stateCanvas) {
    experienciaCharts.estado = new Chart(stateCanvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: stateLabels,
        datasets: [{
          data: stateValues,
          backgroundColor: stateKeys.map(experienciaStateColor),
          borderColor: 'rgba(15,23,42,.95)',
          borderWidth: 2,
          spacing: 2,
          labelColor: '#f8fafc',
          valueFormatter: raw => Number(raw || 0) ? experienciaIntText(raw) : '',
        }],
      },
      plugins: [chartValueLabels],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '60%',
        layout: { padding: 10 },
        plugins: {
          legend: { position: 'bottom', labels: { color: '#e8eaf0', boxWidth: 10 } },
          chartValueLabels: { hideZero: true, font: '800 11px sans-serif' },
          tooltip: {
            callbacks: {
              label: ctx => {
                const value = Number(ctx.raw || 0);
                const pct = stateTotal ? value / stateTotal * 100 : 0;
                return `${ctx.label}: ${experienciaIntText(value)} (${experienciaPctText(pct)})`;
              },
            },
          },
        },
      },
    });
  }

  const localidades = experienciaMetricRows(data?.por_localidad || [], metric)
    .sort((a, b) => Number(b.clientes_evaluados || 0) - Number(a.clientes_evaluados || 0))
    .slice(0, 12);
  const locCanvas = document.getElementById('expLocalidadChart');
  if (locCanvas) {
    experienciaCharts.localidad = new Chart(locCanvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: localidades.map(row => row.localidad || '-'),
        datasets: [{
          label: metricLabel,
          data: localidades.map(row => experienciaMetricValue(row, metric)),
          backgroundColor: localidades.map(row => experienciaStateColor(row.estado)),
          borderWidth: 0,
          borderRadius: 8,
          borderSkipped: false,
          maxBarThickness: 18,
          labelColor: '#f8fafc',
          valueFormatter: raw => experienciaMetricFormat(metric, raw),
        }],
      },
      plugins: [chartValueLabels],
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { right: 48 } },
        plugins: {
          legend: { display: false },
          chartValueLabels: { hideZero: false, font: '800 10px sans-serif', maxLabelsPerDataset: 12 },
          tooltip: { callbacks: { label: ctx => `${metricLabel}: ${experienciaMetricFormat(metric, ctx.raw)}` } },
        },
        scales: {
          x: {
            min: axis.min,
            max: axis.max,
            ticks: { color: '#6b7080', callback: value => experienciaMetricFormat(metric, value) },
            grid: { color: 'rgba(42,46,58,.25)' },
          },
          y: {
            ticks: { color: '#6b7080' },
            grid: { display: false },
          },
        },
      },
    });
  }

  const tipos = experienciaMetricRows(data?.por_tipo_negocio || [], metric)
    .sort((a, b) => Number(b.clientes_evaluados || 0) - Number(a.clientes_evaluados || 0))
    .slice(0, 10);
  const tipoCanvas = document.getElementById('expTipoChart');
  if (tipoCanvas) {
    experienciaCharts.tipo = new Chart(tipoCanvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: tipos.map(row => row.tipo_negocio || '-'),
        datasets: [{
          label: metricLabel,
          data: tipos.map(row => experienciaMetricValue(row, metric)),
          backgroundColor: tipos.map(row => experienciaStateColor(row.estado)),
          borderWidth: 0,
          borderRadius: 8,
          borderSkipped: false,
          maxBarThickness: 18,
          labelColor: '#f8fafc',
          valueFormatter: raw => experienciaMetricFormat(metric, raw),
        }],
      },
      plugins: [chartValueLabels],
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { right: 48 } },
        plugins: {
          legend: { display: false },
          chartValueLabels: { hideZero: false, font: '800 10px sans-serif', maxLabelsPerDataset: 10 },
          tooltip: { callbacks: { label: ctx => `${metricLabel}: ${experienciaMetricFormat(metric, ctx.raw)}` } },
        },
        scales: {
          x: {
            min: axis.min,
            max: axis.max,
            ticks: { color: '#6b7080', callback: value => experienciaMetricFormat(metric, value) },
            grid: { color: 'rgba(42,46,58,.25)' },
          },
          y: {
            ticks: { color: '#6b7080' },
            grid: { display: false },
          },
        },
      },
    });
  }
}

function renderExperienciaTable(data) {
  const el = document.getElementById('expLocalidadTable');
  if (!el) return;
  const rows = data?.por_localidad || [];
  const metric = data?.resumen?.metrica || data?.filtros?.metrica || 'nps';
  const metricLabel = data?.resumen?.metrica_label || experienciaMetricLabel(metric);
  if (!rows.length) {
    el.innerHTML = '<div class="empty"><div class="icon">i</div>Sin localidades para los filtros seleccionados.</div>';
    return;
  }
  let html = `<table class="rtbl"><thead><tr>
    <th>Sucursal</th><th>Localidad</th><th>Estado</th><th>Clientes</th><th>${esc(metricLabel)}</th><th>NPS indice</th><th>RMD</th><th>Buenos</th><th>Neutros</th><th>Malos</th>
  </tr></thead><tbody>`;
  rows.slice(0, 120).forEach(row => {
    html += `<tr>
      <td>${esc(row.sucursal_nombre || row.sucursal_id || '-')}</td>
      <td>${esc(row.localidad || '-')}<div class="exp-table-sub">${fmtN(row.clientes_nps || 0)} NPS | ${fmtN(row.clientes_rmd || 0)} RMD</div></td>
      <td><span class="exp-state-pill ${row.estado || 'sin_dato'}">${experienciaStateLabel(row.estado)}</span></td>
      <td style="font-family:var(--mono);text-align:right">${fmtN(row.clientes_evaluados || 0)} / ${fmtN(row.clientes || 0)}</td>
      <td style="font-family:var(--mono);text-align:right;font-weight:800">${experienciaMetricFormat(metric, experienciaMetricValue(row, metric))}</td>
      <td style="font-family:var(--mono);text-align:right">${experienciaScoreText(row.nps_indice_promedio, 1)}</td>
      <td style="font-family:var(--mono);text-align:right">${experienciaScoreText(row.rmd_promedio, 2)}</td>
      <td style="font-family:var(--mono);text-align:right;color:var(--grn)">${fmtN(row.bueno || 0)}</td>
      <td style="font-family:var(--mono);text-align:right;color:var(--acc)">${fmtN(row.neutro || 0)}</td>
      <td style="font-family:var(--mono);text-align:right;color:var(--red)">${fmtN(row.malo || 0)}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  if (rows.length > 120) {
    html += `<div style="font-size:11px;color:var(--muted);margin-top:8px">Mostrando 120 de ${fmtN(rows.length)} localidades.</div>`;
  }
  el.innerHTML = html;
}

async function loadExperienciaClientes() {
  const seq = ++_loadExpSeq;
  if (_expAbort) _expAbort.abort();
  _expAbort = new AbortController();

  const ids = ['expKpis', 'expSemaforo', 'expLocalidadTable'];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando......</div>';
  });
  const map = document.getElementById('expMap');
  resetExperienciaLeafletMap();
  if (map) {
    map.classList.remove('leaflet-ready');
    map.innerHTML = '<div class="exp-map-empty">Cargando... mapa...</div>';
  }
  destroyExperienciaCharts();
  const meta = document.getElementById('expMeta');
  if (meta) meta.textContent = `${experienciaFilterLabelText()} | Actualizando datos...`;

  try {
    const query = experienciaQueryParams().toString();
    const data = await api(`/api/picos/experiencia-clientes?${query}`, { signal: _expAbort.signal, timeout: 60000 });
    if (seq !== _loadExpSeq || query !== experienciaQueryParams().toString()) return;
    experienciaData = data || {};
    syncExperienciaFilters(experienciaData);
    if (meta) {
      const r = experienciaData.resumen || {};
      const filtros = experienciaData.filtros || {};
      const metric = filtros.metrica || 'nps';
      const npsFuente = r.nps_fuente === 'conteo_respuestas'
        ? `NPS por formula promotores-detractores (${fmtN(r.nps_respuestas || 0)} respuestas)`
        : r.nps_fuente === 'conteo_respuestas_mixto'
          ? `NPS por formula con respuestas detalladas (${fmtN(r.nps_respuestas || 0)} respuestas); ${fmtN(r.nps_clientes_legacy || 0)} clientes solo legacy`
          : `NPS valor cliente legacy (${fmtN(r.clientes_nps || 0)} clientes)`;
      const sourceText = ['nps', 'combinado'].includes(metric) ? ` | ${npsFuente}.` : '.';
      const explanation = experienciaMetricExplanation(metric);
      meta.textContent = `${experienciaFilterLabelText({ ...filtros, metrica: metric }, experienciaData.periodo?.label || '-')} | ${fmtN(r.clientes_evaluados || 0)} clientes evaluados | ${fmtN(r.localidades || 0)} localidades${sourceText}${explanation ? ` ${explanation}` : ''}`;
    }
    renderExperienciaKpis(experienciaData);
    renderExperienciaSemaforo(experienciaData);
    renderExperienciaMap(experienciaData);
    renderExperienciaCharts(experienciaData);
    renderExperienciaTable(experienciaData);
  } catch (e) {
    if (e.name === 'AbortError') return;
    ids.forEach(id => errBox(id, 'Error: ' + e.message));
    if (map) map.innerHTML = `<div class="exp-map-empty" style="color:var(--red)">Error: ${esc(e.message)}</div>`;
    const meta = document.getElementById('expMeta');
    if (meta) meta.textContent = `Error al cargar experiencia clientes: ${e.message}`;
  }
}

async function onExperienciaSucursalChange() {
  const loc = document.getElementById('expLocalidad');
  const tipo = document.getElementById('expTipoNegocio');
  if (loc) loc.value = 'TODAS';
  if (tipo) tipo.value = 'TODAS';
  await loadExperienciaClientes();
}

async function onExperienciaPeriodoChange() {
  const loc = document.getElementById('expLocalidad');
  const tipo = document.getElementById('expTipoNegocio');
  if (loc) loc.value = 'TODAS';
  if (tipo) tipo.value = 'TODAS';
  await loadExperienciaClientes();
}

async function limpiarExperienciaFiltros() {
  const suc = document.getElementById('expSucursal');
  if (suc) suc.value = getSuc();
  ['expLocalidad', 'expTipoNegocio'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = 'TODAS';
  });
  const estado = document.getElementById('expEstado');
  if (estado) estado.value = 'TODOS';
  const metrica = document.getElementById('expMetrica');
  if (metrica) metrica.value = 'nps';
  await loadExperienciaClientes();
}

async function loadAnalisisHl() {
  const seq = ++_loadHlSeq;
  if (_hlAbort) _hlAbort.abort();
  _hlAbort = new AbortController();

  load('analisisHlKpis');
  load('analisisHlChart');
  load('analisisHlTabla');
  load('analisisHlMotivos');

  const n = document.getElementById('selPeriodoHist').value;
  const suc = getSuc();
  try {
    const data = await api(`/api/picos/analisis-rechazos?sucursal=${suc}&meses=${n}`, { signal: _hlAbort.signal });
    if (seq !== _loadHlSeq || suc !== getSuc() || n !== document.getElementById('selPeriodoHist').value) return;

    const meses = data.meses || [];
    const tot = data.totales || {};
    if (!meses.length) {
      document.getElementById('analisisHlKpis').innerHTML = '<div class="empty"><div class="icon">📊</div>Sin datos de rechazos</div>';
      document.getElementById('analisisHlChart').innerHTML = '';
      document.getElementById('analisisHlTabla').innerHTML = '';
      document.getElementById('analisisHlMotivos').innerHTML = '';
      return;
    }

    document.getElementById('analisisHlKpis').innerHTML = `
      <div class="kpi pur"><div class="kpi-lbl">HL despachados</div><div class="kpi-val pur">${fmtN(Math.round(tot.hl_total || 0))}</div></div>
      <div class="kpi red"><div class="kpi-lbl">Total HL rechazados</div><div class="kpi-val red">${fmt1(tot.hl_rechazo || 0)}</div></div>
      <div class="kpi red"><div class="kpi-lbl">% rechazo HL</div><div class="kpi-val red">${fmtPct1(tot.pct_rechazo_hl || 0)}</div></div>
      <div class="kpi pur"><div class="kpi-lbl">HL rechazo parcial</div><div class="kpi-val pur">${fmt1(tot.hl_rechazo_parcial || 0)}</div></div>
      <div class="kpi pur"><div class="kpi-lbl">HL rechazo completo</div><div class="kpi-val pur">${fmt1(tot.hl_rechazo_total || 0)}</div></div>
      <div class="kpi blu"><div class="kpi-lbl">Bultos despachados</div><div class="kpi-val blu">${fmtN(Math.round(tot.bultos_total || 0))}</div></div>
      <div class="kpi ora"><div class="kpi-lbl">Total bultos rechazados</div><div class="kpi-val ora">${fmt1(tot.bultos_rechazo || 0)}</div></div>
      <div class="kpi ora"><div class="kpi-lbl">% rechazo bultos</div><div class="kpi-val ora">${fmtPct1(tot.pct_rechazo_bultos || 0)}</div></div>
      <div class="kpi ora"><div class="kpi-lbl">Bultos rechazo parcial</div><div class="kpi-val ora">${fmt1(tot.bultos_rechazo_parcial || 0)}</div></div>
      <div class="kpi ora"><div class="kpi-lbl">Bultos rechazo completo</div><div class="kpi-val ora">${fmt1(tot.bultos_rechazo_total || 0)}</div></div>
      <div class="kpi blu"><div class="kpi-lbl">PDV rechazados</div><div class="kpi-val blu">${fmtN(tot.pedidos_rechazo || 0)}</div></div>
      <div class="kpi pur"><div class="kpi-lbl">RMCYO HL</div><div class="kpi-val pur">${fmtN(Math.round(tot.rmcyo_hl || 0))}</div></div>
      <div class="kpi red"><div class="kpi-lbl">RMCYO HL rechazados</div><div class="kpi-val red">${fmt1(tot.rmcyo_rechazo_hl || 0)}</div></div>
      <div class="kpi red"><div class="kpi-lbl">% RMCYO rechazo HL</div><div class="kpi-val red">${fmtPct1(tot.rmcyo_pct_rechazo_hl || 0)}</div></div>
      <div class="kpi ora"><div class="kpi-lbl">Peor mes</div><div class="kpi-val ora" style="font-size:18px">${tot.peor_mes || '?'} ${fmtPct(tot.peor_pct_rechazo_hl || 0)}</div></div>
      <div class="kpi blu"><div class="kpi-lbl">Mejor mes</div><div class="kpi-val blu" style="font-size:18px">${tot.mejor_mes || '?'} ${fmtPct(tot.mejor_pct_rechazo_hl || 0)}</div></div>
    `;

    const maxHl = Math.max(...meses.map(x => x.hl_total || 0), 1);
    const maxBultos = Math.max(...meses.map(x => x.bultos_total || 0), 1);
    let chart = '<div style="display:flex;flex-direction:column;gap:7px">';
    meses.forEach(x => {
      const okPct = Math.max(0, ((x.hl_total || 0) - (x.hl_rechazo || 0)) / maxHl * 100);
      const recPct = Math.max(0, (x.hl_rechazo || 0) / maxHl * 100);
      const okBltPct = Math.max(0, ((x.bultos_total || 0) - (x.bultos_rechazo || 0)) / maxBultos * 100);
      const recBltPct = Math.max(0, (x.bultos_rechazo || 0) / maxBultos * 100);
      chart += `<div class="hl-row">
        <span class="bar-lbl">${x.mes.slice(2)} HL</span>
        <div class="hl-stack" title="${fmtN(Math.round(x.hl_total || 0))} HL despachados">
          <div class="hl-ok" style="width:${okPct}%"></div>
          <div class="hl-rec" style="width:${recPct}%"></div>
        </div>
        <span class="bar-end">${fmtN(Math.round(x.hl_rechazo || 0))} HL rechazados</span>
        <span class="bar-end" style="color:${(x.pct_rechazo_hl || 0) > 5 ? 'var(--red)' : 'var(--grn)'}">${fmtPct(x.pct_rechazo_hl || 0)}</span>
      </div>
      <div class="hl-row">
        <span class="bar-lbl">Bultos</span>
        <div class="hl-stack" title="${fmtN(Math.round(x.bultos_total || 0))} bultos despachados">
          <div class="blt-ok" style="width:${okBltPct}%"></div>
          <div class="blt-rec" style="width:${recBltPct}%"></div>
        </div>
        <span class="bar-end">${fmtN(Math.round(x.bultos_rechazo || 0))} rechazados</span>
        <span class="bar-end" style="color:${(x.pct_rechazo_bultos || 0) > 5 ? 'var(--red)' : 'var(--grn)'}">${fmtPct(x.pct_rechazo_bultos || 0)}</span>
      </div>`;
    });
    chart += '</div>';
    document.getElementById('analisisHlChart').innerHTML = chart;

    let table = `<table class="rtbl"><thead><tr>
      <th>Mes</th><th>HL desp.</th><th>Total HL rechazados</th><th>HL rechazo parcial</th><th>HL rechazo completo</th><th>% rechazo HL</th>
      <th>Bultos desp.</th><th>Total bultos rechazados</th><th>Bultos rechazo parcial</th><th>Bultos rechazo completo</th><th>% rechazo bultos</th>
      <th>RMCYO HL</th><th>RMCYO HL rechazados</th><th>PDV rechazados</th><th>Salidas</th><th>Días</th>
    </tr></thead><tbody>`;
    meses.forEach(x => {
      table += `<tr>
        <td style="font-family:var(--mono)">${x.mes}</td>
        <td style="font-family:var(--mono)">${fmtN(Math.round(x.hl_total || 0))}</td>
        <td style="font-family:var(--mono);color:var(--red)">${fmtN(Math.round(x.hl_rechazo || 0))}</td>
        <td style="font-family:var(--mono);color:var(--acc)">${fmtN(Math.round(x.hl_rechazo_parcial || 0))}</td>
        <td style="font-family:var(--mono);color:var(--red)">${fmtN(Math.round(x.hl_rechazo_total || 0))}</td>
        <td style="font-family:var(--mono);color:${(x.pct_rechazo_hl || 0) > 5 ? 'var(--red)' : 'var(--grn)'}">${fmtPct(x.pct_rechazo_hl || 0)}</td>
        <td style="font-family:var(--mono)">${fmtN(Math.round(x.bultos_total || 0))}</td>
        <td style="font-family:var(--mono);color:var(--red)">${fmtN(Math.round(x.bultos_rechazo || 0))}</td>
        <td style="font-family:var(--mono);color:var(--acc)">${fmtN(Math.round(x.bultos_rechazo_parcial || 0))}</td>
        <td style="font-family:var(--mono);color:var(--red)">${fmtN(Math.round(x.bultos_rechazo_total || 0))}</td>
        <td style="font-family:var(--mono);color:${(x.pct_rechazo_bultos || 0) > 5 ? 'var(--red)' : 'var(--grn)'}">${fmtPct(x.pct_rechazo_bultos || 0)}</td>
        <td style="font-family:var(--mono)">${fmtN(Math.round(x.rmcyo_hl || 0))}</td>
        <td style="font-family:var(--mono);color:var(--red)">${fmtN(Math.round(x.rmcyo_rechazo_hl || 0))}</td>
        <td style="font-family:var(--mono)">${fmtN(x.pedidos_rechazo || 0)}</td>
        <td style="font-family:var(--mono)">${fmtN(x.salidas || 0)}</td>
        <td style="font-family:var(--mono)">${fmtN(x.dias || 0)}</td>
      </tr>`;
    });
    table += '</tbody></table>';
    document.getElementById('analisisHlTabla').innerHTML = table;

    const motivos = data.motivos || [];
    if (!motivos.length) {
      document.getElementById('analisisHlMotivos').innerHTML = '<div class="empty"><div class="icon">📋</div>Sin rechazos tomados para el período</div>';
      return;
    }
    let mot = `<table class="rtbl"><thead><tr>
      <th>Sector</th><th>Motivo</th><th>Total bultos rechazados</th><th>Bultos rechazo parcial</th><th>Bultos rechazo completo</th><th>Total HL rechazados</th><th>HL rechazo parcial</th><th>HL rechazo completo</th>
      <th>PDV rechazados</th><th>Ocurrencias</th><th>% rechazo bultos</th><th>% rechazo HL</th><th>Meses</th>
    </tr></thead><tbody>`;
    motivos.forEach(x => {
      mot += `<tr>
        <td>${esc(x.sector)}</td>
        <td>${esc(x.motivo)}</td>
        <td style="font-family:var(--mono);color:var(--red)">${fmtN(Math.round(x.bultos_rechazo || 0))}</td>
        <td style="font-family:var(--mono);color:var(--acc)">${fmtN(Math.round(x.bultos_rechazo_parcial || 0))}</td>
        <td style="font-family:var(--mono);color:var(--red)">${fmtN(Math.round(x.bultos_rechazo_total || 0))}</td>
        <td style="font-family:var(--mono);color:var(--red)">${fmtN(Math.round(x.hl_rechazo || 0))}</td>
        <td style="font-family:var(--mono);color:var(--acc)">${fmtN(Math.round(x.hl_rechazo_parcial || 0))}</td>
        <td style="font-family:var(--mono);color:var(--red)">${fmtN(Math.round(x.hl_rechazo_total || 0))}</td>
        <td style="font-family:var(--mono)">${fmtN(x.pedidos_rechazo || 0)}</td>
        <td style="font-family:var(--mono)">${fmtN(x.ocurrencias || 0)}</td>
        <td style="font-family:var(--mono)">${fmtPct(x.pct_del_rechazo_bultos || 0)}</td>
        <td style="font-family:var(--mono)">${fmtPct(x.pct_del_rechazo_hl || 0)}</td>
        <td style="font-family:var(--mono)">${fmtN(x.meses_con_rechazo || 0)}</td>
      </tr>`;
    });
    mot += '</tbody></table>';
    document.getElementById('analisisHlMotivos').innerHTML = mot;
  } catch (e) {
    if (e.name === 'AbortError') return;
    errBox('analisisHlKpis', 'Error: ' + e.message);
    errBox('analisisHlChart', 'Error: ' + e.message);
  }
}

// ─── DRAWER ──────────────────────────────────────────────────
// ─── DROPSIZE ────────────────────────────────────────────────────────────────
function initRechazosRankingFilters() {
  const suc = document.getElementById('rechazoRankingSucursal');
  const desde = document.getElementById('rechazoRankingDesde');
  const hasta = document.getElementById('rechazoRankingHasta');
  if (suc && !suc.dataset.ready) {
    suc.value = getSuc();
    suc.dataset.ready = '1';
  }
  if (desde && !desde.value) {
    const [y, m] = mesPad().split('-').map(Number);
    desde.value = `${y}-${String(m).padStart(2, '0')}-01`;
  }
  if (hasta && !hasta.value) {
    const [y, m] = mesPad().split('-').map(Number);
    hasta.value = `${y}-${String(m).padStart(2, '0')}-${String(new Date(y, m, 0).getDate()).padStart(2, '0')}`;
  }
}

function renderRechazosPorCliente(rows) {
  if (!rows.length) return '<div class="empty"><div class="icon">📋</div>Sin rechazos por cliente para el periodo</div>';
  let html = '<div style="overflow-x:auto"><table class="rtbl"><thead><tr><th>Cliente</th><th>Descripcion</th><th>Suc.</th><th>PDV</th><th>Bultos</th><th>HL</th><th>Pallets</th><th>Motivos</th></tr></thead><tbody>';
  rows.forEach(r => {
    html += `<tr>
      <td style="font-family:var(--mono);font-weight:700">${escHtml(r.cliente || '')}</td>
      <td>${escHtml(r.descripcion_cliente || '')}</td>
      <td>${escHtml(r.sucursal || '')}</td>
      <td style="font-family:var(--mono);text-align:right">${fmtN(r.pedidos_rechazo || 0)}</td>
      <td style="font-family:var(--mono);text-align:right;color:var(--red)">${fmt1(r.bultos_rechazo || 0)}</td>
      <td style="font-family:var(--mono);text-align:right;color:var(--red)">${fmt1(r.hl_rechazo || 0)}</td>
      <td style="font-family:var(--mono);text-align:right">${fmt1(r.pallets_rechazo || 0)}</td>
      <td style="max-width:280px;white-space:normal">${escHtml(r.motivos || '')}</td>
    </tr>`;
  });
  return html + '</tbody></table></div>';
}

function renderRechazosPorMotivo(rows) {
  if (!rows.length) return '<div class="empty"><div class="icon">📋</div>Sin rechazos por motivo para el periodo</div>';
  let html = '<div style="overflow-x:auto"><table class="rtbl"><thead><tr><th>Sector</th><th>Motivo</th><th>Clientes</th><th>PDV</th><th>Ocurr.</th><th>Bultos</th><th>HL</th><th>Pallets</th></tr></thead><tbody>';
  rows.forEach(r => {
    html += `<tr>
      <td>${escHtml(r.sector || 'Sin sector')}</td>
      <td style="max-width:260px;white-space:normal">${escHtml(r.motivo || 'Sin motivo')}</td>
      <td style="font-family:var(--mono);text-align:right">${fmtN(r.clientes_rechazo || 0)}</td>
      <td style="font-family:var(--mono);text-align:right">${fmtN(r.pedidos_rechazo || 0)}</td>
      <td style="font-family:var(--mono);text-align:right">${fmtN(r.ocurrencias || 0)}</td>
      <td style="font-family:var(--mono);text-align:right;color:var(--red)">${fmt1(r.bultos_rechazo || 0)}</td>
      <td style="font-family:var(--mono);text-align:right;color:var(--red)">${fmt1(r.hl_rechazo || 0)}</td>
      <td style="font-family:var(--mono);text-align:right">${fmt1(r.pallets_rechazo || 0)}</td>
    </tr>`;
  });
  return html + '</tbody></table></div>';
}

async function loadRechazosRankings() {
  initRechazosRankingFilters();
  load('rechazosPorCliente');
  load('rechazosPorMotivo');
  const desde = document.getElementById('rechazoRankingDesde')?.value || '';
  const hasta = document.getElementById('rechazoRankingHasta')?.value || '';
  const sucursal = document.getElementById('rechazoRankingSucursal')?.value || getSuc();
  const limit = document.getElementById('rechazoRankingLimit')?.value || '25';
  const qs = new URLSearchParams({ desde, hasta, sucursal, limit }).toString();
  try {
    const [clientes, motivos] = await Promise.all([
      api('/api/rechazos/por-cliente?' + qs),
      api('/api/rechazos/por-motivo?' + qs),
    ]);
    document.getElementById('rechazosPorCliente').innerHTML = renderRechazosPorCliente(clientes.datos || []);
    document.getElementById('rechazosPorMotivo').innerHTML = renderRechazosPorMotivo(motivos.datos || []);
  } catch (e) {
    errBox('rechazosPorCliente', e.message);
    errBox('rechazosPorMotivo', e.message);
  }
}

function initDropsizeFilters() {
  const mesEl = document.getElementById('dropMes');
  if (!mesEl) return;
  mesEl.value = mesPad();
  setDropsizeDatesFromMes(false);
  const objDesde = document.getElementById('dropObjDesde');
  if (objDesde) objDesde.value = `${new Date().getFullYear()}-01-01`;
}

function setDropsizeDatesFromMes(reloadData = false) {
  const mesEl = document.getElementById('dropMes');
  if (!mesEl?.value) return;
  const [y, m] = mesEl.value.split('-').map(Number);
  const last = new Date(y, m, 0).getDate();
  document.getElementById('dropDesde').value = `${y}-${String(m).padStart(2, '0')}-01`;
  document.getElementById('dropHasta').value = `${y}-${String(m).padStart(2, '0')}-${String(last).padStart(2, '0')}`;
  if (reloadData) loadDropsize();
}

function getDropSuc() {
  return document.getElementById('dropSucursal')?.value || getSuc();
}

function dropsizeQuery(extra = {}) {
  const p = new URLSearchParams({
    sucursal: getDropSuc(),
    fecha_desde: document.getElementById('dropDesde')?.value || '',
    fecha_hasta: document.getElementById('dropHasta')?.value || '',
    mes: document.getElementById('dropMes')?.value || mesPad(),
    ...extra,
  });
  return p.toString();
}

function trafficBadge(item) {
  const estado = item?.estado || 'sin_objetivo';
  const obj = item?.objetivo;
  const txt = obj ? `Min ${fmtDrop(obj.objetivo_minimo)} / Ideal ${fmtDrop(obj.objetivo_ideal)}` : 'Sin objetivo';
  return `<span class="traffic ${estado}" title="${txt}">${item?.label || 'Sin objetivo'}</span>`;
}

function kpiGoalBadge(item) {
  if (!item?.objetivo) return '';
  const obj = item.objetivo;
  const signo = obj.direccion === 'max' ? '<=' : '>=';
  const alerta = obj.alerta == null ? '' : ` / alerta ${fmtDrop(obj.alerta)}${obj.unidad || ''}`;
  const txt = `${obj.nombre}: ${signo} ${fmtDrop(obj.objetivo)}${obj.unidad || ''}${alerta}`;
  return `<div class="kpi-goal"><span class="traffic ${item.estado}" title="${esc(txt)}">${item.label}</span></div>`;
}

function dropDeltaColor(v) {
  if (v == null) return 'var(--muted)';
  return v >= 0 ? 'var(--grn)' : 'var(--red)';
}

function renderDropsizeKpis(d) {
  document.getElementById('dropKpis').innerHTML = `
    <div class="kpi-section">Clientes</div>
    <div class="kpi blu"><div class="kpi-lbl">Entregas consolidadas</div><div class="kpi-val blu">${fmtN(d.entregas_consolidadas || d.clientes_entregados || 0)}</div></div>

    <div class="kpi-section">Bultos</div>
    <div class="kpi ora"><div class="kpi-lbl">Total bultos</div><div class="kpi-val ora">${fmtN(Math.round(d.total_bultos || 0))}</div></div>
    <div class="kpi ora"><div class="kpi-lbl">Dropsize bultos</div><div class="kpi-val ora">${fmtDrop(d.dropsize_bultos || 0)}</div><div>${trafficBadge(d.objetivos?.bultos)}</div></div>

    <div class="kpi-section">Hectolitros</div>
    <div class="kpi pur"><div class="kpi-lbl">Total HL</div><div class="kpi-val pur">${fmtN(Math.round(d.total_hl || 0))}</div></div>
    <div class="kpi pur"><div class="kpi-lbl">Dropsize HL</div><div class="kpi-val pur">${fmtDrop(d.dropsize_hl || 0)}</div><div>${trafficBadge(d.objetivos?.hl)}</div></div>

    <div class="kpi-section">Pallets</div>
    <div class="kpi grn"><div class="kpi-lbl">Total pallets</div><div class="kpi-val grn">${fmtDrop(d.total_pallets || 0)}</div></div>
    <div class="kpi grn"><div class="kpi-lbl">Dropsize pallets</div><div class="kpi-val grn">${fmtDrop(d.dropsize_pallets || 0)}</div><div>${trafficBadge(d.objetivos?.pallets)}</div></div>
  `;
}

function renderDropChart(canvasId, currentChart, labels, datasets) {
  if (!window.Chart) return currentChart;
  const el = document.getElementById(canvasId);
  if (!el) return currentChart;
  if (currentChart) currentChart.destroy();
  const labelLimit = labels.length > 18 ? 14 : 99;
  const labelledDatasets = datasets.map(ds => ({
    ...ds,
    pointRadius: ds.pointRadius ?? 3,
    pointHoverRadius: ds.pointHoverRadius ?? 5,
    labelColor: ds.labelColor || ds.borderColor,
    valueFormatter: ds.valueFormatter || (raw => fmtDrop(raw || 0)),
    maxLabelsPerDataset: labelLimit,
  }));
  return new Chart(el.getContext('2d'), {
    type: 'line',
    data: { labels, datasets: labelledDatasets },
    plugins: [chartValueLabels],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 22 } },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#e8eaf0', boxWidth: 10 } },
        chartValueLabels: { hideZero: true, maxLabelsPerDataset: labelLimit },
      },
      scales: {
        x: { ticks: { color: '#6b7080', maxRotation: 0 }, grid: { color: 'rgba(42,46,58,.35)' } },
        y: { ticks: { color: '#6b7080' }, grid: { color: 'rgba(42,46,58,.35)' } },
      },
    },
  });
}

function renderDropsizeDiaria(data) {
  const dias = data.dias || [];
  dropDiarioChart = renderDropChart('dropChartDiario', dropDiarioChart, dias.map(x => x.fecha?.slice(5)), [
    { label: 'Bultos/cliente', data: dias.map(x => x.dropsize_bultos), borderColor: '#f5a623', backgroundColor: 'rgba(245,166,35,.12)', tension: .25 },
    { label: 'HL/cliente', data: dias.map(x => x.dropsize_hl), borderColor: '#a78bfa', backgroundColor: 'rgba(167,139,250,.12)', tension: .25 },
    { label: 'Pallets/cliente', data: dias.map(x => x.dropsize_pallets), borderColor: '#4caf82', backgroundColor: 'rgba(76,175,130,.12)', tension: .25 },
  ]);

  if (!dias.length) {
    document.getElementById('dropTabla').innerHTML = '<div class="empty"><div class="icon">📊</div>Sin datos de Dropsize</div>';
    return;
  }
  let html = `<table class="rtbl"><thead><tr>
    <th>Fecha</th><th>Entregas</th><th>Bultos</th><th>HL</th><th>Pallets</th>
    <th>Drop bultos</th><th>Drop HL</th><th>Drop pallets</th>
  </tr></thead><tbody>`;
  dias.forEach(x => {
    html += `<tr>
      <td style="font-family:var(--mono)">${x.fecha}</td>
      <td style="font-family:var(--mono)">${fmtN(x.clientes_entregados || 0)}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(x.total_bultos || 0))}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(x.total_hl || 0))}</td>
      <td style="font-family:var(--mono)">${fmtDrop(x.total_pallets || 0)}</td>
      <td style="font-family:var(--mono);color:var(--acc)">${fmtDrop(x.dropsize_bultos || 0)}</td>
      <td style="font-family:var(--mono);color:var(--pur)">${fmtDrop(x.dropsize_hl || 0)}</td>
      <td style="font-family:var(--mono);color:var(--grn)">${fmtDrop(x.dropsize_pallets || 0)}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('dropTabla').innerHTML = html;
}

function renderDropsizeMensual(data) {
  const meses = data.meses || [];
  dropMensualChart = renderDropChart('dropChartMensual', dropMensualChart, meses.map(x => x.mes?.slice(2)), [
    { label: 'Bultos/cliente', data: meses.map(x => x.dropsize_bultos), borderColor: '#f5a623', backgroundColor: 'rgba(245,166,35,.12)', tension: .25 },
    { label: 'HL/cliente', data: meses.map(x => x.dropsize_hl), borderColor: '#a78bfa', backgroundColor: 'rgba(167,139,250,.12)', tension: .25 },
    { label: 'Pallets/cliente', data: meses.map(x => x.dropsize_pallets), borderColor: '#4caf82', backgroundColor: 'rgba(76,175,130,.12)', tension: .25 },
  ]);
}

function renderDropsizeRanking(data) {
  const rows = data.ranking || [];
  const agrupacionLabel = data.agrupacion_label || 'Agrupación';
  if (!rows.length) {
    document.getElementById('dropRanking').innerHTML = '<div class="empty"><div class="icon">📊</div>Sin ranking</div>';
    return;
  }
  let html = `<table class="rtbl"><thead><tr>
    <th>#</th><th>${esc(agrupacionLabel)}</th><th>Entregas</th><th>Drop bultos</th><th>Drop HL</th><th>Drop pallets</th>
  </tr></thead><tbody>`;
  rows.forEach(x => {
    const grupo = x.grupo || x.sucursal || x.grupo_id || '';
    const entregas = x.entregas_consolidadas || x.clientes_entregados || 0;
    html += `<tr>
      <td style="font-family:var(--mono)">${x.ranking}</td>
      <td>${esc(grupo)}</td>
      <td style="font-family:var(--mono)">${fmtN(entregas)}</td>
      <td style="font-family:var(--mono);color:var(--acc)">${fmtDrop(x.dropsize_bultos || 0)}</td>
      <td style="font-family:var(--mono);color:var(--pur)">${fmtDrop(x.dropsize_hl || 0)}</td>
      <td style="font-family:var(--mono);color:var(--grn)">${fmtDrop(x.dropsize_pallets || 0)}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('dropRanking').innerHTML = html;
}

function renderDropsizeComparativo(data) {
  const actual = data.actual || {};
  const prev = data.mes_anterior || {};
  const aa = data.anio_anterior || {};
  const actualRange = data?.periodo_actual?.fecha_desde && data?.periodo_actual?.fecha_hasta
    ? `${data.periodo_actual.fecha_desde} al ${data.periodo_actual.fecha_hasta}`
    : 'rango actual';
  const actualDays = data?.periodo_actual?.dias ? `${data.periodo_actual.dias} días` : 'mismo número de días';
  const rows = [
    ['Entregas', 'clientes_entregados', v => fmtN(v || 0)],
    ['Bultos', 'total_bultos', v => fmtN(Math.round(v || 0))],
    ['HL', 'total_hl', v => fmtN(Math.round(v || 0))],
    ['Pallets', 'total_pallets', v => fmtDrop(v || 0)],
    ['Drop bultos', 'dropsize_bultos', v => fmtDrop(v || 0)],
    ['Drop HL', 'dropsize_hl', v => fmtDrop(v || 0)],
    ['Drop pallets', 'dropsize_pallets', v => fmtDrop(v || 0)],
  ];
  let html = `<div style="font-size:11px;color:var(--muted);margin-bottom:8px;line-height:1.4">
    Compara ${esc(actualRange)} (${actualDays}) contra la ventana equivalente del período anterior y del año anterior.
  </div>`;
  html += `<table class="rtbl"><thead><tr>
    <th>Indicador</th><th>Actual</th><th>Ventana ant.</th><th>Var.</th><th>Año ant.</th><th>Var.</th>
  </tr></thead><tbody>`;
  rows.forEach(([label, key, fmt]) => {
    const vm = prev.variacion_pct?.[key];
    const va = aa.variacion_pct?.[key];
    html += `<tr>
      <td>${label}</td>
      <td style="font-family:var(--mono)">${fmt(actual[key])}</td>
      <td style="font-family:var(--mono)">${fmt(prev.resumen?.[key])}</td>
      <td style="font-family:var(--mono);color:${dropDeltaColor(vm)}">${fmtDelta(vm)}</td>
      <td style="font-family:var(--mono)">${fmt(aa.resumen?.[key])}</td>
      <td style="font-family:var(--mono);color:${dropDeltaColor(va)}">${fmtDelta(va)}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('dropComparativo').innerHTML = html;
}

function renderDropsizePicos(data) {
  const rows = data.dias || [];
  if (!rows.length) {
    document.getElementById('dropPicos').innerHTML = '<div class="empty"><div class="icon">📈</div>Sin días pico en el período</div>';
    return;
  }
  let html = `<table class="rtbl"><thead><tr><th>Fecha</th><th>Motivo</th><th>Entregas</th><th>Bultos</th><th>HL</th><th>Pallets</th></tr></thead><tbody>`;
  rows.forEach(x => {
    html += `<tr>
      <td style="font-family:var(--mono)">${x.fecha}</td>
      <td>${(x.motivos || []).map(m => `<span class="tag pico">${m}</span>`).join(' ')}</td>
      <td style="font-family:var(--mono)">${fmtN(x.clientes_entregados || 0)}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(x.total_bultos || 0))}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(x.total_hl || 0))}</td>
      <td style="font-family:var(--mono)">${fmtDrop(x.total_pallets || 0)}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('dropPicos').innerHTML = html;
}

function renderDropsizeObjetivos(rows) {
  dropsizeObjetivos = rows || [];
  if (!dropsizeObjetivos.length) {
    document.getElementById('dropObjetivos').innerHTML = '<div class="empty"><div class="icon">🎯</div>Sin objetivos cargados</div>';
    return;
  }
  let html = `<table class="rtbl"><thead><tr>
    <th>Sucursal</th><th>Unidad</th><th>M?nimo</th><th>Ideal</th><th>Desde</th><th>Hasta</th><th>Estado</th><th></th>
  </tr></thead><tbody>`;
  dropsizeObjetivos.forEach(x => {
    html += `<tr>
      <td>${esc(x.sucursal || 'Todas')}</td>
      <td style="font-family:var(--mono)">${x.unidad}</td>
      <td style="font-family:var(--mono)">${fmtDrop(x.objetivo_minimo)}</td>
      <td style="font-family:var(--mono)">${fmtDrop(x.objetivo_ideal)}</td>
      <td style="font-family:var(--mono)">${x.fecha_desde}</td>
      <td style="font-family:var(--mono)">${x.fecha_hasta || '?'}</td>
      <td>${x.activo ? '<span class="tag ok">Activo</span>' : '<span class="tag err">Inactivo</span>'}</td>
      <td style="display:flex;gap:4px"><button class="btn sm" onclick="editDropsizeObjetivo(${x.id})">Editar</button><button class="btn sm danger" onclick="deleteDropsizeObjetivo(${x.id})">Eliminar</button></td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('dropObjetivos').innerHTML = html;
}

async function loadDropsizePicos() {
  load('dropPicos');
  try {
    const met = document.getElementById('dropPicoMetrica').value;
    const data = await api(`/api/dropsize/dias_pico?${dropsizeQuery({ metrica: met })}`);
    renderDropsizePicos(data);
  } catch (e) {
    errBox('dropPicos', 'Error: ' + e.message);
  }
}

async function loadDropsize() {
  const seq = ++_loadDropSeq;
  if (_dropAbort) _dropAbort.abort();
  _dropAbort = new AbortController();
  ['dropKpis', 'dropRanking', 'dropComparativo', 'dropTabla', 'dropPicos'].forEach(load);
  const q = dropsizeQuery();
  const monthlyQ = new URLSearchParams({ sucursal: getDropSuc(), mes: document.getElementById('dropMes')?.value || mesPad(), meses: document.getElementById('selPeriodoHist').value || '12' });
  const rankUnidad = document.getElementById('dropRankingUnidad')?.value || 'bultos';
  const rankAgrupacion = document.getElementById('dropRankingAgrupacion')?.value || 'sucursal';
  const rankQ = dropsizeQuery({ unidad: rankUnidad, agrupacion: rankAgrupacion });

  try {
    const [resumen, diaria, mensual, ranking, comparativo, picos] = await Promise.all([
      api(`/api/dropsize/resumen?${q}`, { signal: _dropAbort.signal }),
      api(`/api/dropsize/evolucion_diaria?${q}`, { signal: _dropAbort.signal }),
      api(`/api/dropsize/evolucion_mensual?${monthlyQ.toString()}`, { signal: _dropAbort.signal }),
      api(`/api/dropsize/ranking_sucursales?${rankQ}`, { signal: _dropAbort.signal }),
      api(`/api/dropsize/comparativo?${dropsizeQuery()}`, { signal: _dropAbort.signal }),
      api(`/api/dropsize/dias_pico?${dropsizeQuery({ metrica: document.getElementById('dropPicoMetrica').value })}`, { signal: _dropAbort.signal }),
    ]);
    if (seq !== _loadDropSeq) return;
    renderDropsizeKpis(resumen);
    renderDropsizeDiaria(diaria);
    renderDropsizeMensual(mensual);
    renderDropsizeRanking(ranking);
    renderDropsizeComparativo(comparativo);
    renderDropsizePicos(picos);
  } catch (e) {
    if (e.name === 'AbortError') return;
    errBox('dropKpis', 'Error: ' + e.message);
  }
}

async function loadDropsizeObjetivos() {
  if (!document.getElementById('dropObjetivos')) return;
  load('dropObjetivos');
  try {
    const rows = await api(`/api/dropsize/objetivos?sucursal=${getSuc()}`);
    renderDropsizeObjetivos(rows);
  } catch (e) {
    errBox('dropObjetivos', 'Error: ' + e.message);
  }
}

function editDropsizeObjetivo(id) {
  const x = dropsizeObjetivos.find(o => Number(o.id) === Number(id));
  if (!x) return;
  document.getElementById('dropObjId').value = x.id;
  document.getElementById('dropObjSucursal').value = x.sucursal_id || 'TODAS';
  document.getElementById('dropObjUnidad').value = x.unidad;
  document.getElementById('dropObjMin').value = x.objetivo_minimo;
  document.getElementById('dropObjIdeal').value = x.objetivo_ideal;
  document.getElementById('dropObjDesde').value = x.fecha_desde;
  document.getElementById('dropObjHasta').value = x.fecha_hasta || '';
}

async function deleteDropsizeObjetivo(id) {
  if (!confirm('¿Eliminar este objetivo?')) return;
  try {
    const r = await fetch(API + '/api/dropsize/objetivos/' + id, { method: 'DELETE' });
    if (!r.ok) throw new Error('Error al eliminar');
    await loadDropsizeObjetivos();
    if (document.getElementById('tab-dropsize')?.style.display !== 'none') await loadDropsize();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function saveDropsizeObjetivo() {
  const msg = document.getElementById('dropObjMsg');
  msg.style.color = 'var(--muted)';
  msg.textContent = 'Guardando...';
  const payload = {
    id: document.getElementById('dropObjId').value || null,
    sucursal_id: document.getElementById('dropObjSucursal').value,
    unidad: document.getElementById('dropObjUnidad').value,
    objetivo_minimo: Number(document.getElementById('dropObjMin').value || 0),
    objetivo_ideal: Number(document.getElementById('dropObjIdeal').value || 0),
    fecha_desde: document.getElementById('dropObjDesde').value,
    fecha_hasta: document.getElementById('dropObjHasta').value || null,
    activo: true,
  };
  try {
    const r = await fetch(API + '/api/dropsize/objetivos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || 'Error');
    msg.style.color = 'var(--grn)';
    msg.textContent = 'Objetivo guardado';
    document.getElementById('dropObjId').value = '';
    await loadDropsizeObjetivos();
    if (document.getElementById('tab-dropsize')?.style.display !== 'none') await loadDropsize();
  } catch (e) {
    msg.style.color = 'var(--red)';
    msg.textContent = e.message;
  }
}

async function recalcularDropsize() {
  const msg = document.getElementById('dropObjMsg');
  msg.style.color = 'var(--muted)';
  msg.textContent = 'Recalculando histórico...';
  try {
    const r = await fetch(API + '/api/dropsize/recalcular', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sucursal: getDropSuc(),
        fecha_desde: document.getElementById('dropDesde').value,
        fecha_hasta: document.getElementById('dropHasta').value,
        mes: document.getElementById('dropMes').value,
      }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || 'Error');
    msg.style.color = 'var(--grn)';
    msg.textContent = `Histórico recalculado: ${fmtN(data.registros || 0)} filas`;
    await loadDropsize();
  } catch (e) {
    msg.style.color = 'var(--red)';
    msg.textContent = e.message;
  }
}

function exportDropsizeExcel() {
  window.location.href = `${API}/api/dropsize/export?${dropsizeQuery()}`;
}

function openDrawer(fecha) {
  document.getElementById('drawerTitle').textContent = fecha;
  document.getElementById('drawerBody').innerHTML = '<div class="loading"><div class="spinner"></div>Cargando detalle…</div>';
  document.getElementById('drawer').classList.add('open');
  loadDayDetail(fecha);
}

function closeDrawer() {
  if (_drawerAbort) _drawerAbort.abort();
  document.getElementById('drawer').classList.remove('open');
  selDay = null;
  renderCal();
}

async function loadDayDetail(fecha) {
  if (_drawerAbort) _drawerAbort.abort();
  _drawerAbort = new AbortController();
  const sig  = _drawerAbort.signal;
  const body = document.getElementById('drawerBody');

  try {
    const fetchJ = (url) => fetch(url, { signal: sig }).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    const [detail, equipos, disponibles] = await Promise.allSettled([
      fetchJ(`${API}/api/picos/dia?sucursal=${getSuc()}&fecha=${fecha}`),
      cfg.equiposUrl     ? fetchJ(`${API}/api/recursos/equipos?url=${encodeURIComponent(cfg.equiposUrl)}&fecha=${fecha}&sucursal=${getSuc()}`)     : Promise.reject('no url'),
      cfg.disponiblesUrl ? fetchJ(`${API}/api/recursos/disponibles?url=${encodeURIComponent(cfg.disponiblesUrl)}&fecha=${fecha}&sucursal=${getSuc()}`) : Promise.reject('no url'),
    ]);

    if (sig.aborted) return;

    const d    = detail.status      === 'fulfilled' ? detail.value              : null;
    const eq   = equipos.status     === 'fulfilled' ? equipos.value.equipos     || [] : [];
    const disp = disponibles.status === 'fulfilled' ? disponibles.value.disponibles || [] : [];
    const di   = diasData.find(x => x.fecha === fecha) || {};

    let html = '';

    if (di.es_evento && di.evento_desc) {
      html += `<div style="background:rgba(239,68,68,.08);border:1px dashed rgba(239,68,68,.45);border-radius:6px;padding:10px 14px;font-size:12px">
        <span style="font-weight:600;color:var(--red)">&#9888; Evento especial</span>
        <span style="color:var(--muted);margin-left:8px">${dayDetailText(di.evento_desc, 'Sin dato')}</span>
        <div style="margin-top:4px;font-size:11px;color:var(--muted)">La venta de este d&iacute;a se distribuye antes o despu&eacute;s.</div>
      </div>`;
    }
    if (di.es_feriado && di.feriado_desc) {
      html += `<div style="background:rgba(167,139,250,.1);border:1px solid rgba(167,139,250,.35);border-radius:6px;padding:8px 14px;font-size:12px">
        <span style="font-weight:600;color:var(--pur)">Feriado:</span>
        <span style="color:var(--muted);margin-left:6px">${dayDetailText(di.feriado_desc, 'Sin dato')}</span>
      </div>`;
    }

    if (d?.detalle_nota) {
      html += `<div style="margin-top:8px;background:rgba(91,141,238,.08);border:1px solid rgba(91,141,238,.28);border-radius:6px;padding:8px 12px;font-size:12px;color:var(--txt)">
        <div style="font-weight:600;color:var(--blu);margin-bottom:2px">Nota del informe</div>
        <div>${dayDetailText(d.detalle_nota, '')}</div>
        ${d?.detalle_fuente ? `<div style="margin-top:4px;font-size:10px;color:var(--muted)">Fuente: ${dayDetailText(d.detalle_fuente, '')}</div>` : ''}
      </div>`;
    }

    if (di.bultos != null) {
      html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <div class="kpi ora"><div class="kpi-lbl">Bultos desp.</div><div class="kpi-val ora" style="font-size:18px">${fmtN(Math.round(di.bultos))}</div></div>
        <div class="kpi pur"><div class="kpi-lbl">HL desp.</div><div class="kpi-val pur" style="font-size:18px">${fmtN(Math.round(di.hectolitros))}</div></div>
        <div class="kpi grn"><div class="kpi-lbl">PDV atendidos</div><div class="kpi-val grn" style="font-size:18px">${fmtN(di.pedidos || 0)}</div></div>
        <div class="kpi pur"><div class="kpi-lbl">Clientes &uacute;nicos</div><div class="kpi-val pur" style="font-size:18px">${fmtN(d?.clientes_unicos || di.clientes_unicos || 0)}</div></div>
        <div class="kpi red"><div class="kpi-lbl">% rechazo PDV</div><div class="kpi-val red" style="font-size:18px">${fmtPct1(di.pct_rechazo_pedidos ?? 0)}</div></div>
        <div class="kpi red"><div class="kpi-lbl">% rechazo bultos</div><div class="kpi-val red" style="font-size:18px">${fmtPct1(di.pct_rechazo_bultos ?? 0)}</div></div>
        <div class="kpi red"><div class="kpi-lbl">% rechazo HL</div><div class="kpi-val red" style="font-size:18px">${fmtPct1(di.pct_rechazo_hl ?? 0)}</div></div>
        <div class="kpi red"><div class="kpi-lbl">Total bultos rechazados</div><div class="kpi-val red" style="font-size:18px">${fmt1(di.rechazo_bultos || 0)}</div></div>
        <div class="kpi red"><div class="kpi-lbl">Total HL rechazados</div><div class="kpi-val red" style="font-size:18px">${fmt1(di.rechazo_hl || 0)}</div></div>
        <div class="kpi red"><div class="kpi-lbl">PDV rechazados</div><div class="kpi-val red" style="font-size:18px">${fmtN(di.rechazo_pedidos || 0)}</div></div>
        <div class="kpi ora"><div class="kpi-lbl">HL rechazo parcial</div><div class="kpi-val ora" style="font-size:18px">${fmt1(di.rechazo_hl_parcial || 0)}</div></div>
        <div class="kpi ora"><div class="kpi-lbl">HL rechazo completo</div><div class="kpi-val ora" style="font-size:18px">${fmt1(di.rechazo_hl_total || 0)}</div></div>
        <div class="kpi ora"><div class="kpi-lbl">Bultos rechazo parcial</div><div class="kpi-val ora" style="font-size:18px">${fmt1(di.rechazo_bultos_parcial || 0)}</div></div>
        <div class="kpi ora"><div class="kpi-lbl">Bultos rechazo completo</div><div class="kpi-val ora" style="font-size:18px">${fmt1(di.rechazo_bultos_total || 0)}</div></div>
        <div class="kpi blu"><div class="kpi-lbl">RMCYO HL</div><div class="kpi-val blu" style="font-size:18px">${fmtN(Math.round(di.rmcyo_hl || 0))}</div></div>
        <div class="kpi red"><div class="kpi-lbl">RMCYO HL rechazados</div><div class="kpi-val red" style="font-size:18px">${fmt1(di.rmcyo_rechazo_hl || 0)}</div></div>
      </div>`;
    }

    if (disp.length) {
      html += `<div class="sec">Disponibilidad</div>`;
      disp.forEach(r => {
        html += `<div class="box" style="padding:10px 14px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
          <div><div style="font-size:9px;color:var(--muted)">CAMIONES DISP.</div><div style="font-family:var(--mono);font-size:18px;color:var(--grn)">${dayDetailText(r.camiones_disponibles, 'Sin dato')}</div></div>
          <div><div style="font-size:9px;color:var(--muted)">EN TALLER</div><div style="font-family:var(--mono);font-size:18px;color:var(--red)">${dayDetailText(r.camiones_en_taller, 'Sin dato')}</div></div>
          <div><div style="font-size:9px;color:var(--muted)">PERSONAS DISP.</div><div style="font-family:var(--mono);font-size:18px;color:var(--blu)">${dayDetailText(r.personas_disponibles, 'Sin dato')}</div></div>
        </div>`;
      });
    }

    if (d?.planillas?.length) {
      html += `<div class="sec">Salidas &uacute;nicas (${d.salidas_unicas || d.planillas.length})</div>`;
      let t = `<table class="rtbl"><thead><tr><th>Cami&oacute;n</th><th>Patente</th><th>Bultos</th><th>Pallets</th><th>Hora salida</th></tr></thead><tbody>`;
      d.planillas.forEach(p => {
        const sal    = dayDetailTime(p.hora_salida_label ?? p.fecha_salida, 'Sin hora');
        const camion = dayDetailText(p.transporte || p.camion_key, 'Sin dato');
        t += `<tr>
          <td style="font-family:var(--mono)">${camion}</td>
          <td style="font-family:var(--mono)">${dayDetailText(p.patente, 'Sin dato')}</td>
          <td style="font-family:var(--mono)">${fmtN(Math.round(p.bultos_totales || 0))}</td>
          <td style="font-family:var(--mono)">${Math.round(p.pallets || 0)}</td>
          <td style="font-family:var(--mono)">${sal}</td>
        </tr>`;
      });
      t += '</tbody></table>';
      html += t;
    }

    if (d?.clientes_por_sucursal?.length) {
      html += `<div class="sec">Clientes por sucursal</div>
        <table class="rtbl"><thead><tr><th>Sucursal</th><th>Clientes &uacute;nicos</th></tr></thead><tbody>`;
      d.clientes_por_sucursal.forEach(r => {
        html += `<tr><td>${dayDetailText(r.sucursal, 'SIN SUCURSAL')}</td><td style="font-family:var(--mono)">${fmtN(r.clientes_unicos || 0)}</td></tr>`;
      });
      html += '</tbody></table>';
    }

    if (d?.clientes?.length) {
      html += `<div class="sec">Clientes &uacute;nicos</div>
        <table class="rtbl"><thead><tr><th>ID cliente</th><th>Cliente</th><th>Sucursal</th></tr></thead><tbody>`;
      d.clientes.slice(0, 100).forEach(c => {
        html += `<tr>
          <td style="font-family:var(--mono)">${dayDetailText(c.id_cliente, 'Sin dato')}</td>
          <td>${dayDetailText(c.nombre_cliente, 'Sin dato')}</td>
          <td>${dayDetailText(c.sucursal, 'Sin dato')}</td>
        </tr>`;
      });
      if (d.clientes.length > 100) {
        html += `<tr><td colspan="3" style="font-size:12px;color:var(--muted)">Mostrando 100 de ${d.clientes.length} clientes</td></tr>`;
      }
      html += '</tbody></table>';
    }

    if (eq.length) {
      html += `<div class="sec">Equipos de reparto</div>`;
      eq.forEach(r => {
        const ok = r.cargado_tiempo?.toLowerCase().includes('si') || r.cargado_tiempo === '1';
        html += `<div class="box" style="padding:10px 14px">
          <div style="font-size:13px;font-weight:600">${dayDetailText(r.chofer, 'Sin dato')}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:3px">
            &#128667; ${dayDetailText(r.camion, 'Sin dato')}${r.nro_camion != null && r.nro_camion !== '' ? ' #' + dayDetailText(r.nro_camion, '') : ''}
            ${r.ayudante1 ? ' &middot; ' + dayDetailText(r.ayudante1, 'Sin dato') : ''}${r.ayudante2 ? ' &middot; ' + dayDetailText(r.ayudante2, 'Sin dato') : ''}
            &middot; ${dayDetailText(r.personas, 'Sin dato')} pers. &middot; ${dayDetailText(r.pallets, 'Sin dato')} pallets
            ${r.kms != null && r.kms !== '' ? ' &middot; ' + dayDetailText(r.kms, 'Sin dato') + ' km' : ''}${r.horas != null && r.horas !== '' ? ' &middot; ' + dayDetailText(r.horas, 'Sin dato') + ' hs' : ''}
          </div>
          ${r.cargado_tiempo ? `<div style="margin-top:5px"><span class="tag ${ok ? 'ok' : 'err'}">${ok ? '&#10003; A tiempo' : '&#10007; Tarde'}</span></div>` : ''}
        </div>`;
      });
    }

    if (d?.top_articulos?.length) {
      html += `<div class="sec">Top art&iacute;culos</div>
        <table class="rtbl"><thead><tr><th>Art&iacute;culo</th><th>Bultos</th><th>HL</th><th>Bultos rechazados</th><th>HL rechazados</th><th>PDV rechazados</th></tr></thead><tbody>`;
      d.top_articulos.slice(0, 15).forEach(a => {
        html += `<tr>
          <td>${dayDetailText(a.descripcion_articulo, 'Sin dato')}</td>
          <td style="font-family:var(--mono)">${Math.round(a.bultos || 0)}</td>
          <td style="font-family:var(--mono)">${Math.round(a.hl || 0)}</td>
          <td style="font-family:var(--mono);color:${a.b_rec > 0 ? 'var(--red)' : 'var(--muted)'}">${Math.round(a.b_rec || 0)}</td>
          <td style="font-family:var(--mono);color:${a.hl_rec > 0 ? 'var(--red)' : 'var(--muted)'}">${Math.round(a.hl_rec || 0)}</td>
          <td style="font-family:var(--mono);color:${a.p_rec > 0 ? 'var(--red)' : 'var(--muted)'}">${a.p_rec || 0}</td>
        </tr>`;
      });
      html += '</tbody></table>';
    }

    if (d?.rechazos?.length) {
      html += `<div class="sec">Motivos de rechazo</div>
        <table class="rtbl"><thead><tr><th>Motivo</th><th>PDV rechazados</th><th>Total bultos rechazados</th><th>Bultos rechazo parcial</th><th>Bultos rechazo completo</th><th>Total HL rechazados</th><th>HL rechazo parcial</th><th>HL rechazo completo</th></tr></thead><tbody>`;
      d.rechazos.forEach(r => {
        html += `<tr>
          <td>${r.motivo}</td>
          <td style="font-family:var(--mono)">${r.pedidos || 0}</td>
          <td style="font-family:var(--mono);color:var(--red)">${Math.round(r.bultos || 0)}</td>
          <td style="font-family:var(--mono);color:var(--acc)">${Math.round(r.bultos_parcial || 0)}</td>
          <td style="font-family:var(--mono);color:var(--red)">${Math.round(r.bultos_total || 0)}</td>
          <td style="font-family:var(--mono);color:var(--red)">${Math.round(r.hectolitros || 0)}</td>
          <td style="font-family:var(--mono);color:var(--acc)">${Math.round(r.hectolitros_parcial || 0)}</td>
          <td style="font-family:var(--mono);color:var(--red)">${Math.round(r.hectolitros_total || 0)}</td>
        </tr>`;
      });
      html += '</tbody></table>';
    }

    if (!html) html = '<div class="empty"><div class="icon">&#128196;</div>Sin datos para este d&iacute;a</div>';
    body.innerHTML = html;
  } catch (e) {
    if (e.name === 'AbortError') return;
    body.innerHTML = `<div class="err-box">Error: ${e.message}</div>`;
  }
}

// ─── UMBRAL / MÉTRICA ─────────────────────────────────────────
function onUmbralChange(v) {
  document.getElementById('lblUmbral').textContent = '+' + Math.round((v - 1) * 100) + '%';
  umbral = parseFloat(v);
}

function setUmbral(v) {
  document.getElementById('sliderUmbral').value = v;
  onUmbralChange(v);
  refreshPicoDependentViews();
}

async function guardarUmbral() {
  const v  = parseFloat(document.getElementById('sliderUmbral').value);
  const m  = document.getElementById('selMetrica').value;
  const el = document.getElementById('umbralMsg');
  try {
    await fetch(API + '/api/parametros', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sucursal: getSuc(), umbral_pct: v, metrica: m }),
    });
    el.style.color  = 'var(--grn)';
    el.textContent  = '✓ Guardado';
    setTimeout(() => el.textContent = '', 2000);
    await refreshPicoDependentViews();
  } catch (e) {
    el.style.color = 'var(--red)';
    el.textContent = 'Error';
  }
}

async function onMetricaChange() {
  metrica = document.getElementById('selMetrica').value;
  await refreshPicoDependentViews();
}

async function onSucursalChange() {
  const selVentaDia = document.getElementById('ventaDiaSucursal');
  if (selVentaDia) selVentaDia.value = getSuc();
  const selVentaAnual = document.getElementById('ventaAnualSucursal');
  if (selVentaAnual) selVentaAnual.value = getSuc();
  const selExp = document.getElementById('expSucursal');
  if (selExp) selExp.value = getSuc();
  const expLoc = document.getElementById('expLocalidad');
  const expTipo = document.getElementById('expTipoNegocio');
  if (expLoc) expLoc.value = 'TODAS';
  if (expTipo) expTipo.value = 'TODAS';
  document.getElementById('cfgSucursal').value = getSuc();
  if (document.getElementById('dropSucursal')) document.getElementById('dropSucursal').value = getSuc();
  if (document.getElementById('planSucursal')) document.getElementById('planSucursal').value = getSuc();
  await loadParams(false);
  await refreshPicoDependentViews();
  loadArticulosCount();
}

async function onVentaDiaSucursalChange() {
  const sel = document.getElementById('ventaDiaSucursal');
  const globalSel = document.getElementById('selSucursal');
  if (!sel || !globalSel) return;
  globalSel.value = sel.value;
  await onSucursalChange();
}

// ─── UPLOAD ──────────────────────────────────────────────────
let uploadOpen = true;
function toggleUpload() {
  uploadOpen = !uploadOpen;
  document.getElementById('uploadBody').style.display  = uploadOpen ? '' : 'none';
  document.getElementById('uploadToggleIcon').textContent = uploadOpen ? 'â–¾' : 'â–¸';
}

async function loadArticulosCount() {
  const el = document.getElementById('articulosCount');
  const missingEl = document.getElementById('articulosSinClasificar');
  const infoEl = document.getElementById('articulosSinClasificarInfo');
  if (!el) return;
  try {
    const d = await api('/api/articulos/count');
    el.textContent = fmtN(d.total);
  } catch (e) { el.textContent = 'Error'; }
  if (!missingEl) return;
  try {
    const d = await api(`/api/articulos/sin-clasificar?mes=${mesPad()}&sucursal=${getSuc()}&limit=3`);
    missingEl.textContent = fmtN(d.articulos);
    missingEl.style.color = d.articulos > 0 ? 'var(--red)' : 'var(--grn)';
    if (infoEl) {
      if (d.articulos > 0) {
        const top = (d.top || [])
          .map(x => `${x.id_articulo} - ${esc(x.descripcion_articulo)} (${fmtN(x.filas)} filas)`)
          .join('<br>');
        infoEl.innerHTML = `${fmtN(d.filas)} filas excluidas del calculo del mes.${top ? '<br>' + top : ''}`;
      } else {
        infoEl.textContent = 'Sin articulos del detalle pendientes de cargar en la tabla articulos.';
      }
    }
  } catch (e) {
    missingEl.textContent = 'Error';
    if (infoEl) infoEl.textContent = '';
  }
}

async function uploadFile(tipo, force = false) {
  const ids = {
    articulos: 'fileArticulos',
    resumen: 'fileResumen',
    detalle: 'fileDetalle',
    ventasDetalle: 'fileVentasDetalle',
    clientes: 'fileClientes',
    transportes: 'fileTransportes',
    rechazos: 'fileRechazos',
  };
  const stIds = {
    articulos: 'stArticulos',
    resumen: 'stResumen',
    detalle: 'stDetalle',
    ventasDetalle: 'stVentasDetalle',
    clientes: 'stClientes',
    transportes: 'stTransportes',
    rechazos: 'stRechazos',
  };
  const fi = document.getElementById(ids[tipo]);
  const st = document.getElementById(stIds[tipo]);
  if (!fi.files.length) { st.textContent = 'Sin archivo'; st.className = 'upload-status err'; return; }
  const fd = new FormData();
  fd.append('file', fi.files[0]);
  if (force) fd.append('force', 'true');
  if (tipo === 'resumen' || tipo === 'detalle' || tipo === 'ventasDetalle') {
    const suc = document.getElementById('uploadSucursal').value;
    if (!suc) { st.textContent = 'Elegí sucursal'; st.className = 'upload-status err'; return; }
    fd.append('sucursal', suc);
  }
  st.textContent = 'Subiendo?'; st.className = 'upload-status';
  try {
    const endpoint = tipo === 'ventasDetalle' ? 'ventas-detalle' : tipo;
    const r = await fetch(`${API}/api/upload/${endpoint}`, { method: 'POST', body: fd });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Error');
    st.textContent = `✓ ${d.inserted || d.total || 0} filas`;
    st.className   = 'upload-status ok';
    if (tipo === 'articulos') loadArticulosCount();
    else {
      await refreshPicoDependentViews();
      loadArticulosCount();
    }
  } catch (e) { st.textContent = '✗ ' + e.message; st.className = 'upload-status err'; }
}

// ─── FERIADOS ────────────────────────────────────────────────
async function syncFeriados() {
  const url = document.getElementById('inputFeriadosUrl').value.trim();
  const st  = document.getElementById('stFeriados');
  if (!url) { st.style.color = 'var(--red)'; st.textContent = 'Ingresá la URL del Sheet'; return; }
  st.style.color = 'var(--muted)'; st.textContent = 'Sincronizando…';
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 30000); // 30s max
  try {
    const r = await fetch(API + '/api/feriados', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sheets_url: url }),
      signal: abort.signal,
    });
    clearTimeout(timer);
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Error del servidor');
    const extra = d.errors > 0 ? ` (${d.errors} errores, ${d.skipped || 0} omitidos)` : '';
    st.style.color = 'var(--grn)';
    st.textContent = `✓ ${d.imported} feriados importados${extra}`;
    cfg.feriadosUrl = url;
    localStorage.setItem('pico_cfg', JSON.stringify(cfg));
    loadMes(); loadFeriados();
  } catch (e) {
    clearTimeout(timer);
    st.style.color = 'var(--red)';
    st.textContent = e.name === 'AbortError' ? 'Tiempo agotado (30s). Verific? la URL.' : 'Error: ' + e.message;
  }
}

async function loadFeriados() {
  const el = document.getElementById('ferList');
  if (!el) return;
  try {
    const data      = await api(`/api/feriados?anio=${vY}`);
    const mesFiltro = mesPad();
    const delMes    = data.filter(f => f.fecha.startsWith(mesFiltro));
    const otros     = data.filter(f => !f.fecha.startsWith(mesFiltro));
    const mesNombre = MESES[vM] + ' ' + vY;

    const tipoTag = (t) => {
      const v = (t || '').toLowerCase();
      const lbl = v === 'local' ? 'Empresa' : t ? 'Feriado AR' : '';
      const col = v === 'local' ? 'var(--acc)' : 'var(--pur)';
      return lbl ? `<span style="font-family:var(--mono);font-size:10px;color:${col};background:rgba(0,0,0,.25);padding:1px 6px;border-radius:3px;margin:0 6px">${lbl}</span>` : '';
    };

    const list = delMes.length ? delMes : data.slice(0, 12);

    const mesHeader = delMes.length
      ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
           <span style="font-size:11px;color:var(--muted)">${delMes.length} feriado${delMes.length !== 1 ? 's' : ''} en ${mesNombre}</span>
            ${delMes.length > 2
              ? `<button class="btn sm danger" onclick="limpiarFeriadosMes()" title="Elimina todos los feriados de ${mesNombre}">Limpiar ${MESES[vM]}</button>`
              : ''}
         </div>`
      : `<div style="font-size:11px;color:var(--muted);margin-bottom:6px">Sin feriados en ${mesNombre}. Mostrando otros del a?o.</div>`;

    if (!data.length) {
      el.innerHTML = `<div style="font-size:11px;color:var(--muted);padding:4px 0">Sin feriados registrados para ${vY}.</div>`;
      return;
    }

    const rows = list.map(f => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--brd);font-size:12px">
        <span>
          <span style="font-family:var(--mono);color:var(--pur)">${f.fecha}</span>
          ${tipoTag(f.tipo)}
          ${f.descripcion}
        </span>
        <button class="btn sm danger" onclick="deleteFeriado('${f.fecha}')">✕</button>
      </div>`).join('');

    const extra = otros.length && delMes.length
      ? `<div style="font-size:11px;color:var(--muted);padding:4px 0;margin-top:4px">${otros.length} feriado${otros.length !== 1 ? 's' : ''} m?s en ${vY}</div>`
      : '';

    el.innerHTML = mesHeader + rows + extra;
  } catch (er) { if (el) el.innerHTML = ''; }
}

async function limpiarFeriadosMes() {
  const mesNombre = MESES[vM] + ' ' + vY;
  if (!confirm(`¿Eliminar TODOS los feriados de ${mesNombre}?`)) return;
  try {
    await fetch(`${API}/api/feriados/mes/${vY}/${vM + 1}`, { method: 'DELETE' });
    loadFeriados();
    loadMes();
  } catch(e) { alert('Error: ' + e.message); }
}

async function limpiarAnio() {
  const st = document.getElementById('stFeriados');
  if (!confirm(`¿Eliminar TODOS los feriados de ${vY}? Luego podés volver a sincronizar desde el Sheet.`)) return;
  st.style.color = 'var(--muted)';
  st.textContent = 'Limpiando?';
  try {
    const r = await fetch(`${API}/api/feriados/anio/${vY}`, { method: 'DELETE' });
    const d = await r.json();
    st.style.color = 'var(--grn)';
    st.textContent = `✓ ${d.deleted} feriados eliminados de ${vY}`;
    loadFeriados();
    loadMes();
  } catch(e) {
    st.style.color = 'var(--red)';
    st.textContent = 'Error: ' + e.message;
  }
}

async function addFeriado() {
  const fecha = document.getElementById('ferFecha').value;
  const desc  = document.getElementById('ferDesc').value.trim();
  const tipo  = document.getElementById('ferTipo').value;
  const inp   = document.getElementById('ferDesc');
  if (!fecha || !desc) { inp.style.borderColor = 'var(--red)'; return; }
  inp.style.borderColor = '';
  try {
    await fetch(`${API}/api/feriados`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fecha, descripcion: desc, tipo }),
    });
    inp.value = '';
    loadFeriados(); loadMes();
  } catch (e) { alert('Error al guardar feriado'); }
}

async function deleteFeriado(fecha) {
  await fetch(`${API}/api/feriados/${fecha}`, { method: 'DELETE' });
  loadFeriados(); loadMes();
}

// ─── EVENTOS ESPECIALES ───────────────────────────────────────
async function loadEventos() {
  const el = document.getElementById('evList');
  if (!el) return;
  try {
    const data = await api(`/api/eventos?mes=${mesPad()}&sucursal=${getSuc()}`);
    if (!data.length) {
      el.innerHTML = '<div style="font-size:11px;color:var(--muted);padding:6px 0">Sin eventos para este mes.</div>';
      return;
    }
    el.innerHTML = data.map(e => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--brd);font-size:12px">
        <span>
          <span style="font-family:var(--mono);color:var(--acc)">${e.fecha}</span>
          <span style="color:var(--muted);margin:0 6px;font-size:10px">${e.sucursal}</span>
          ${e.descripcion}
        </span>
        <button class="btn sm danger" onclick="deleteEvento(${e.id})">✕</button>
      </div>`).join('');
  } catch (er) { if (el) el.innerHTML = ''; }
}

async function addEvento() {
  const fecha = document.getElementById('evFecha').value;
  const suc   = document.getElementById('evSucursal').value;
  const desc  = document.getElementById('evDesc').value.trim();
  const inp   = document.getElementById('evDesc');
  if (!fecha || !desc) { inp.style.borderColor = 'var(--red)'; return; }
  inp.style.borderColor = '';
  try {
    await fetch(`${API}/api/eventos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fecha, sucursal: suc, descripcion: desc }),
    });
    inp.value = '';
    await loadEventos();
    await refreshPicoDependentViews();
  } catch (e) { alert('Error al guardar evento'); }
}

async function deleteEvento(id) {
  await fetch(`${API}/api/eventos/${id}`, { method: 'DELETE' });
  await loadEventos();
  await refreshPicoDependentViews();
}

// ─── RECHAZOS ─────────────────────────────────────────────────
async function loadRechazos() {
  load('rechazosGrid');
  try {
    const data = await api('/api/rechazos');
    renderRechazosTable(data);
  } catch(e) { errBox('rechazosGrid', e.message); }
}

function renderRechazosTable(rows) {
  if (!rows.length) {
    document.getElementById('rechazosGrid').innerHTML =
      '<div class="empty"><div class="icon">📋</div>Sin motivos registrados. Sincroniz? desde el detalle.</div>';
    return;
  }
  let html = `<table class="rtbl"><thead><tr>
    <th>Motivo</th><th>Filas en DB</th><th>Bultos</th><th>?Contar?</th>
  </tr></thead><tbody>`;
  for (const r of rows) {
    html += `<tr>
      <td>${esc(r.motivo_rechazo)}</td>
      <td style="font-family:var(--mono);color:var(--muted)">${fmtN(r.filas)}</td>
      <td style="font-family:var(--mono);color:var(--muted)">${fmtN(Math.round(r.bultos))}</td>
      <td>
        <button class="tag ${r.tomar ? 'ok' : 'err'}"
                onclick="toggleTomar('${jsEsc(r.motivo_key)}', ${!r.tomar})"
                style="cursor:pointer;border:none;font-size:11px;padding:3px 10px">
          ${r.tomar ? 'SÍ' : 'NO'}
        </button>
      </td>
    </tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('rechazosGrid').innerHTML = html;
}

async function toggleTomar(key, val) {
  try {
    const res = await fetch(API + '/api/rechazos/' + encodeURIComponent(key), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tomar: val }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      throw new Error(err?.error || `HTTP ${res.status}`);
    }
    loadRechazos();
  } catch(e) { alert('Error al actualizar: ' + e.message); }
}

async function syncRechazos() {
  const btn = document.getElementById('btnSyncRechazos');
  const msg = document.getElementById('syncRechazosMsg');
  btn.disabled = true;
  btn.textContent = 'Sincronizando…';
  try {
    const r = await fetch(API + '/api/rechazos/sync', { method: 'POST' });
    const d = await r.json();
    msg.style.color = 'var(--grn)';
    msg.textContent = d.inserted > 0 ? `✓ ${d.inserted} nuevos motivos` : '✓ Sin nuevos motivos';
    loadRechazos();
  } catch(e) {
    msg.style.color = 'var(--red)';
    msg.textContent = 'Error: ' + e.message;
  }
  btn.disabled = false;
  btn.textContent = '↻ Sincronizar desde detalle';
}

// ─── CONFIG ──────────────────────────────────────────────────
function saveConfig() {
  cfg.equiposUrl     = document.getElementById('cfgEquiposUrl').value.trim();
  cfg.disponiblesUrl = document.getElementById('cfgDisponiblesUrl').value.trim();
  cfg.dotacionEntregaUrl = document.getElementById('cfgDotacionEntregaUrl')?.value.trim() || '';
  cfg.dotacionRecargasUrl = document.getElementById('cfgDotacionRecargasUrl')?.value.trim() || '';
  localStorage.setItem('pico_cfg', JSON.stringify(cfg));
  const m = document.getElementById('cfgMsg');
  m.textContent = '✓ Guardado';
  setTimeout(() => m.textContent = '', 2000);
}

async function saveParams() {
  const suc = document.getElementById('cfgSucursal').value;
  const u   = parseFloat(document.getElementById('cfgUmbral').value);
  const met = document.getElementById('cfgMetrica').value;
  try {
    await fetch(API + '/api/parametros', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sucursal: suc, umbral_pct: u, metrica: met }),
    });
    const m = document.getElementById('paramsMsg');
    m.textContent = '✓ Guardado';
    setTimeout(() => m.textContent = '', 2000);
    if (suc === getSuc()) {
      document.getElementById('sliderUmbral').value = u;
      document.getElementById('selMetrica').value   = met;
      onUmbralChange(u);
      metrica = met;
      await refreshPicoDependentViews();
    }
  } catch (e) {
    document.getElementById('paramsMsg').style.color  = 'var(--red)';
    document.getElementById('paramsMsg').textContent  = 'Error';
  }
}

// ─── TABS ────────────────────────────────────────────────────
function renderKpiObjetivos(rows) {
  kpiObjetivos = rows || [];
  const el = document.getElementById('kpiObjetivos');
  if (!el) return;
  if (!kpiObjetivos.length) {
    el.innerHTML = '<div class="empty"><div class="icon">🎯</div>Sin objetivos KPI cargados</div>';
    return;
  }
  const sum = key => diasData.reduce((acc, d) => acc + Number(d[key] || 0), 0);
  const total = {
    bultos: mesKpis.bultos ?? sum('bultos'),
    hectolitros: mesKpis.hectolitros ?? sum('hectolitros'),
    pallets: mesKpis.pallets ?? sum('pallets'),
    up: mesKpis.up ?? sum('up'),
    pedidos: mesKpis.pedidos ?? sum('pedidos'),
    clientes: mesKpis.clientes ?? sum('clientes_unicos'),
    pct_rechazo_pedidos: mesKpis.pct_rechazo_pedidos ?? 0,
    pct_rechazo_bultos: mesKpis.pct_rechazo_bultos ?? 0,
    pct_rechazo_hl: mesKpis.pct_rechazo_hl ?? 0,
    camiones: diasData.reduce((s,d)=>s+(d.dot?.tiene_datos?d.dot.total_camiones:0),0) || mesKpis.camiones || sum('camiones_salidos'),
    picos: diasData.filter(d => d.es_pico).length,
    feriados: diasData.filter(d => d.es_feriado).length,
    eventos: diasData.filter(d => d.es_evento).length,
  };
  let html = `<table class="rtbl"><thead><tr>
    <th>Sucursal</th><th>Indicador</th><th>Regla</th><th>Alerta</th><th>Desde</th><th>Hasta</th><th>Estado</th><th></th>
  </tr></thead><tbody>`;
  kpiObjetivos.forEach(x => {
    const signo = x.direccion === 'max' ? '<=' : '>=';
    html += `<tr>
      <td>${esc(x.sucursal || 'Todas')}</td>
      <td>${esc(x.nombre)}</td>
      <td style="font-family:var(--mono)">${signo} ${fmtDrop(x.objetivo)}${x.unidad || ''}</td>
      <td style="font-family:var(--mono)">${x.alerta == null ? '?' : fmtDrop(x.alerta) + (x.unidad || '')}</td>
      <td style="font-family:var(--mono)">${x.fecha_desde}</td>
      <td style="font-family:var(--mono)">${x.fecha_hasta || '?'}</td>
      <td>${x.activo ? '<span class="tag ok">Activo</span>' : '<span class="tag err">Inactivo</span>'}</td>
      <td style="display:flex;gap:4px"><button class="btn sm" onclick="editKpiObjetivo(${x.id})">Editar</button><button class="btn sm danger" onclick="deleteKpiObjetivo(${x.id})">Eliminar</button></td>
    </tr>`;
  });
  html += `</tbody><tfoot><tr class="total-row">
    <td>Total mes</td>
    <td>${fmtN(Math.round(total.bultos || 0))}</td>
    <td>${fmtN(Math.round(total.hectolitros || 0))}</td>
    <td>${fmtN(Math.round(total.pallets || 0))}</td>
    <td>${fmtN(Math.round(total.up || 0))}</td>
    <td>${fmtN(total.pedidos || 0)}</td>
    <td>${fmtN(total.clientes || 0)}</td>
    <td>${fmtPct1(total.pct_rechazo_pedidos || 0)}</td>
    <td>${fmtPct1(total.pct_rechazo_bultos || 0)}</td>
    <td><span class="pct-pill ${(total.pct_rechazo_hl || 0) > 5 ? 'bad' : 'ok'}">${fmtPct1(total.pct_rechazo_hl || 0)}</span></td>
    <td>${fmtN(total.camiones || 0)}</td>
    <td>${fmtN(total.picos || 0)}</td>
    <td>${fmtN(total.feriados || 0)}</td>
    <td>${fmtN(total.eventos || 0)}</td>
  </tr></tfoot></table>`;
  el.innerHTML = html;
}

async function loadKpiObjetivos() {
  const el = document.getElementById('kpiObjetivos');
  if (!el) return;
  load('kpiObjetivos');
  try {
    const rows = await api(`/api/kpi-objetivos?sucursal=${getSuc()}`);
    renderKpiObjetivos(rows);
  } catch (e) {
    errBox('kpiObjetivos', 'Error: ' + e.message);
  }
}

function editKpiObjetivo(id) {
  const x = kpiObjetivos.find(o => Number(o.id) === Number(id));
  if (!x) return;
  document.getElementById('kpiObjId').value = x.id;
  document.getElementById('kpiObjSucursal').value = x.sucursal_id || 'TODAS';
  document.getElementById('kpiObjIndicador').value = x.indicador;
  document.getElementById('kpiObjObjetivo').value = x.objetivo;
  document.getElementById('kpiObjAlerta').value = x.alerta ?? '';
  document.getElementById('kpiObjDesde').value = x.fecha_desde;
  document.getElementById('kpiObjHasta').value = x.fecha_hasta || '';
}

async function deleteKpiObjetivo(id) {
  if (!confirm('¿Eliminar este objetivo KPI?')) return;
  try {
    const r = await fetch(API + '/api/kpi-objetivos/' + id, { method: 'DELETE' });
    if (!r.ok) throw new Error('Error al eliminar');
    await loadKpiObjetivos();
    await refreshPicoDependentViews();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function saveKpiObjetivo() {
  const msg = document.getElementById('kpiObjMsg');
  msg.style.color = 'var(--muted)';
  msg.textContent = 'Guardando...';
  const payload = {
    id: document.getElementById('kpiObjId').value || null,
    sucursal_id: document.getElementById('kpiObjSucursal').value,
    indicador: document.getElementById('kpiObjIndicador').value,
    objetivo: Number(document.getElementById('kpiObjObjetivo').value || 0),
    alerta: document.getElementById('kpiObjAlerta').value || null,
    fecha_desde: document.getElementById('kpiObjDesde').value,
    fecha_hasta: document.getElementById('kpiObjHasta').value || null,
    activo: true,
  };
  try {
    const r = await fetch(API + '/api/kpi-objetivos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || 'Error');
    msg.style.color = 'var(--grn)';
    msg.textContent = 'Objetivo KPI guardado';
    document.getElementById('kpiObjId').value = '';
    await loadKpiObjetivos();
    await refreshPicoDependentViews();
  } catch (e) {
    msg.style.color = 'var(--red)';
    msg.textContent = e.message;
  }
}

// ─── PLANIFICACION PICOS ────────────────────────────
function setPlanMsg(msg, isErr = false) {
  const el = document.getElementById('planMsg');
  if (!el) return;
  el.style.color = isErr ? 'var(--red)' : 'var(--grn)';
  el.textContent = msg || '';
}

function planPayload() {
  return {
    empresa_id: document.getElementById('planEmpresa')?.value || '1',
    sucursal_id: document.getElementById('planSucursal')?.value || 'TODAS',
    anio_plan: Number(document.getElementById('planAnio')?.value || new Date().getFullYear()),
    mes_plan: Number(document.getElementById('planMes')?.value || (new Date().getMonth() + 1)),
    anio_base: Number(document.getElementById('planAnioBase')?.value || (new Date().getFullYear() - 1)),
    factor_hl: Number(document.getElementById('planFactorHl')?.value || 1),
    factor_pdv: Number(document.getElementById('planFactorPdv')?.value || 1),
    factor_salidas: Number(document.getElementById('planFactorSalidas')?.value || 1),
    factor_rechazos: Number(document.getElementById('planFactorRechazos')?.value || 1),
    factor_dias_pico: Number(document.getElementById('planFactorDiasPico')?.value || 1),
    factor_camiones: Number(document.getElementById('planFactorCamiones')?.value || 1),
    factor_empleados: Number(document.getElementById('planFactorEmpleados')?.value || 1),
  };
}

async function fetchPlanJson(url, options = {}) {
  const r = await fetch(API + url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function estadoClass(estado) {
  const e = String(estado || '').toUpperCase();
  if (e === 'CRITICO') return 'err';
  if (e === 'ALERTA') return 'pico';
  return 'ok';
}

function switchPlanSubtab(t, el) {
  document.querySelectorAll('#tab-planificacion .plan-tab').forEach(x => x.classList.remove('active'));
  if (el) el.classList.add('active');
  document.querySelectorAll('#tab-planificacion .plan-sub').forEach(x => x.style.display = 'none');
  const target = document.getElementById('plan-sub-' + t);
  if (target) target.style.display = '';
}

function _showPlanEmpty() {
  const el = document.getElementById('planKpis');
  if (el) el.innerHTML = `
    <div style="padding:24px;text-align:center;color:var(--muted)">
      <div style="font-size:13px;margin-bottom:12px">Seleccioná el mes y hacé clic en <strong style="color:var(--acc)">Buscar</strong> para ver el plan, o en <strong style="color:var(--acc)">Generar</strong> para crear uno nuevo.</div>
    </div>`;
  ['planResumenTabla','planDiasTabla','planAlertas','planCapacidadTabla'].forEach(id => {
    const e = document.getElementById(id); if (e) e.innerHTML = '';
  });
  clearPlanCharts?.();
}

async function loadPlanificacion() {
  const p = planPayload();
  const kpiEl = document.getElementById('planKpis');
  if (kpiEl) kpiEl.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando planificación… (la primera vez puede demorar hasta 90 s mientras se prepara la base de datos)</div>';
  try {
    const qs = new URLSearchParams({
      empresa_id: p.empresa_id,
      sucursal_id: p.sucursal_id,
      anio: p.anio_plan,
      mes: p.mes_plan,
    });
    const data = await api('/api/planificacion_picos/resumen?' + qs.toString(), { timeout: 90000 });
    renderPlanificacion(data);
    loadDotacionExternaPlanificacion();
    loadDotacionEntregaRealPlanificacion();
    loadFlotaPlanificacion();
    await loadConfigPlanificacion();
  } catch (e) {
    errBox('planKpis', e.message);
    setPlanMsg(e.message, true);
  }
}

function renderPlanificacion(data) {
  const plan = data.plan;
  planActualId = plan.id || null;
  planEscenarioActivoId = data.escenario_activo?.id || data.plan_comparativo?.escenario_id || null;
  if (!plan) {
    const mes = MESES[Number(document.getElementById('planMes')?.value || 0) - 1] || '';
    const anio = document.getElementById('planAnio')?.value || '';
    document.getElementById('planKpis').innerHTML = `
      <div style="padding:24px;border-radius:8px;background:var(--surf2);text-align:center;grid-column:1/-1">
        <div style="font-size:22px;margin-bottom:8px">📋</div>
        <div style="font-size:14px;font-weight:600;margin-bottom:6px">No hay plan para ${mes} ${anio}</div>
        <div style="font-size:12px;color:var(--muted);margin-bottom:14px">Hacé clic en <strong>Generar</strong> para crear el plan del mes basado en el histórico.</div>
        <button class="btn primary" onclick="generarPlanificacion()">Generar plan para ${mes} ${anio}</button>
      </div>`;
    document.getElementById('planResumenTabla').innerHTML = '';
    document.getElementById('planDiasTabla').innerHTML = '';
    document.getElementById('planAlertas').innerHTML = '';
    document.getElementById('planCapacidadTabla').innerHTML = '';
    clearPlanCharts?.();
    return;
  }
  renderPlanKpis(data);
  renderPlanResumenTabla(data);
  renderPlanEscenarios(data);
  renderPlanVariables(data);
  renderPlanDias(data.dias || []);
  document.getElementById('planAlertas').innerHTML = renderPlanAlertas(data.alertas || []);
  renderPlanCapacidad(data.capacidad || {});
  renderPlanCharts(data);
  setPlanMsg(`Planificaci?n #${plan.id} cargada`);
}

function kpiCard(label, value, color = 'ora', badge = '') {
  return `<div class="kpi ${color}"><div class="kpi-lbl">${label}</div><div class="kpi-val ${color}">${value}</div>${badge}</div>`;
}

function renderPlanKpis(data) {
  const p = data.plan_comparativo || data.plan || {};
  const r = data.real || {};
  const icm = data.icm || {};
  const badge = `<span class="tag ${estadoClass(r.estado_general || icm.estado)}">${r.estado_general || icm.estado || 'PLAN'}</span>`;
  document.getElementById('planKpis').innerHTML = `
    ${kpiCard('HL plan', fmtN(Math.round(p.hl_plan || 0)), 'pur')}
    ${kpiCard('HL real', r.hl_real == null ? '—' : fmtN(Math.round(r.hl_real || 0)), 'pur')}
    ${kpiCard('Desvío HL', r.desvio_hl_pct == null ? '—' : fmtPct1(r.desvio_hl_pct), 'red', badge)}
    ${kpiCard('Días pico del plan', fmtN(Math.round(p.dias_pico_plan || 0)), 'ora')}
    ${kpiCard('Días pico real', r.dias_pico_real == null ? '—' : fmtN(Math.round(r.dias_pico_real || 0)), 'ora')}
    ${kpiCard('ICM', `${fmt1(icm.valor || 0)}`, icm.estado === 'CRITICO' ? 'red' : icm.estado === 'ALERTA' ? 'ora' : 'grn', `<span class="tag ${estadoClass(icm.estado)}">${icm.estado || 'NORMAL'}</span>`)}
    ${kpiCard('Salidas plan', fmtN(Math.round(p.salidas_plan || 0)), 'blu')}
    ${kpiCard('PDV plan', fmtN(Math.round(p.pdv_unicos_plan || 0)), 'grn')}
    ${kpiCard('Rechazos plan', fmtPct1(p.rechazos_pct_plan || 0), 'red')}
    ${kpiCard('Escenario', esc(p.escenario_tipo || 'AUTO'), p.escenario_tipo === 'MANUAL' ? 'ora' : 'blu', `<span class="tag ok">${esc(p.escenario_nombre || 'AUTO')}</span>`)}
  `;
}

function renderPlanResumenTabla(data) {
  const base = data.plan || {};
  const p = data.plan_comparativo || base;
  const r = data.real || {};
  const rows = [
    ['HL', base.hl_base, p.hl_plan, r.hl_real, r.desvio_hl_pct],
    ['Días pico', base.dias_pico_base, p.dias_pico_plan, r.dias_pico_real, r.desvio_dias_pico_pct],
    ['Rechazos %', base.rechazos_pct_base, p.rechazos_pct_plan, r.rechazos_pct_real, r.desvio_rechazos_pct],
    ['Salidas', base.salidas_base, p.salidas_plan, r.salidas_real, r.desvio_salidas_pct],
    ['PDV', base.pdv_unicos_base, p.pdv_unicos_plan, r.pdv_unicos_real, r.desvio_pdv_pct],
    ['Camiones promedio', base.camiones_promedio_base, p.camiones_promedio_plan, r.camiones_promedio_real, r.desvio_camiones_pct],
    ['Empleados normales', base.empleados_normal_base, p.empleados_normal_plan, r.empleados_normal_real, r.desvio_empleados_pct],
  ];
  let html = `<div class="plan-note" style="margin-bottom:8px">Comparando contra: ${esc(p.escenario_nombre || 'AUTO')}</div>`;
  html += `<table class="rtbl"><thead><tr><th>Indicador</th><th>Base LY</th><th>Plan vigente</th><th>Real</th><th>Desvio</th></tr></thead><tbody>`;
  rows.forEach(x => {
    html += `<tr>
      <td>${x[0]}</td>
      <td style="font-family:var(--mono)">${x[1] == null ? '?' : fmtN(Math.round(x[1]))}</td>
      <td style="font-family:var(--mono);color:var(--acc)">${x[2] == null ? '?' : fmtN(Math.round(x[2]))}</td>
      <td style="font-family:var(--mono)">${x[3] == null ? '?' : fmtN(Math.round(x[3]))}</td>
      <td><span class="pct-pill ${Math.abs(Number(x[4] || 0)) > 15 ? 'bad' : 'ok'}">${x[4] == null ? '?' : fmtPct1(x[4])}</span></td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('planResumenTabla').innerHTML = html;
}

function renderPlanDias(rows) {
  if (!rows.length) {
    document.getElementById('planDiasTabla').innerHTML = '<div class="empty">Sin detalle diario.</div>';
    return;
  }
  let html = `<table class="rtbl"><thead><tr>
    <th>Fecha</th><th>HL plan</th><th>HL real</th><th>Salidas plan</th><th>Salidas real</th>
    <th>PDV plan</th><th>PDV real</th><th>Pico plan</th><th>Pico real</th><th>Base equiv.</th><th>Score</th><th>Camiones</th><th>Empleados</th><th>Estado</th>
  </tr></thead><tbody>`;
  rows.forEach(d => {
    html += `<tr>
      <td style="font-family:var(--mono)">${d.fecha}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(d.hl_plan || 0))}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(d.hl_real || 0))}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(d.salidas_plan || 0))}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(d.salidas_real || 0))}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(d.pdv_plan || 0))}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(d.pdv_real || 0))}</td>
      <td>${d.es_pico_planificado ? '<span class="tag pico">PICO</span>' : '<span class="tag ok">Normal</span>'}</td>
      <td>${d.es_pico_real ? '<span class="tag pico">PICO</span>' : '<span class="tag ok">Normal</span>'}</td>
      <td style="font-family:var(--mono)">${d.fecha_base || '-'}</td>
      <td style="font-family:var(--mono)">${fmt1(d.score_asignacion || 0)}</td>
      <td style="font-family:var(--mono)">${fmt1(d.camiones_plan || 0)} / ${fmt1(d.camiones_real || 0)}</td>
      <td style="font-family:var(--mono)">${fmt1(d.empleados_plan || 0)} / ${fmt1(d.empleados_real || 0)}</td>
      <td><span class="tag ${estadoClass(d.estado)}">${d.estado}</span></td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('planDiasTabla').innerHTML = html;
}

function setEscenarioInput(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value == null ? '' : Number(value || 0).toFixed(2);
}

function fillPlanEscenarioForm(plan) {
  if (!plan) return;
  setEscenarioInput('planEscHl', plan.hl_plan);
  setEscenarioInput('planEscDiasPico', plan.dias_pico_plan);
  setEscenarioInput('planEscRechazos', plan.rechazos_pct_plan);
  setEscenarioInput('planEscSalidas', plan.salidas_plan);
  setEscenarioInput('planEscPdv', plan.pdv_unicos_plan);
  setEscenarioInput('planEscCamionesProm', plan.camiones_promedio_plan);
  setEscenarioInput('planEscCamionesPico', plan.camiones_pico_plan);
  setEscenarioInput('planEscEmpNorm', plan.empleados_normal_plan);
  setEscenarioInput('planEscEmpPico', plan.empleados_pico_plan);
}

function renderPlanEscenarios(data) {
  const select = document.getElementById('planEscenarioSelect');
  if (!select) return;
  const escenarios = data.escenarios || [];
  planEscenariosData = escenarios;
  select.innerHTML = escenarios.length
    ? escenarios.map(e => `<option value="${e.id}" ${e.activo ? 'selected' : ''}>${esc(e.nombre)}${e.activo ? ' (vigente)' : ''}</option>`).join('')
    : '<option value="">Sin escenarios</option>';
  select.onchange = () => {
    const selected = planEscenariosData.find(e => String(e.id) === String(select.value));
    if (selected) fillPlanEscenarioForm(selected);
  };
  fillPlanEscenarioForm(data.plan_comparativo || data.plan);
  const msg = document.getElementById('planEscenarioMsg');
  if (msg) msg.textContent = data.escenario_activo ? `Vigente: ${data.escenario_activo.nombre}` : '';
}

function fmtPlanVarValue(value, unidad) {
  if (value == null || value === '') return '<span style="color:var(--muted)">SIN INFORMACI?N</span>';
  if (String(unidad || '').toUpperCase() === 'PCT') return fmtPct1(value);
  return fmtN(Math.round(Number(value || 0)));
}

function renderPlanVariables(data) {
  const el = document.getElementById('planVariablesTabla');
  if (!el) return;
  const varsPlan = data.variables_plan || [];
  const vars = data.variables || [];
  const rows = varsPlan.length
    ? varsPlan
    : vars.map(v => ({
        codigo: v.codigo,
        nombre: v.nombre,
        categoria: v.categoria,
        unidad: v.unidad,
        activo: v.activo,
      }));
  if (!rows.length) {
    el.innerHTML = '<div class="empty">Sin variables configuradas.</div>';
    return;
  }
  let html = `<table class="rtbl"><thead><tr>
    <th>Codigo</th><th>Nombre</th><th>Categoria</th><th>Unidad</th>
    <th>Base</th><th>Plan</th><th>Real</th><th>Desvio</th><th>Impacto ICM</th><th>Estado dato</th>
  </tr></thead><tbody>`;
  rows.forEach(v => {
    const hasInfo = v.valor_plan != null && v.valor_real != null;
    html += `<tr>
      <td style="font-family:var(--mono)">${esc(v.codigo || '')}</td>
      <td>${esc(v.nombre || '')}</td>
      <td>${esc(v.categoria || '')}</td>
      <td style="font-family:var(--mono)">${esc(v.unidad || '')}</td>
      <td style="font-family:var(--mono)">${fmtPlanVarValue(v.valor_base, v.unidad)}</td>
      <td style="font-family:var(--mono);color:var(--acc)">${fmtPlanVarValue(v.valor_plan, v.unidad)}</td>
      <td style="font-family:var(--mono)">${fmtPlanVarValue(v.valor_real, v.unidad)}</td>
      <td>${v.desvio == null ? '<span style="color:var(--muted)">SIN INFORMACI?N</span>' : `<span class="pct-pill ${Math.abs(Number(v.desvio || 0)) > 15 ? 'bad' : 'ok'}">${fmtPct1(v.desvio)}</span>`}</td>
      <td style="font-family:var(--mono)">${v.impacto == null ? '<span style="color:var(--muted)">SIN INFORMACI?N</span>' : fmtPct1(v.impacto)}</td>
      <td>${hasInfo ? '<span class="tag ok">OK</span>' : '<span class="tag pico">SIN INFORMACI?N</span>'}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  el.innerHTML = html;
}

function renderPlanAlertas(alertas) {
  if (!alertas.length) return '<div class="empty"><div class="icon">✓</div>Sin alertas activas</div>';
  return alertas.map(a => `
    <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--brd)">
      <div><span class="tag ${estadoClass(a.estado)}">${a.estado}</span> <span style="font-family:var(--mono);color:var(--muted);font-size:11px">${a.tipo}</span></div>
      <div style="font-size:12px">${a.mensaje}</div>
    </div>
  `).join('');
}

function renderPlanCapacidad(cap) {
  const rows = cap.items || [];
  if (!cap.disponible) {
    document.getElementById('planCapacidadTabla').innerHTML = `<div class="empty"><div class="icon">âš™</div>${cap.mensaje || 'Sin capacidad cargada'}</div>`;
    return;
  }
  let html = `<table class="rtbl"><thead><tr><th>Fecha</th><th>HL plan</th><th>Capacidad HL</th><th>Faltante HL</th><th>Camiones</th><th>Empleados</th><th>Estado</th></tr></thead><tbody>`;
  rows.forEach(r => {
    html += `<tr>
      <td style="font-family:var(--mono)">${r.fecha}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(r.hl_plan || 0))}</td>
      <td style="font-family:var(--mono)">${fmtN(Math.round(r.capacidad_hl || 0))}</td>
      <td style="font-family:var(--mono);color:${r.faltante_hl > 0 ? 'var(--red)' : 'var(--grn)'}">${fmtN(Math.round(r.faltante_hl || 0))}</td>
      <td style="font-family:var(--mono)">${fmt1(r.camiones_plan || 0)} / ${fmt1(r.camiones_disponibles || 0)}</td>
      <td style="font-family:var(--mono)">${fmt1(r.empleados_plan || 0)} / ${fmt1(r.empleados_disponibles || 0)}</td>
      <td><span class="tag ${estadoClass(r.estado)}">${r.estado}</span></td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('planCapacidadTabla').innerHTML = html;
}

async function loadDotacionExternaPlanificacion() {
  const el = document.getElementById('planDotacionExterna');
  if (!el) return;
  const p = planPayload();
  el.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando... dotacion externa...</div>';
  try {
    const qs = new URLSearchParams({
      empresa_id: p.empresa_id,
      estado: 'activo',
      per_page: '500',
    });
    if (p.sucursal_id && p.sucursal_id !== 'TODAS') qs.set('sucursal_id', p.sucursal_id);
    const data = await fetchPlanJson('/api/catalogo/dotacion_operativa?' + qs.toString());
    const r = data.resumen || {};
    const rows = data.por_sucursal || [];
    let html = `<div class="sec" style="margin-bottom:10px">Dotacion nominal externa</div>
      <div class="kpi-grid">
        ${kpiCard('Empleados activos', fmtN(r.total_empleados || 0), 'blu')}
        ${kpiCard('Choferes', fmtN(r.choferes || 0), 'grn')}
        ${kpiCard('Ayudantes', fmtN((r.ayudantes || 0) + (r.acompanantes || 0)), 'ora')}
        ${kpiCard('Operarios', fmtN(r.operarios || 0), 'pur')}
      </div>`;
    if (rows.length) {
      html += `<table class="rtbl" style="margin-top:10px"><thead><tr>
        <th>Sucursal</th><th>Total</th><th>Choferes</th><th>Ayudantes</th><th>Operarios</th>
      </tr></thead><tbody>`;
      rows.forEach(x => {
        html += `<tr>
          <td>${esc(x.sucursal_nombre || x.sucursal_id)}</td>
          <td style="font-family:var(--mono)">${fmtN(x.total_empleados || 0)}</td>
          <td style="font-family:var(--mono)">${fmtN(x.choferes || 0)}</td>
          <td style="font-family:var(--mono)">${fmtN((x.ayudantes || 0) + (x.acompanantes || 0))}</td>
          <td style="font-family:var(--mono)">${fmtN(x.operarios || 0)}</td>
        </tr>`;
      });
      html += '</tbody></table>';
    }
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="empty">Dotacion externa no disponible. Configurar EXTERNAL_API_BASE_URL y EXTERNAL_API_KEY en el backend.</div>`;
  }
}

async function loadDotacionEntregaRealPlanificacion() {
  const el = document.getElementById('planDotacionEntregaReal');
  if (!el) return;
  const p = planPayload();
  el.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando... dotacion real de entrega...</div>';
  try {
    const qs = new URLSearchParams({
      mes: `${p.anio_plan}-${String(p.mes_plan).padStart(2, '0')}`,
    });
    if (p.sucursal_id && p.sucursal_id !== 'TODAS') qs.set('sucursal', p.sucursal_id);
    if (cfg.dotacionEntregaUrl) qs.set('url', cfg.dotacionEntregaUrl);
    if (cfg.dotacionRecargasUrl) qs.set('recargas_url', cfg.dotacionRecargasUrl);
    const data = await fetchPlanJson('/api/recursos/dotacion-entrega?' + qs.toString());
    const r = data.resumen || {};
    const rr = data.recargas?.resumen || r.recargas || {};
    const warnings = data.advertencias || [];
    const dias = data.dias || [];
    const diasRecargas = data.recargas?.dias || [];
    let html = `<div class="sec" style="margin-bottom:10px">Dotacion real de entrega</div>
      <div class="kpi-grid">
        ${kpiCard('Camiones jornada', fmtN(r.camiones_jornada || 0), 'blu')}
        ${kpiCard('Personas jornada', fmtN(r.personas_jornada || 0), 'grn')}
        ${kpiCard('Choferes distintos', fmtN(r.choferes_distintos || 0), 'ora')}
        ${kpiCard('Ayudantes distintos', fmtN(r.ayudantes_distintos || 0), 'pur')}
        ${kpiCard('Clientes', fmtN(Math.round(r.clientes || 0)), 'grn')}
        ${kpiCard('Pallets', fmtN(Math.round(r.pallets || 0)), 'blu')}
      </div>`;
    html += `<div class="sec" style="margin:12px 0 10px">Recargas</div>
      <div class="kpi-grid">
        ${kpiCard('Recargas', fmtN(rr.registros || 0), 'ora')}
        ${kpiCard('Camiones recarga', fmtN(rr.camiones_jornada || 0), 'blu')}
        ${kpiCard('Personas recarga', fmtN(rr.personas_jornada || 0), 'grn')}
        ${kpiCard('Clientes recarga', fmtN(Math.round(rr.clientes || 0)), 'grn')}
        ${kpiCard('UP recarga', fmtN(Math.round(rr.up || 0)), 'pur')}
        ${kpiCard('Salidas total', fmtN(r.salidas_total_con_recargas || r.camiones_jornada || 0), 'ora')}
      </div>`;
    if (warnings.length) {
      html += `<div class="err-box" style="margin-top:10px">${warnings.map(esc).join('<br>')}</div>`;
    }
    if (dias.length) {
      html += `<table class="rtbl" style="margin-top:10px"><thead><tr>
        <th>Fecha</th><th>Camiones</th><th>Personas</th><th>UP</th><th>Clientes</th><th>Pallets</th><th>Sucursales detectadas</th>
      </tr></thead><tbody>`;
      dias.slice(-12).forEach(d => {
        html += `<tr>
          <td style="font-family:var(--mono)">${d.fecha}</td>
          <td style="font-family:var(--mono)">${fmtN(d.camiones || 0)}</td>
          <td style="font-family:var(--mono)">${fmtN(d.personas || 0)}</td>
          <td style="font-family:var(--mono)">${fmtN(Math.round(d.up || 0))}</td>
          <td style="font-family:var(--mono)">${fmtN(Math.round(d.clientes || 0))}</td>
          <td style="font-family:var(--mono)">${fmtN(Math.round(d.pallets || 0))}</td>
          <td>${(d.sucursales || []).map(esc).join(', ') || '<span style="color:var(--muted)">SIN SUCURSAL</span>'}</td>
        </tr>`;
      });
      html += '</tbody></table>';
    } else {
      html += '<div class="empty" style="margin-top:10px">Sin registros reales de entrega para el filtro seleccionado.</div>';
    }
    if (diasRecargas.length) {
      html += `<div class="sec" style="margin:12px 0 8px">Detalle recargas</div>
        <table class="rtbl"><thead><tr>
          <th>Fecha</th><th>Camiones</th><th>Personas</th><th>UP</th><th>Clientes</th><th>Pallets</th><th>Sucursal</th>
        </tr></thead><tbody>`;
      diasRecargas.slice(-12).forEach(d => {
        html += `<tr>
          <td style="font-family:var(--mono)">${d.fecha}</td>
          <td style="font-family:var(--mono)">${fmtN(d.camiones || 0)}</td>
          <td style="font-family:var(--mono)">${fmtN(d.personas || 0)}</td>
          <td style="font-family:var(--mono)">${fmtN(Math.round(d.up || 0))}</td>
          <td style="font-family:var(--mono)">${fmtN(Math.round(d.clientes || 0))}</td>
          <td style="font-family:var(--mono)">${fmtN(Math.round(d.pallets || 0))}</td>
          <td>${(d.sucursales || []).map(esc).join(', ') || '<span style="color:var(--muted)">SIN SUCURSAL</span>'}</td>
        </tr>`;
      });
      html += '</tbody></table>';
    }
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="empty">Dotacion real de entrega no disponible: ${esc(e.message)}</div>`;
  }
}

async function loadFlotaPlanificacion() {
  const el = document.getElementById('planFlotaOperativa');
  if (!el) return;
  const p = planPayload();
  el.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando... flota operativa...</div>';
  try {
    const qs = new URLSearchParams({
      empresa_id: p.empresa_id,
      sucursal_id: p.sucursal_id,
      anio: p.anio_plan,
      mes: p.mes_plan,
    });
    const data = await fetchPlanJson('/api/flota/vehiculos?' + qs.toString());
    const r = data.resumen || {};
    const rows = data.vehiculos || [];
    let html = `<div style="display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
      <div class="sec">Flota operativa ${String(data.mes || p.mes_plan).padStart(2, '0')}/${data.anio || p.anio_plan}</div>
      <button class="btn sm" onclick="loadFlotaPlanificacion()">Actualizar</button>
    </div>
    <div class="kpi-grid">
      ${kpiCard('Vehiculos activos', fmtN(r.activos || 0), 'grn')}
      ${kpiCard('Vehiculos inactivos', fmtN(r.inactivos || 0), 'red')}
      ${kpiCard('Capacidad U.P activa', fmtN(Math.round(r.capacidad_up_activa || 0)), 'blu')}
      ${kpiCard('Carga kg activa', fmtN(Math.round(r.carga_kg_activa || 0)), 'ora')}
      ${kpiCard('Propios', fmtN(r.propios || 0), 'pur')}
    </div>`;
    if (!rows.length) {
      el.innerHTML = html + '<div class="empty" style="margin-top:10px">Sin vehiculos cargados para el filtro seleccionado.</div>';
      return;
    }
    html += `<table class="rtbl" style="margin-top:10px"><thead><tr>
      <th>Estado mes</th><th>Codigo</th><th>Vehiculo</th><th>Sucursal</th><th>Placa</th>
      <th>Marca</th><th>Modelo</th><th>Kg</th><th>U.P</th><th>Motivo</th>
    </tr></thead><tbody>`;
    rows.forEach(v => {
      const disabled = v.anulado ? 'disabled' : '';
      html += `<tr>
        <td>
          <input type="checkbox" ${v.activo_mes ? 'checked' : ''} ${disabled}
            onchange="toggleFlotaMes(${Number(v.id)}, this.checked)">
          <span class="tag ${v.activo_mes ? 'ok' : 'err'}">${v.activo_mes ? 'ACTIVA' : 'INACTIVA'}</span>
        </td>
        <td style="font-family:var(--mono)">${esc(v.codigo || '')}</td>
        <td>${esc(v.descripcion || '')}</td>
        <td>${esc(v.sucursal || v.sucursal_id || '')}</td>
        <td style="font-family:var(--mono)">${esc(v.placa || '')}</td>
        <td>${esc(v.marca || '')}</td>
        <td style="font-family:var(--mono)">${esc(v.modelo || '')}</td>
        <td style="font-family:var(--mono)">${v.carga_maxima_kg == null ? '-' : fmtN(Math.round(v.carga_maxima_kg || 0))}</td>
        <td style="font-family:var(--mono)">${v.capacidad_up == null ? '-' : fmtN(Math.round(v.capacidad_up || 0))}</td>
        <td>${esc(v.motivo_mes || '')}</td>
      </tr>`;
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="empty">Flota operativa no disponible: ${esc(e.message)}</div>`;
  }
}

async function toggleFlotaMes(vehiculoId, activo) {
  const p = planPayload();
  let motivo = '';
  if (!activo) {
    motivo = window.prompt('Motivo de baja mensual', 'MANTENIMIENTO');
    if (motivo === null) {
      loadFlotaPlanificacion();
      return;
    }
    motivo = motivo.trim() || 'NO DISPONIBLE';
  }
  try {
    await fetchPlanJson('/api/flota/disponibilidad', {
      method: 'POST',
      body: JSON.stringify({
        vehiculo_id: vehiculoId,
        anio: p.anio_plan,
        mes: p.mes_plan,
        activo,
        motivo,
      }),
    });
    if (isTabVisible('tab-planificacion')) await loadPlanificacion();
    else await loadFlotaPlanificacion();
  } catch (e) {
    setPlanMsg(e.message, true);
    if (isTabVisible('tab-planificacion')) await loadPlanificacion();
    else await loadFlotaPlanificacion();
  }
}

function clearPlanCharts() {
  Object.values(planCharts).forEach(ch => { if (ch) ch.destroy(); });
  planCharts = {};
}

function renderPlanBar(canvasId, label, planVal, realVal, color = '#f5a623') {
  if (!window.Chart) return;
  const el = document.getElementById(canvasId);
  if (!el) return;
  if (planCharts[canvasId]) planCharts[canvasId].destroy();
  planCharts[canvasId] = new Chart(el.getContext('2d'), {
    type: 'bar',
    data: {
      labels: ['Plan', 'Real'],
      datasets: [{
        label,
        data: [Number(planVal || 0), Number(realVal || 0)],
        backgroundColor: [color + 'aa', '#5b8deeaa'],
        borderColor: [color, '#5b8dee'],
        borderWidth: 1,
        labelColor: [color, '#5b8dee'],
        valueFormatter: raw => fmtDrop(raw || 0),
      }]
    },
    plugins: [chartValueLabels],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 22 } },
      plugins: {
        legend: { labels: { color: '#e8eaf0' } },
        chartValueLabels: { hideZero: true },
      },
      scales: {
        x: { ticks: { color: '#6b7080' }, grid: { color: 'rgba(42,46,58,.35)' } },
        y: { beginAtZero: true, ticks: { color: '#6b7080' }, grid: { color: 'rgba(42,46,58,.35)' } },
      },
    }
  });
}

function renderPlanCharts(data) {
  const p = data.plan_comparativo || data.plan || {};
  const r = data.real || {};
  renderPlanBar('planChartHl', 'HL', p.hl_plan, r.hl_real, '#a78bfa');
  renderPlanBar('planChartSalidas', 'Salidas', p.salidas_plan, r.salidas_real, '#5b8dee');
  renderPlanBar('planChartPdv', 'PDV', p.pdv_unicos_plan, r.pdv_unicos_real, '#4caf82');
  renderPlanBar('planChartPicos', 'Días pico', p.dias_pico_plan, r.dias_pico_real, '#f5a623');
  renderPlanBar('planChartCapacidad', 'HL capacidad', data.capacidad?.resumen?.hl_plan || p.hl_plan, data.capacidad?.resumen?.capacidad_hl || 0, '#e05c5c');
  renderPlanBar('planChartIcm', 'ICM', 0, data.icm?.valor || 0, '#f5a623');
}

async function generarPlanificacion() {
  setPlanMsg('Generando...');
  try {
    const data = await fetchPlanJson('/api/planificacion_picos/generar', {
      method: 'POST',
      body: JSON.stringify(planPayload()),
    });
    renderPlanificacion(data);
  } catch (e) {
    setPlanMsg(e.message, true);
  }
}

async function actualizarRealPlanificacion() {
  if (!planActualId) return setPlanMsg('Primero generá o cargá una planificación.', true);
  setPlanMsg('Actualizando real...');
  try {
    const data = await fetchPlanJson(`/api/planificacion_picos/${planActualId}/actualizar_real`, { method: 'POST', body: '{}' });
    renderPlanificacion(data);
  } catch (e) {
    setPlanMsg(e.message, true);
  }
}

async function recalcularPlanificacion() {
  if (!planActualId) return setPlanMsg('Primero generá o cargá una planificación.', true);
  setPlanMsg('Recalculando...');
  try {
    const data = await fetchPlanJson(`/api/planificacion_picos/${planActualId}/recalcular`, { method: 'POST', body: '{}' });
    renderPlanificacion(data);
  } catch (e) {
    setPlanMsg(e.message, true);
  }
}

function planEscenarioPayload() {
  return {
    nombre: document.getElementById('planEscNombre')?.value || 'Ajuste manual',
    tipo: 'MANUAL',
    activar: true,
    hl_plan: Number(document.getElementById('planEscHl')?.value || 0),
    dias_pico_plan: Number(document.getElementById('planEscDiasPico')?.value || 0),
    rechazos_pct_plan: Number(document.getElementById('planEscRechazos')?.value || 0),
    salidas_plan: Number(document.getElementById('planEscSalidas')?.value || 0),
    pdv_unicos_plan: Number(document.getElementById('planEscPdv')?.value || 0),
    camiones_promedio_plan: Number(document.getElementById('planEscCamionesProm')?.value || 0),
    camiones_pico_plan: Number(document.getElementById('planEscCamionesPico')?.value || 0),
    empleados_normal_plan: Number(document.getElementById('planEscEmpNorm')?.value || 0),
    empleados_pico_plan: Number(document.getElementById('planEscEmpPico')?.value || 0),
  };
}

async function guardarEscenarioPlanificacion() {
  if (!planActualId) return setPlanMsg('Primero generá o cargá una planificación.', true);
  setPlanMsg('Guardando escenario...');
  try {
    const data = await fetchPlanJson(`/api/planificacion_picos/${planActualId}/escenarios`, {
      method: 'POST',
      body: JSON.stringify(planEscenarioPayload()),
    });
    renderPlanificacion(data);
  } catch (e) {
    setPlanMsg(e.message, true);
  }
}

async function activarEscenarioPlanificacion() {
  if (!planActualId) return setPlanMsg('Primero generá o cargá una planificación.', true);
  const escenarioId = document.getElementById('planEscenarioSelect')?.value;
  if (!escenarioId) return setPlanMsg('Seleccioná un escenario.', true);
  setPlanMsg('Activando escenario...');
  try {
    const data = await fetchPlanJson(`/api/planificacion_picos/${planActualId}/escenarios/${escenarioId}/activar`, {
      method: 'POST',
      body: '{}',
    });
    renderPlanificacion(data);
  } catch (e) {
    setPlanMsg(e.message, true);
  }
}

async function simularPlanificacion() {
  if (!planActualId) return setPlanMsg('Primero generá o cargá una planificación.', true);
  try {
    const data = await fetchPlanJson('/api/planificacion_picos/simulador', {
      method: 'POST',
      body: JSON.stringify({
        planificacion_id: planActualId,
        delta_hl_pct: Number(document.getElementById('simDeltaHl')?.value || 0),
        delta_pdv_pct: Number(document.getElementById('simDeltaPdv')?.value || 0),
        delta_dias_pico: Number(document.getElementById('simDeltaPicos')?.value || 0),
        delta_rechazos_pct: Number(document.getElementById('simDeltaRechazos')?.value || 0),
      }),
    });
    const p = data.proyeccion || {};
    document.getElementById('planSimResultado').innerHTML = `
      ${kpiCard('HL proyectados', fmtN(Math.round(p.hl || 0)), 'pur')}
      ${kpiCard('PDV proyectados', fmtN(Math.round(p.pdv_unicos || 0)), 'grn')}
      ${kpiCard('Días pico', fmtN(Math.round(p.dias_pico || 0)), 'ora')}
      ${kpiCard('Rechazos', fmtPct1(p.rechazos_pct || 0), 'red')}
      ${kpiCard('Camiones req.', fmt1(p.camiones_requeridos || 0), 'blu')}
      ${kpiCard('Empleados req.', fmt1(p.empleados_requeridos || 0), 'blu', `<span class="tag ${estadoClass(data.riesgo)}">${data.riesgo}</span>`)}
    `;
    switchPlanSubtab('simulador', document.querySelector('.plan-tab[onclick*="simulador"]'));
  } catch (e) {
    setPlanMsg(e.message, true);
  }
}

function exportPlanificacion(formato) {
  if (!planActualId) return setPlanMsg('Primero generá o cargá una planificación.', true);
  if (formato === 'pdf') {
    fetchPlanJson(`/api/planificacion_picos/export?planificacion_id=${planActualId}&formato=pdf`)
      .catch(e => setPlanMsg(e.message, true));
    return;
  }
  window.location.href = `${API}/api/planificacion_picos/export?planificacion_id=${planActualId}&formato=${formato}`;
}

async function loadConfigPlanificacion() {
  const p = planPayload();
  try {
    const cfg = await api(`/api/planificacion_picos/configuracion?empresa_id=${p.empresa_id}&sucursal_id=${p.sucursal_id}`);
    document.getElementById('cfgPlanUmbralHl').value = cfg.umbral_pico_hl_pct ?? 20;
    document.getElementById('cfgPlanUmbralSalidas').value = cfg.umbral_pico_salidas_pct ?? 20;
    document.getElementById('cfgPlanUmbralPdv').value = cfg.umbral_pico_pdv_pct ?? 20;
    document.getElementById('cfgPlanAlerta').value = cfg.umbral_alerta_desvio_pct ?? 15;
    document.getElementById('cfgPlanCritico').value = cfg.umbral_critico_desvio_pct ?? 30;
  } catch (e) {}
}

async function guardarConfigPlanificacion() {
  const p = planPayload();
  const msg = document.getElementById('planCfgMsg');
  try {
    await fetchPlanJson('/api/planificacion_picos/configuracion', {
      method: 'POST',
      body: JSON.stringify({
        empresa_id: p.empresa_id,
        sucursal_id: p.sucursal_id,
        umbral_pico_hl_pct: Number(document.getElementById('cfgPlanUmbralHl').value || 20),
        umbral_pico_salidas_pct: Number(document.getElementById('cfgPlanUmbralSalidas').value || 20),
        umbral_pico_pdv_pct: Number(document.getElementById('cfgPlanUmbralPdv').value || 20),
        umbral_alerta_desvio_pct: Number(document.getElementById('cfgPlanAlerta').value || 15),
        umbral_critico_desvio_pct: Number(document.getElementById('cfgPlanCritico').value || 30),
      }),
    });
    msg.style.color = 'var(--grn)';
    msg.textContent = 'Configuraci?n guardada';
    if (isTabVisible('tab-planificacion')) await loadPlanificacion();
    else await loadConfigPlanificacion();
  } catch (e) {
    msg.style.color = 'var(--red)';
    msg.textContent = e.message;
  }
}

async function guardarVariablePlanificacion() {
  const p = planPayload();
  const msg = document.getElementById('planVarMsg');
  const payload = {
    empresa_id: p.empresa_id,
    sucursal_id: p.sucursal_id,
    codigo: document.getElementById('varPlanCodigo')?.value || '',
    nombre: document.getElementById('varPlanNombre')?.value || '',
    categoria: document.getElementById('varPlanCategoria')?.value || 'OPERACION',
    unidad: document.getElementById('varPlanUnidad')?.value || '',
    activo: true,
  };
  if (!payload.codigo.trim() || !payload.nombre.trim()) {
    if (msg) {
      msg.style.color = 'var(--red)';
      msg.textContent = 'Codigo y nombre son requeridos';
    }
    return;
  }
  try {
    await fetchPlanJson('/api/planificacion_picos/variables', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (msg) {
      msg.style.color = 'var(--grn)';
      msg.textContent = 'Variable guardada';
    }
    ['varPlanCodigo', 'varPlanNombre', 'varPlanCategoria', 'varPlanUnidad'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    await loadPlanificacion();
  } catch (e) {
    if (msg) {
      msg.style.color = 'var(--red)';
      msg.textContent = e.message;
    }
  }
}

function switchTab(t, el) {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
  ['kpis', 'historico', 'venta-dia', 'venta-anual', 'comparativo', 'experiencia', 'dotacion', 'analisis', 'dropsize', 'planificacion', 'operaciones', 'simulador', 'calibres', 'upload', 'config', 'ayuda'].forEach(x => {
    const el2 = document.getElementById('tab-' + x);
    if (el2) el2.style.display = x === t ? '' : 'none';
  });
  if (t === 'historico')   loadHistorico();
  if (t === 'venta-dia')   loadVentaDia();
  if (t === 'venta-anual') loadVentaAnual();
  if (t === 'comparativo') loadComparativo();
  if (t === 'experiencia') loadExperienciaClientes();
  if (t === 'dotacion')    loadDotacion();
  if (t === 'analisis')    { loadAnalisisHl(); loadRechazosRankings(); }
  if (t === 'calibres')    loadCalibres();
  if (t === 'dropsize')  {
    if (document.getElementById('dropSucursal')) document.getElementById('dropSucursal').value = getSuc();
    if (document.getElementById('dropMes')) {
      document.getElementById('dropMes').value = mesPad();
      setDropsizeDatesFromMes(false);
    }
    loadDropsize();
  }
  if (t === 'upload')    { loadArticulosCount(); loadEventos(); loadFeriados(); }
  if (t === 'config')    { initAusentismoDefaults(); loadAusentismoMensual(); loadSucursalesConfig(); loadRechazos(); loadKpiObjetivos(); loadDropsizeObjetivos(); }
  if (t === 'planificacion') {
    // Sync mes/a?o con el calendario principal
    const anioEl = document.getElementById('planAnio');
    const mesEl  = document.getElementById('planMes');
    if (anioEl) anioEl.value = vY;
    if (mesEl)  mesEl.value  = vM + 1;
    if (document.getElementById('planSucursal')) document.getElementById('planSucursal').value = getSuc();
    // No auto-cargar: mostrar estado vac?o para evitar esperas largas
    _showPlanEmpty();
  }
  if (t === 'operaciones') {
    initFlotaSelects();
    const subtabFlota = document.querySelector('#oper-sub-flota .plan-tab.active')?.textContent?.trim();
    if (subtabFlota === 'Camiones') loadCamiones();
    else loadFlota();
  }
  if (t === 'simulador') initSimulador();
}

// ── CRUD CAMIONES ──────────────────────────────────────────────────────────

async function loadCamiones() {
  const tbody = document.getElementById('camionesTbody');
  if (!tbody) return;
  const incluirAnulados = document.getElementById('camMostrarAnulados')?.checked ? '1' : '0';
  tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:20px"><div class="spinner" style="display:inline-block"></div> Cargando?</td></tr>';
  try {
    const data = await api(`/api/flota/vehiculos?incluir_anulados=${incluirAnulados}`);
    _camionesTodos = data.vehiculos || [];
    _renderCamionesResumen(data.resumen);
    filtrarCamiones();
    _populateCamSucursal();
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="9" style="color:var(--red);text-align:center;padding:16px">? ${e.message}</td></tr>`;
  }
}

function _renderCamionesResumen(resumen) {
  const el = document.getElementById('camionesResumen');
  if (!el || !resumen) return;
  el.innerHTML = `
    <div class="mini"><span class="lbl">Total</span><span class="val">${resumen.total||0}</span></div>
    <div class="mini"><span class="lbl">Propios</span><span class="val">${resumen.propios||0}</span></div>
    <div class="mini"><span class="lbl">Cap. UP</span><span class="val" style="color:var(--acc)">${resumen.capacidad_up_activa||0}</span></div>
    <div class="mini"><span class="lbl">Carga kg</span><span class="val">${(resumen.carga_kg_activa||0).toLocaleString()}</span></div>
  `;
}

function _renderCamionesTbody(rows) {
  const tbody = document.getElementById('camionesTbody');
  rows = rows || [];
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:20px">Sin camiones. Agregá uno o sincronizá desde Transportes.</td></tr>';
    return;
  }
  const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  tbody.innerHTML = rows.map(v => {
    const anulado = v.anulado;
    const base    = _estadoActivo(v.activo_base);
    return `<tr style="${anulado ? 'opacity:.5' : ''}">
      <td style="font-family:var(--mono);font-size:11px">${esc(v.codigo)}</td>
      <td style="font-size:12px">${esc(v.descripcion)}</td>
      <td style="font-family:var(--mono);font-size:11px">${esc(v.placa||'?')}</td>
      <td style="font-size:11px">${esc(v.sucursal||v.sucursal_id)}</td>
      <td style="font-family:var(--mono);font-size:11px;text-align:right">${v.capacidad_up ?? '?'}</td>
      <td style="font-family:var(--mono);font-size:11px;text-align:right">${v.carga_maxima_kg ?? '?'}</td>
      <td style="font-size:11px;text-align:center">${v.propio ? '✓' : '?'}</td>
      <td style="font-size:11px;text-align:center;color:${base?'var(--grn)':'var(--red)'}">${base?'Activo':'Inactivo'}</td>
      <td>
        <div style="display:flex;gap:4px">
          <button class="btn sm" onclick="editarCamion(${v.id})" style="font-size:10px">✎</button>
          <button class="btn sm danger" onclick="confirmarEliminarCamion(${v.id},'${esc(v.codigo)}')" style="font-size:10px">✕</button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

function _estadoActivo(valor) {
  return valor === true || valor === 1 || valor === '1';
}

function _camionesFiltrados() {
  const q = (document.getElementById('camBuscar')?.value || '').toLowerCase();
  const estado = document.getElementById('camFiltroEstado')?.value || 'todos';
  return _camionesTodos.filter(v => {
    const coincideTexto = !q ||
      String(v.codigo||'').toLowerCase().includes(q) ||
      String(v.descripcion||'').toLowerCase().includes(q) ||
      String(v.placa||'').toLowerCase().includes(q);
    const activo = _estadoActivo(v.activo_base);
    const coincideEstado =
      estado === 'todos' ||
      (estado === 'activos' && activo) ||
      (estado === 'inactivos' && !activo);
    return coincideTexto && coincideEstado;
  });
}

function filtrarCamiones() {
  _renderCamionesTbody(_camionesFiltrados());
}

function _populateCamSucursal() {
  const sel = document.getElementById('camSucursal');
  if (!sel || sel.options.length > 1) return;
  api('/api/sucursales').then(list => {
    list.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.value; opt.textContent = `${s.value} - ${s.label}`;
      sel.appendChild(opt);
    });
  }).catch(() => {});
}

function editarCamion(id) {
  const v = _camionesTodos.find(x => x.id === id);
  if (!v) return;
  document.getElementById('camionId').value          = v.id;
  document.getElementById('camCodigo').value         = v.codigo || '';
  document.getElementById('camDescripcion').value    = v.descripcion || '';
  document.getElementById('camSucursal').value       = v.sucursal_id || '';
  document.getElementById('camMarca').value          = v.marca || '';
  document.getElementById('camModelo').value         = v.modelo || '';
  document.getElementById('camPlaca').value          = v.placa || '';
  document.getElementById('camCargaKg').value        = v.carga_maxima_kg ?? '';
  document.getElementById('camCapacidadUp').value    = v.capacidad_up ?? '';
  document.getElementById('camPropio').value         = v.propio ? '1' : '0';
  document.getElementById('camActivoBase').value     = v.activo_base ? '1' : '0';
  document.getElementById('camAnulado').value        = v.anulado ? '1' : '0';
  document.getElementById('camDepositoId').value     = v.deposito_default_id || '';
  document.getElementById('camDepositoNombre').value = v.deposito_default_nombre || '';
  document.getElementById('camObservaciones').value  = v.observaciones || '';
  document.getElementById('camionFormTitulo').textContent = `Editando: ${v.codigo} - ${v.descripcion}`;
  document.getElementById('camionMsg').textContent = '';
  document.getElementById('camCodigo').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function limpiarFormCamion() {
  ['camionId','camCodigo','camDescripcion','camMarca','camModelo','camPlaca',
   'camCargaKg','camCapacidadUp','camDepositoId','camDepositoNombre','camObservaciones'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  document.getElementById('camSucursal').value    = '';
  document.getElementById('camPropio').value      = '1';
  document.getElementById('camActivoBase').value  = '1';
  document.getElementById('camAnulado').value     = '0';
  document.getElementById('camionFormTitulo').textContent = 'Nuevo camión';
  document.getElementById('camionMsg').textContent = '';
}

async function guardarCamion() {
  const msg     = document.getElementById('camionMsg');
  const codigo  = document.getElementById('camCodigo').value.trim();
  const desc    = document.getElementById('camDescripcion').value.trim();
  const sucursal= document.getElementById('camSucursal').value.trim();
  if (!codigo) { msg.textContent='⚠ Código requerido'; msg.style.color='var(--red)'; return; }
  if (!desc)   { msg.textContent='⚠ Descripción requerida'; msg.style.color='var(--red)'; return; }
  if (!sucursal){ msg.textContent='? Sucursal requerida'; msg.style.color='var(--red)'; return; }

  const payload = {
    empresa_id:             '1',
    sucursal_id:            sucursal,
    codigo,
    descripcion:            desc,
    marca:                  document.getElementById('camMarca').value.trim() || null,
    modelo:                 document.getElementById('camModelo').value.trim() || null,
    placa:                  document.getElementById('camPlaca').value.trim() || null,
    carga_maxima_kg:        parseFloat(document.getElementById('camCargaKg').value) || null,
    capacidad_up:           parseFloat(document.getElementById('camCapacidadUp').value) || null,
    propio:                 document.getElementById('camPropio').value === '1',
    activo_base:            document.getElementById('camActivoBase').value === '1',
    anulado:                document.getElementById('camAnulado').value === '1',
    deposito_default_id:    document.getElementById('camDepositoId').value.trim() || null,
    deposito_default_nombre:document.getElementById('camDepositoNombre').value.trim() || null,
    observaciones:          document.getElementById('camObservaciones').value.trim() || null,
    fuente:                 'MANUAL',
  };

  msg.textContent = 'Guardando?'; msg.style.color = 'var(--muted)';
  try {
    await api('/api/flota/vehiculos', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    msg.textContent = `✓ Camión "${codigo}" guardado`;
    msg.style.color = 'var(--grn)';
    limpiarFormCamion();
    await loadCamiones();
  } catch(e) {
    msg.textContent = '? ' + e.message;
    msg.style.color = 'var(--red)';
  }
}

async function confirmarEliminarCamion(id, codigo) {
  if (!confirm(`¿Eliminar el camión ${codigo}? Esta acción no se puede deshacer.`)) return;
  try {
    await api(`/api/flota/vehiculos/${id}`, { method: 'DELETE' });
    await loadCamiones();
  } catch(e) {
    alert('Error al eliminar: ' + e.message);
  }
}

// ── SUCURSALES CONFIG ──────────────────────────────────────────────────────

async function loadSucursalesConfig() {
  const el = document.getElementById('sucList');
  if (!el) return;
  try {
    const rows = await api('/api/sucursales');
    if (!rows.length) {
      el.innerHTML = '<div style="color:var(--muted);font-size:11px">Sin sucursales cargadas.</div>';
      return;
    }
    el.innerHTML = `<table class="rtbl" style="width:100%">
      <thead><tr><th style="width:60px">ID</th><th>Nombre</th><th style="width:80px">Estado</th><th style="width:60px"></th></tr></thead>
      <tbody>${rows.map(s => `
        <tr>
          <td style="font-family:var(--mono);font-size:11px">${s.value}</td>
          <td style="font-size:12px">${s.label}</td>
          <td><span style="color:${s.activa !== false ? 'var(--grn)' : 'var(--muted)'};font-size:11px">${s.activa !== false ? 'Activa' : 'Inactiva'}</span></td>
          <td><button class="btn sm" onclick="editarSucursal('${s.value}','${s.label}',${s.activa !== false})" style="font-size:10px">Editar</button></td>
        </tr>`).join('')}
      </tbody></table>`;
  } catch(e) {
    el.innerHTML = `<div style="color:var(--red);font-size:11px">${e.message}</div>`;
  }
}

function editarSucursal(id, nombre, activa) {
  document.getElementById('sucId').value = id;
  document.getElementById('sucNombre').value = nombre;
  document.getElementById('sucActiva').value = activa ? '1' : '0';
}

async function guardarSucursal() {
  const id     = document.getElementById('sucId').value.trim();
  const nombre = document.getElementById('sucNombre').value.trim();
  const activa = document.getElementById('sucActiva').value === '1';
  const msg    = document.getElementById('sucMsg');
  if (!id || !nombre) { msg.textContent = 'ID y nombre requeridos'; msg.style.color='var(--red)'; return; }
  try {
    const res = await fetch('/api/sucursales', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ id, nombre, activa }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    msg.textContent = `✓ Sucursal "${nombre}" guardada`;
    msg.style.color = 'var(--grn)';
    document.getElementById('sucId').value = '';
    document.getElementById('sucNombre').value = '';
    await loadSucursalesConfig();
    await loadSucursales();
  } catch(e) {
    msg.textContent = '? ' + e.message;
    msg.style.color = 'var(--red)';
  }
}

// ── FLOTA ──────────────────────────────────────────────────────────────────

async function loadAusentismoMensual() {
  const anio = Number(document.getElementById('ausAnio')?.value || vY);
  const mes = Number(document.getElementById('ausMes')?.value || (vM + 1));
  const sucursal = document.getElementById('ausSucursal')?.value || 'TODAS';
  const pctInput = document.getElementById('ausPct');
  const msg = document.getElementById('ausMsg');
  const resumen = document.getElementById('ausResumen');
  if (!anio || !mes) return;
  if (msg) { msg.textContent = 'Cargando......'; msg.style.color = 'var(--muted)'; }
  try {
    const qs = new URLSearchParams({ empresa_id: '1', sucursal_id: sucursal, anio: String(anio) });
    const data = await api('/api/picos/ausentismo-mensual?' + qs.toString());
    const meses = data.meses || [];
    const row = meses.find(item => Number(item.mes) === mes);
    if (pctInput) pctInput.value = row && row.pct_ausentismo != null ? row.pct_ausentismo : '';
    if (resumen) {
      resumen.innerHTML = `<table class="rtbl" style="width:100%">
        <thead><tr><th>Mes</th><th style="text-align:right">Ausentismo %</th></tr></thead>
        <tbody>${meses.map(item => `
          <tr>
            <td>${esc(item.nombre || MESES[Number(item.mes || 1) - 1] || item.mes)}</td>
            <td style="font-family:var(--mono);text-align:right;color:${item.pct_ausentismo == null ? 'var(--muted)' : Number(item.pct_ausentismo) >= 10 ? 'var(--red)' : Number(item.pct_ausentismo) >= 5 ? 'var(--acc)' : 'var(--grn)'}">${item.pct_ausentismo == null ? 'Sin dato' : fmtPct1(item.pct_ausentismo)}</td>
          </tr>
        `).join('')}</tbody>
      </table>`;
    }
    if (msg) {
      msg.textContent = row && row.pct_ausentismo != null ? `Dato cargado: ${fmtPct1(row.pct_ausentismo)}` : 'Mes sin dato cargado';
      msg.style.color = 'var(--muted)';
    }
  } catch(e) {
    if (msg) { msg.textContent = e.message; msg.style.color = 'var(--red)'; }
  }
}

async function saveAusentismoMensual() {
  const anio = Number(document.getElementById('ausAnio')?.value || vY);
  const mes = Number(document.getElementById('ausMes')?.value || (vM + 1));
  const sucursal = document.getElementById('ausSucursal')?.value || 'TODAS';
  const pct = Number(document.getElementById('ausPct')?.value || 0);
  const msg = document.getElementById('ausMsg');
  if (!anio || mes < 1 || mes > 12) {
    if (msg) { msg.textContent = 'Año y mes requeridos'; msg.style.color = 'var(--red)'; }
    return;
  }
  if (pct < 0 || pct > 100) {
    if (msg) { msg.textContent = 'El ausentismo debe estar entre 0 y 100%'; msg.style.color = 'var(--red)'; }
    return;
  }
  if (msg) { msg.textContent = 'Guardando...'; msg.style.color = 'var(--muted)'; }
  try {
    await api('/api/picos/ausentismo-mensual', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        empresa_id: '1',
        sucursal_id: sucursal,
        anio,
        filas: [{ mes, pct_ausentismo: pct }],
      }),
    });
    if (msg) { msg.textContent = `Ausentismo de ${MESES[mes - 1]} ${anio} guardado: ${fmtPct1(pct)}`; msg.style.color = 'var(--grn)'; }
    await loadAusentismoMensual();
    await refreshPicoDependentViews();
  } catch(e) {
    if (msg) { msg.textContent = e.message; msg.style.color = 'var(--red)'; }
  }
}

async function importAusentismoHistorico() {
  const msg = document.getElementById('ausImportMsg');
  const file = document.getElementById('ausImportFile')?.files?.[0];
  const text = document.getElementById('ausImportTexto')?.value || '';
  const sucursal = document.getElementById('ausSucursal')?.value || 'TODAS';
  if (!file && !text.trim()) {
    if (msg) { msg.textContent = 'Pegá una tabla o seleccioná un CSV.'; msg.style.color = 'var(--red)'; }
    return;
  }
  if (msg) { msg.textContent = 'Importando histórico...'; msg.style.color = 'var(--muted)'; }
  try {
    let result;
    if (file) {
      const form = new FormData();
      form.append('file', file);
      form.append('empresa_id', '1');
      form.append('sucursal_id', sucursal);
      result = await api('/api/picos/ausentismo-mensual/import', {
        method: 'POST',
        body: form,
        timeout: 120000,
      });
    } else {
      result = await api('/api/picos/ausentismo-mensual/import', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ empresa_id: '1', sucursal_id: sucursal, texto: text }),
        timeout: 120000,
      });
    }
    if (msg) {
      const anios = (result.anios || []).join(', ');
      const sucursales = (result.sucursales || []).join(', ');
      msg.textContent = `Importado: ${fmtN(result.registros)} valores${result.omitidas ? `, ${fmtN(result.omitidas)} celdas omitidas` : ''}. Años: ${anios || '-'} | Sucursales: ${sucursales || '-'}`;
      msg.style.color = 'var(--grn)';
    }
    await loadAusentismoMensual();
    await refreshPicoDependentViews();
  } catch(e) {
    if (msg) { msg.textContent = e.message; msg.style.color = 'var(--red)'; }
  }
}

let _flotaData = [];
let _camionesTodos = [];

function switchOperSubtab(t, el) {
  document.querySelectorAll('#tab-operaciones > .plan-tabs .plan-tab').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('oper-sub-flota').style.display     = t === 'flota'     ? '' : 'none';
  document.getElementById('oper-sub-capacidad').style.display = t === 'capacidad' ? '' : 'none';
  document.getElementById('oper-sub-planilla').style.display  = t === 'planilla'  ? '' : 'none';
  if (t === 'capacidad') {
    loadDotacionExternaPlanificacion();
    loadDotacionEntregaRealPlanificacion();
    loadFlotaPlanificacion();
  }
  if (t === 'planilla') initPlanillaOperativa();
}

function switchFlotaSubtab(t, el) {
  document.querySelectorAll('#oper-sub-flota > .plan-tabs .plan-tab').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('flota-activacion').style.display = t === 'activacion' ? '' : 'none';
  document.getElementById('flota-camiones').style.display   = t === 'camiones'   ? '' : 'none';
  if (t === 'camiones') loadCamiones();
}

function initFlotaSelects() {
  const hoy = new Date();
  const anioEl = document.getElementById('flotaAnio');
  const mesEl  = document.getElementById('flotaMes');
  if (!anioEl.value) anioEl.value = hoy.getFullYear();
  if (!mesEl.value || mesEl.value === '0') mesEl.value = hoy.getMonth() + 1;

  const sucEl = document.getElementById('flotaSucursal');
  if (sucEl.options.length <= 1) {
    api('/api/sucursales').then(list => {
      list.forEach(s => {
        if (sucEl.querySelector(`option[value="${s.value}"]`)) return;
        const opt = document.createElement('option');
        opt.value = s.value; opt.textContent = `${s.value} - ${s.label}`;
        sucEl.appendChild(opt);
      });
    }).catch(() => {});
  }
}

function _flotaFiltrada() {
  const estado = document.getElementById('flotaFiltroEstado')?.value || 'todos';
  if (estado === 'activos') return _flotaData.filter(v => _estadoActivo(v.activo_mes));
  if (estado === 'inactivos') return _flotaData.filter(v => !_estadoActivo(v.activo_mes));
  return _flotaData;
}

function _resumenFlotaDesdeRows(rows) {
  const activos = rows.filter(v => _estadoActivo(v.activo_mes));
  const inactivos = rows.length - activos.length;
  const capUp = activos.reduce((s, v) => s + (Number(v.capacidad_up) || 0), 0);
  return {
    total: rows.length,
    activos: activos.length,
    inactivos,
    capacidad_up_activa: Math.round(capUp * 100) / 100,
  };
}

function filtrarFlota() {
  renderFlotaTabla(_flotaFiltrada());
}

async function loadFlota() {
  const anio = document.getElementById('flotaAnio')?.value;
  const mes  = document.getElementById('flotaMes')?.value;
  const suc  = document.getElementById('flotaSucursal')?.value;
  const tbody = document.getElementById('flotaTbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px"><div class="spinner" style="display:inline-block"></div> Cargando?</td></tr>';

  try {
    let path = `/api/flota/vehiculos?anio=${anio||''}&mes=${mes||''}&incluir_anulados=0`;
    if (suc && suc !== 'TODAS') path += `&sucursal_id=${encodeURIComponent(suc)}`;
    const data = await api(path);
    _flotaData = data.vehiculos || [];
    renderFlotaTabla(_flotaFiltrada(), data.resumen);
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="8" style="color:var(--red);text-align:center;padding:16px">? ${e.message}</td></tr>`;
  }
}

function renderFlotaTabla(vehiculos, resumen) {
  vehiculos = vehiculos || [];
  const summaryEl = document.getElementById('flotaSummary');
  const estadoFiltro = document.getElementById('flotaFiltroEstado')?.value || 'todos';
  const resumenVisible = (resumen && estadoFiltro === 'todos') ? resumen : _resumenFlotaDesdeRows(vehiculos);
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="mini" style="min-width:120px"><span class="lbl">Total</span><span class="val">${resumenVisible.total || 0}</span></div>
      <div class="mini" style="min-width:120px"><span class="lbl">Activos mes</span><span class="val" style="color:var(--grn)">${resumenVisible.activos || 0}</span></div>
      <div class="mini" style="min-width:120px"><span class="lbl">Inactivos mes</span><span class="val" style="color:var(--red)">${resumenVisible.inactivos || 0}</span></div>
      <div class="mini" style="min-width:140px"><span class="lbl">Cap. UP activa</span><span class="val" style="color:var(--acc)">${resumenVisible.capacidad_up_activa || 0}</span></div>
    `;
  }

  const tbody = document.getElementById('flotaTbody');
  if (!vehiculos.length) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px">Sin vehículos. Sincronizá desde Transportes primero.</td></tr>';
    return;
  }

  tbody.innerHTML = vehiculos.map((v, i) => {
    const activo = _estadoActivo(v.activo_mes);
    const originalIdx = _flotaData.findIndex(x => x.id === v.id);
    const idx = originalIdx >= 0 ? originalIdx : i;
    return `
      <tr id="flotaRow${v.id}">
        <td style="font-family:var(--mono);font-size:11px">${v.codigo}</td>
        <td style="font-size:12px">${v.descripcion || ''}</td>
        <td style="font-family:var(--mono);font-size:11px">${v.placa || '?'}</td>
        <td style="font-size:11px">${v.sucursal || v.sucursal_id}</td>
        <td style="font-family:var(--mono);font-size:11px;text-align:right">${v.capacidad_up != null ? v.capacidad_up : '?'}</td>
        <td>${_flotaToggleBtn(v.id, activo, idx)}</td>
        <td>
          <input type="text" id="flotaMotivo${v.id}" value="${v.motivo_mes || ''}"
            placeholder="Motivo inactividad"
            style="width:100%;font-size:11px;padding:3px 6px;border-radius:4px;border:1px solid var(--brd);background:var(--surf2);color:var(--txt)">
        </td>
        <td>
          <button class="btn sm" onclick="guardarDisponibilidadFlota(${v.id}, ${idx})" style="font-size:11px">✓</button>
        </td>
      </tr>`;
  }).join('');
}

function _flotaToggleBtn(vehiculoId, activo, idx) {
  const color = activo ? 'var(--grn)' : 'var(--red)';
  const label = activo ? '● ACTIVO' : '○ INACTIVO';
  return `<button data-toggle onclick="toggleFlotaEstado(${vehiculoId}, ${activo}, ${idx})"
    style="background:${color}22;border:1px solid ${color};color:${color};
           border-radius:12px;padding:3px 10px;font-size:11px;cursor:pointer;font-weight:600;white-space:nowrap">
    ${label}
  </button>`;
}

function _actualizarToggle(vehiculoId, activo, idx) {
  const row = document.getElementById(`flotaRow${vehiculoId}`);
  if (!row) return;
  const td = row.querySelector('[data-toggle]')?.parentElement;
  if (td) td.innerHTML = _flotaToggleBtn(vehiculoId, activo, idx);
}

function _actualizarSummaryFlota() {
  renderFlotaTabla(_flotaFiltrada());
}

function toggleFlotaEstado(vehiculoId, estadoActual, idx) {
  if (!_flotaData[idx]) return;
  const nuevoEstado = !estadoActual;
  _flotaData[idx].activo_mes = nuevoEstado;
  _actualizarToggle(vehiculoId, nuevoEstado, idx);
  guardarDisponibilidadFlota(vehiculoId, idx, estadoActual);
}

async function guardarDisponibilidadFlota(vehiculoId, idx, estadoAnterior) {
  if (!_flotaData[idx]) return;
  const anio   = parseInt(document.getElementById('flotaAnio').value);
  const mes    = parseInt(document.getElementById('flotaMes').value);
  const activo = _estadoActivo(_flotaData[idx].activo_mes);
  const motivo = (document.getElementById(`flotaMotivo${vehiculoId}`)?.value || '').trim();
  const msgEl  = document.getElementById('flotaSyncMsg');

  try {
    await api('/api/flota/disponibilidad', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ vehiculo_id: vehiculoId, anio, mes, activo, motivo }),
    });
    _flotaData[idx].motivo_mes = motivo;
    _actualizarSummaryFlota();
    if (msgEl) { msgEl.textContent = ''; }
  } catch(e) {
    // Revertir el toggle si falló
    if (estadoAnterior !== undefined) {
      _flotaData[idx].activo_mes = estadoAnterior;
      _actualizarToggle(vehiculoId, estadoAnterior, idx);
    }
    if (msgEl) { msgEl.textContent = '? ' + e.message; msgEl.style.color = 'var(--red)'; }
  }
}

async function syncFlotaDesdeTransportes() {
  const btn = document.getElementById('btnSyncFlota');
  const msg = document.getElementById('flotaSyncMsg');
  btn.disabled = true;
  msg.textContent = 'Sincronizando…';
  msg.style.color = 'var(--muted)';
  try {
    const data = await api('/api/flota/sync-transportes', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ empresa_id: '1' }),
      timeout: 60000,
    });
    msg.textContent = `✓ ${data.sincronizados} vehículo(s) sincronizados desde Transportes`;
    msg.style.color = 'var(--grn)';
    await loadFlota();
  } catch(e) {
    msg.textContent = '? Error: ' + e.message;
    msg.style.color = 'var(--red)';
  } finally {
    btn.disabled = false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────

async function reload() {
  const drawerOpen = document.getElementById('drawer').classList.contains('open');
  picoSet = new Set(); diasData = [];
  renderCal();
  await refreshPicoDependentViews();
  loadArticulosCount();
  if (drawerOpen && selDay) await loadDayDetail(selDay);
}

function abrirReportePicos() {
  const mes    = mesPad();
  const suc    = getSuc();
  const umbral = document.getElementById('sliderUmbral')?.value || '1.20';
  const metrica= document.getElementById('selMetrica')?.value  || 'bultos';
  const url    = `/reporte-picos?sucursal=${encodeURIComponent(suc)}&mes=${mes}&umbral=${umbral}&metrica=${metrica}`;
  window.open(url, '_blank');
}

function exportDiasDetalle() {
  const hasta = mesPad();
  if (hasta < '2025-01') {
    alert('El exportador comienza en enero 2025. Seleccioná enero 2025 o un mes posterior.');
    return;
  }
  const params = new URLSearchParams({
    sucursal: getSuc(),
    desde: '2025-01',
    hasta,
    umbral: document.getElementById('sliderUmbral')?.value || '1.20',
    metrica: document.getElementById('selMetrica')?.value || 'bultos',
  });
  window.location.href = `${API}/api/picos/dias-detalle/export?${params.toString()}`;
}

// ── PLANILLA OPERATIVA ─────────────────────────────────────────────────────

function exportVentaDia(formato) {
  const params = ventaDiaQueryParams({ formato });
  const url = `${API}/api/picos/venta-dia/export?${params.toString()}`;
  if (formato === 'pdf') {
    window.open(url, '_blank');
    return;
  }
  window.location.href = url;
}

const MESES_PLANILLA = ['','Enero','Febrero','Marzo','Abril','Mayo','Junio',
  'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];

const SUC_LABELS = { '1': 'Casa Central', '2': 'Dolores' };

async function initPlanillaOperativa() {
  const selAnio = document.getElementById('planillaAnio');
  if (selAnio && selAnio.options.length === 0) {
    const now = new Date();
    for (let y = now.getFullYear(); y >= 2022; y--) {
      const o = document.createElement('option');
      o.value = y; o.textContent = y;
      selAnio.appendChild(o);
    }
  }
  // Default month to current
  const selMes = document.getElementById('planillaMes');
  if (selMes && !selMes.dataset.init) {
    selMes.value = new Date().getMonth() + 1;
    selMes.dataset.init = '1';
  }
  // Auto-select year/month with most recent data in DB
  try {
    const r = await fetch(`${API}/api/sync/operacion-camiones/anios?empresa_id=1`);
    const d = await r.json();
    if (d.anio_mas_reciente && selAnio) {
      selAnio.value = d.anio_mas_reciente;
      if (d.mes_mas_reciente && selMes) selMes.value = d.mes_mas_reciente;
    }
  } catch(_) {}
}

async function cargarPlanillaOperativa() {
  const anio = document.getElementById('planillaAnio')?.value;
  const mes  = document.getElementById('planillaMes')?.value;
  const cont = document.getElementById('planillaContenido');
  if (!anio || !mes) return;
  cont.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando?</div>';
  try {
    const resp = await fetch(`${API}/api/sync/operacion-camiones/mensual?empresa_id=1&sucursal_id=TODAS&anio=${anio}&mes=${mes}`);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);
    _renderPlanilla(data.filas || [], parseInt(anio), parseInt(mes));
  } catch(e) {
    cont.innerHTML = `<div style="color:var(--red);padding:16px">⚠ ${esc(e.message)}</div>`;
  }
}

async function syncDotacionConfig() {
  const btn    = document.getElementById('cfgBtnSyncDot');
  const msgEl  = document.getElementById('cfgSyncDotMsg');
  const detEl  = document.getElementById('cfgSyncDotDetalle');
  if (btn) btn.disabled = true;
  if (msgEl) { msgEl.textContent = 'Sincronizando…'; msgEl.style.color = 'var(--muted)'; }
  if (detEl) detEl.innerHTML = '';

  let secs = 0;
  const timer = setInterval(() => {
    secs++;
    if (msgEl) msgEl.textContent = `Sincronizando… ${secs}s`;
  }, 1000);

  const controller = new AbortController();
  const timeoutId  = setTimeout(() => controller.abort(), 90000);

  try {
    const data = await fetch(`${API}/api/sync/sheets-operativo`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ empresa_id: '1' }),
      signal: controller.signal,
    }).then(r => r.json());

    clearTimeout(timeoutId); clearInterval(timer);

    const n    = data.insertados ?? 0;
    const errs = data.errores   ?? [];
    const det  = data.detalle   ?? [];

    if (msgEl) {
      msgEl.textContent = errs.length
        ? `Completado con ${errs.length} error(es) - ${n} registros`
        : `Completado en ${secs}s - ${n} registros sincronizados`;
      msgEl.style.color = errs.length ? 'var(--acc)' : 'var(--grn)';
    }
    if (detEl) {
      detEl.innerHTML = det.map(d => d.error
        ? `<div style="color:var(--red)">? ${escHtml(d.url_tag)}: ${escHtml(d.error)}</div>`
        : `<div>✓ ${escHtml(d.url_tag)}: ${d.filas_csv} filas → ${d.filas_parseadas} parseadas → ${d.upsertados} insertadas</div>`
      ).join('');
    }
  } catch (e) {
    clearTimeout(timeoutId); clearInterval(timer);
    const msg = e.name === 'AbortError'
      ? '? Tiempo de espera agotado (90s). Intent? de nuevo.'
      : '? ' + (e.message || 'Error desconocido');
    if (btn) btn.disabled = false;
  }
}

async function syncYCargarPlanilla() {
  const btn   = document.getElementById('planillaBtnSync');
  const msgEl = document.getElementById('planillaSyncMsg');
  const cont  = document.getElementById('planillaContenido');
  if (btn) btn.disabled = true;
  if (cont) cont.innerHTML = '<div class="loading"><div class="spinner"></div>Importando datos desde Google Sheets…</div>';

  // Contador de segundos para que el usuario sepa que está procesando
  let secs = 0;
  const timer = setInterval(() => {
    secs++;
    if (msgEl) { msgEl.textContent = `Sincronizando… ${secs}s (las 4 hojas pueden tardar hasta 30s)`; msgEl.style.color = 'var(--muted)'; }
  }, 1000);

  const controller = new AbortController();
  const timeoutId  = setTimeout(() => controller.abort(), 90000); // 90s máximo

  try {
    const resp = await fetch(`${API}/api/sync/sheets-operativo`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ empresa_id: '1' }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    clearInterval(timer);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);

    // Mostrar detalle por tab
    const n    = data.insertados ?? 0;
    const errs = data.errores ?? [];
    const det  = data.detalle ?? [];
    let resumen = det.map(d => d.error
      ? `? ${esc(d.url_tag)}: ${esc(d.error)}`
      : `✓ Tab ${esc(d.url_tag)}: ${d.filas_csv} filas CSV → ${d.filas_parseadas} parseadas`
    ).join('<br>');
    const color = errs.length ? 'var(--acc)' : 'var(--grn)';
    if (msgEl) {
      msgEl.innerHTML = `<strong style="color:${color}">${n} registros procesados</strong><br><span style="color:var(--muted)">${resumen}</span>`;
    }

    // Auto-seleccionar año/mes más reciente de la DB
    try {
      const r2 = await fetch(`${API}/api/sync/operacion-camiones/anios?empresa_id=1`);
      const d2 = await r2.json();
      if (d2.anio_mas_reciente) {
        const sa = document.getElementById('planillaAnio');
        const sm = document.getElementById('planillaMes');
        if (sa) sa.value = d2.anio_mas_reciente;
        if (sm) sm.value = d2.mes_mas_reciente;
      }
    } catch(_) {}

    await cargarPlanillaOperativa();
    await refreshPicoDependentViews();
  } catch(e) {
    clearTimeout(timeoutId);
    clearInterval(timer);
    const msg = e.name === 'AbortError'
      ? '? Tiempo de espera agotado (90s). Intent? de nuevo.'
      : '? ' + (e.message || 'Error desconocido');
    if (msgEl) { msgEl.textContent = msg; msgEl.style.color = 'var(--red)'; }
    if (cont)  cont.innerHTML = '';
  } finally {
    if (btn) btn.disabled = false;
  }
}

function _renderPlanilla(filas, anio, mes) {
  const cont = document.getElementById('planillaContenido');
  if (!filas.length) {
    cont.innerHTML = `<div style="padding:30px;text-align:center;color:var(--muted);font-size:13px">
      Sin datos para <strong>${esc(MESES_PLANILLA[mes])} ${anio}</strong>.<br>
      <span style="font-size:11px">Si ya sincronizaste, verific? el a?o y mes - los datos en la planilla pueden ser de otro per?odo.<br>
      Tambi?n pod?s usar <strong>"↻ Sincronizar y cargar"</strong> para importar y auto-seleccionar el per?odo correcto.</span>
    </div>`;
    return;
  }

  // Group by sucursal_id
  const bySuc = {};
  for (const f of filas) {
    (bySuc[f.sucursal_id] = bySuc[f.sucursal_id] || []).push(f);
  }

  // Group each sucursal by date → {s1: {...}, s2: {...}}
  function groupByDate(rows) {
    const byDate = {};
    for (const r of rows) {
      if (!byDate[r.fecha]) byDate[r.fecha] = {};
      byDate[r.fecha][r.nro_salida] = r;
    }
    return byDate;
  }

  function buildTable(rows, sucLabel) {
    const byDate = groupByDate(rows);
    const dates  = Object.keys(byDate).sort();

    // Totals
    let totS1 = {camiones:0,choferes:0,ayudantes:0,personas:0};
    let totS2 = {camiones:0,choferes:0,ayudantes:0,personas:0};

    let tbody = '';
    for (const fecha of dates) {
      const s1 = byDate[fecha][1] || {};
      const s2 = byDate[fecha][2] || {};
      const totalCam  = (s1.camiones||0) + (s2.camiones||0);
      const totalPers = (s1.personas||0) + (s2.personas||0);
      totS1.camiones  += s1.camiones||0; totS1.choferes  += s1.choferes||0;
      totS1.ayudantes += s1.ayudantes||0; totS1.personas += s1.personas||0;
      totS2.camiones  += s2.camiones||0; totS2.choferes  += s2.choferes||0;
      totS2.ayudantes += s2.ayudantes||0; totS2.personas += s2.personas||0;

      const d = new Date(fecha + 'T00:00:00');
      const dLabel = d.toLocaleDateString('es-AR', {weekday:'short', day:'numeric'});

      tbody += `<tr>
        <td style="font-size:11px;white-space:nowrap">${esc(dLabel)}</td>
        <td style="text-align:center">${s1.camiones||'?'}</td>
        <td style="text-align:center">${s1.choferes||'?'}</td>
        <td style="text-align:center">${s1.ayudantes||'?'}</td>
        <td style="text-align:center;color:var(--muted)">${s1.personas||'?'}</td>
        <td style="text-align:center">${s2.camiones||'?'}</td>
        <td style="text-align:center">${s2.choferes||'?'}</td>
        <td style="text-align:center">${s2.ayudantes||'?'}</td>
        <td style="text-align:center;color:var(--muted)">${s2.personas||'?'}</td>
        <td style="text-align:center;font-weight:600;color:var(--acc)">${totalCam}</td>
        <td style="text-align:center;font-weight:600">${totalPers}</td>
      </tr>`;
    }

    const totTotalCam  = totS1.camiones + totS2.camiones;
    const totTotalPers = totS1.personas + totS2.personas;

    return `
      <div style="margin-bottom:18px">
        <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
                    color:var(--acc);margin-bottom:8px;padding:6px 0;border-bottom:2px solid var(--acc)">
          ${esc(sucLabel)} ? ${esc(MESES_PLANILLA[mes])} ${anio}
        </div>
        <div style="overflow-x:auto">
          <table class="rtbl" style="width:100%;font-size:12px">
            <thead>
              <tr>
                <th rowspan="2" style="min-width:90px">Fecha</th>
                <th colspan="4" style="text-align:center;background:rgba(var(--blu-rgb,26,95,163),.08)">1? Salida</th>
                <th colspan="4" style="text-align:center;background:rgba(var(--grn-rgb,12,110,66),.08)">2? Salida</th>
                <th colspan="2" style="text-align:center;background:rgba(var(--acc-rgb,154,95,5),.08)">Total d?a</th>
              </tr>
              <tr>
                <th style="text-align:center;background:rgba(var(--blu-rgb,26,95,163),.05)">Cam.</th>
                <th style="text-align:center;background:rgba(var(--blu-rgb,26,95,163),.05)">Chor.</th>
                <th style="text-align:center;background:rgba(var(--blu-rgb,26,95,163),.05)">Ayd.</th>
                <th style="text-align:center;background:rgba(var(--blu-rgb,26,95,163),.05);color:var(--muted)">Pers.</th>
                <th style="text-align:center;background:rgba(var(--grn-rgb,12,110,66),.05)">Cam.</th>
                <th style="text-align:center;background:rgba(var(--grn-rgb,12,110,66),.05)">Chor.</th>
                <th style="text-align:center;background:rgba(var(--grn-rgb,12,110,66),.05)">Ayd.</th>
                <th style="text-align:center;background:rgba(var(--grn-rgb,12,110,66),.05);color:var(--muted)">Pers.</th>
                <th style="text-align:center">Cam.</th>
                <th style="text-align:center">Pers.</th>
              </tr>
            </thead>
            <tbody>
              ${tbody}
            </tbody>
            <tfoot>
              <tr style="font-weight:700;border-top:2px solid var(--brd)">
                <td>TOTAL</td>
                <td style="text-align:center">${totS1.camiones}</td>
                <td style="text-align:center">${totS1.choferes}</td>
                <td style="text-align:center">${totS1.ayudantes}</td>
                <td style="text-align:center;color:var(--muted)">${totS1.personas}</td>
                <td style="text-align:center">${totS2.camiones}</td>
                <td style="text-align:center">${totS2.choferes}</td>
                <td style="text-align:center">${totS2.ayudantes}</td>
                <td style="text-align:center;color:var(--muted)">${totS2.personas}</td>
                <td style="text-align:center;color:var(--acc)">${totTotalCam}</td>
                <td style="text-align:center">${totTotalPers}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>`;
  }

  let html = '';
  const sucIds = Object.keys(bySuc).sort();
  for (const sid of sucIds) {
    html += buildTable(bySuc[sid], SUC_LABELS[sid] || ('Sucursal ' + sid));
  }
  cont.innerHTML = html;
}

// ─── PERÍODOS CRÍTICOS ────────────────────────────────────────
let _pcAbort = null;

async function loadPeriodosCriticos() {
  const cont = document.getElementById('periodosCriticos');
  if (!cont) return;
  if (_pcAbort) _pcAbort.abort();
  _pcAbort = new AbortController();
  cont.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  const anio = vY;
  const suc  = getSuc();
  try {
    const data = await api(
      `/api/picos/periodos-criticos?sucursal_id=${suc}&anio=${anio}`,
      { signal: _pcAbort.signal }
    );
    renderPeriodosCriticos(data, anio, suc);
  } catch (e) {
    if (e.name === 'AbortError') return;
    cont.innerHTML = `<div style="color:var(--red);font-size:12px">Error al cargar periodos: ${e.message}</div>`;
  }
}

function _renderAusLineChart(ausMensual, ausMensualAnt, anio) {
  const W = 520, H = 155, PL = 30, PR = 10, PT = 28, PB = 22;
  const CW = W - PL - PR, CH = H - PT - PB;
  const allPcts = [
    ...ausMensual.map(m => m.pct_ausentismo || 0),
    ...ausMensualAnt.map(m => m.pct_ausentismo || 0),
  ];
  const maxPct = Math.max(...allPcts, 12);
  const xOf = i => PL + (i / 11) * CW;
  const yOf = p => PT + CH - (p / maxPct * CH);
  const ABREV = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
  const fmtP = p => Number.isInteger(p) ? `${p}%` : `${p.toFixed(1)}%`;

  let svg = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:155px;overflow:visible;display:block">`;

  // Eje X base
  svg += `<line x1="${PL}" y1="${PT+CH}" x2="${W-PR}" y2="${PT+CH}" stroke="rgba(255,255,255,.1)" stroke-width="1"/>`;

  // Líneas guía horizontales con etiqueta
  [5, 10, 15, 20].filter(p => p <= maxPct + 2).forEach(p => {
    const y = yOf(p);
    svg += `<line x1="${PL}" y1="${y}" x2="${W-PR}" y2="${y}" stroke="rgba(255,255,255,.07)" stroke-width="1" stroke-dasharray="3,4"/>`;
    svg += `<text x="${PL-4}" y="${y+3}" font-size="8" fill="rgba(255,255,255,.28)" text-anchor="end">${p}%</text>`;
  });

  // Etiquetas de meses en el eje X
  ABREV.forEach((a, i) => {
    svg += `<text x="${xOf(i)}" y="${H-3}" font-size="8.5" fill="rgba(255,255,255,.45)" text-anchor="middle">${a}</text>`;
  });

  // ── Serie a?o anterior (punteada gris) ─────────────────────
  const ptAnt = ausMensualAnt.filter(m => m.pct_ausentismo != null)
    .map(m => `${xOf(m.mes-1).toFixed(1)},${yOf(m.pct_ausentismo).toFixed(1)}`).join(' ');
  if (ptAnt) {
    svg += `<polyline points="${ptAnt}" fill="none" stroke="rgba(255,255,255,.22)" stroke-width="1.5" stroke-dasharray="4,3"/>`;
    ausMensualAnt.filter(m => m.pct_ausentismo != null).forEach(m => {
      const cx = xOf(m.mes-1), cy = yOf(m.pct_ausentismo);
      const p = m.pct_ausentismo;
      // Etiqueta debajo del punto (a?o anterior)
      const ly = cy + 14;
      svg += `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="2.5" fill="rgba(255,255,255,.3)"/>`;
      svg += `<text x="${cx.toFixed(1)}" y="${ly.toFixed(1)}" font-size="7.5" fill="rgba(255,255,255,.38)" text-anchor="middle">${fmtP(p)}</text>`;
    });
  }

  // ── Serie a?o actual (s?lida, coloreada por umbral) ────────
  const ptAct = ausMensual.filter(m => m.pct_ausentismo != null)
    .map(m => `${xOf(m.mes-1).toFixed(1)},${yOf(m.pct_ausentismo).toFixed(1)}`).join(' ');
  if (ptAct) {
    svg += `<polyline points="${ptAct}" fill="none" stroke="var(--acc)" stroke-width="2"/>`;
    ausMensual.filter(m => m.pct_ausentismo != null).forEach(m => {
      const p = m.pct_ausentismo;
      const cx = xOf(m.mes-1), cy = yOf(p);
      const col = p >= 10 ? 'var(--red)' : p >= 5 ? 'var(--acc)' : 'var(--grn)';
      // Etiqueta encima del punto; si est? cerca del tope la pone debajo
      const ly = cy <= PT + 14 ? cy + 14 : cy - 7;
      svg += `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="3.5" fill="${col}" stroke="var(--bg)" stroke-width="1.5"/>`;
      svg += `<text x="${cx.toFixed(1)}" y="${ly.toFixed(1)}" font-size="9" fill="${col}" text-anchor="middle" font-weight="600">${fmtP(p)}</text>`;
    });
  }

  svg += '</svg>';

  const tieneAnt = ausMensualAnt.some(m => m.pct_ausentismo != null);
  const leyenda = `<div style="display:flex;gap:14px;margin-top:4px;font-size:10px;color:var(--muted);flex-wrap:wrap;align-items:center">
    <span><span style="color:var(--grn)">●</span> &lt;5% normal</span>
    <span><span style="color:var(--acc)">●</span> 5-10% medio</span>
    <span><span style="color:var(--red)">●</span> ≥10% alto</span>
    ${tieneAnt ? `<span style="margin-left:6px;display:inline-flex;align-items:center;gap:5px">
      <svg width="18" height="10"><line x1="0" y1="5" x2="18" y2="5" stroke="rgba(255,255,255,.3)" stroke-width="1.5" stroke-dasharray="4,3"/></svg>${anio - 1}
      &nbsp;
      <svg width="18" height="10"><line x1="0" y1="5" x2="18" y2="5" stroke="var(--acc)" stroke-width="2"/></svg>${anio}
    </span>` : ''}
  </div>`;

  return `<div style="margin-bottom:16px">
    <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">Ausentismo histórico mensual</div>
    ${svg}${leyenda}
  </div>`;
}

function renderPeriodosCriticos(data, anio, suc) {
  const cont = document.getElementById('periodosCriticos');
  if (!cont) return;
  const periodos      = data.periodos  || [];
  const sugeridos     = data.sugeridos || [];
  const ausMensual    = data.ausentismo_mensual          || [];
  const ausMensualAnt = data.ausentismo_mensual_anterior || [];
  const cumple        = data.cumple_minimo;

  // ── Gr?fico de l?nea ausentismo ──────────────────────────
  const ausHtml = (ausMensual.length || ausMensualAnt.length)
    ? _renderAusLineChart(ausMensual, ausMensualAnt, anio)
    : '';

  let html = ausHtml + `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px">
    <div style="display:flex;align-items:center;gap:8px">
      <span style="font-size:13px;font-weight:600">Períodos críticos ${anio}</span>
      <span style="font-family:var(--mono);font-size:11px;padding:2px 8px;border-radius:12px;${cumple ? 'background:rgba(76,175,130,.2);color:var(--grn)' : 'background:rgba(224,92,92,.2);color:var(--red)'}">${periodos.length} definido${periodos.length !== 1 ? 's' : ''} ${cumple ? '✓' : '— mínimo 3'}</span>
    </div>
    <button class="btn primary" style="font-size:11px;padding:5px 12px" onclick="abrirFormPeriodo()">+ Agregar período</button>
  </div>`;

  if (periodos.length > 0) {
    html += `<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:14px">`;
    periodos.forEach(p => {
      const dur = p.fecha_fin === p.fecha_inicio ? '1 día' : `${calcDuracion(p.fecha_inicio, p.fecha_fin)} días`;
      html += `<div style="background:var(--surf2);border:1px solid var(--brd);border-left:3px solid var(--acc);border-radius:5px;padding:8px 12px;display:flex;justify-content:space-between;align-items:center;gap:8px">
        <div>
          <span style="font-weight:600;font-size:12px">${escHtml(p.nombre)}</span>
          <span style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-left:8px">${p.fecha_inicio} → ${p.fecha_fin} (${dur})</span>
          ${p.motivo ? `<div style="font-size:11px;color:var(--muted);margin-top:2px">${escHtml(p.motivo)}</div>` : ''}
        </div>
        <button onclick="eliminarPeriodoCritico(${p.id})" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:16px;padding:0 4px" title="Eliminar">×</button>
      </div>`;
    });
    html += `</div>`;
  } else {
    html += `<div style="color:var(--muted);font-size:12px;margin-bottom:14px">Sin períodos definidos para ${anio}.</div>`;
  }

  if (sugeridos.length > 0) {
    html += `<div class="sec" style="margin-bottom:10px">Sugerencias basadas en análisis histórico</div>
    <div style="display:flex;flex-direction:column;gap:5px">`;
    sugeridos.slice(0, 6).forEach(s => {
      const dur = s.duracion_dias === 1 ? '1 día' : `${s.duracion_dias} días`;
      const ndsColor = s.nds_promedio < 85 ? 'var(--red)' : s.nds_promedio < 95 ? 'var(--acc)' : 'var(--grn)';
      html += `<div style="background:var(--surf2);border:1px solid var(--brd);border-radius:5px;padding:7px 12px;display:flex;justify-content:space-between;align-items:center;gap:8px;opacity:.85">
        <div style="flex:1">
          <span style="font-size:11px;font-weight:600">${escHtml(s.nombre_sugerido)}</span>
          <span style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-left:8px">${s.fecha_inicio} → ${s.fecha_fin} (${dur})</span>
          <span style="font-size:10px;color:var(--muted);margin-left:6px">· NDS ${s.nds_promedio}%</span>
          ${s.pct_ausentismo_historico > 0 ? `<span style="font-size:10px;color:${s.pct_ausentismo_historico >= 10 ? 'var(--red)' : 'var(--acc)'};margin-left:6px">· Aus. ${s.pct_ausentismo_historico}%</span>` : ''}
          <div style="font-size:10px;color:var(--muted);margin-top:1px">${escHtml(s.motivo_sugerido)}</div>
        </div>
        <button onclick="usarSugerencia(${JSON.stringify(s).split('"').join('&quot;')})" style="font-size:10px;padding:3px 8px;background:var(--surf3);border:1px solid var(--brd);border-radius:4px;color:var(--txt);cursor:pointer">Usar</button>
      </div>`;
    });
    html += `</div>`;
  }

  html += `<div id="formPeriodo" style="display:none;margin-top:14px;background:var(--surf2);border:1px solid var(--brd);border-radius:6px;padding:14px">
    <div style="font-size:12px;font-weight:600;margin-bottom:10px">Nuevo período crítico</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
      <div><label style="font-size:10px;color:var(--muted)">Nombre</label>
        <input id="pcNombre" type="text" placeholder="Ej: Semana Santa" style="width:100%;margin-top:3px"></div>
      <div><label style="font-size:10px;color:var(--muted)">Motivo</label>
        <input id="pcMotivo" type="text" placeholder="Ej: alto volumen + ausentismo" style="width:100%;margin-top:3px"></div>
      <div><label style="font-size:10px;color:var(--muted)">Fecha inicio</label>
        <input id="pcFechaIni" type="date" style="width:100%;margin-top:3px"></div>
      <div><label style="font-size:10px;color:var(--muted)">Fecha fin (máx +6 días)</label>
        <input id="pcFechaFin" type="date" style="width:100%;margin-top:3px"></div>
    </div>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="btn" onclick="cerrarFormPeriodo()">Cancelar</button>
      <button class="btn primary" onclick="guardarPeriodoCritico()">Guardar</button>
    </div>
    <div id="pcError" style="color:var(--red);font-size:11px;margin-top:6px;min-height:16px"></div>
  </div>`;

  cont.innerHTML = html;
}

function calcDuracion(fi, ff) {
  const a = new Date(fi), b = new Date(ff);
  return Math.round((b - a) / 86400000) + 1;
}

function escHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function abrirFormPeriodo() {
  const f = document.getElementById('formPeriodo');
  if (f) { f.style.display = 'block'; document.getElementById('pcNombre')?.focus(); }
}

function cerrarFormPeriodo() {
  const f = document.getElementById('formPeriodo');
  if (f) f.style.display = 'none';
}

function usarSugerencia(s) {
  abrirFormPeriodo();
  const n = document.getElementById('pcNombre');
  const m = document.getElementById('pcMotivo');
  const fi = document.getElementById('pcFechaIni');
  const ff = document.getElementById('pcFechaFin');
  if (n) n.value = s.nombre_sugerido || '';
  if (m) m.value = s.motivo_sugerido || '';
  if (fi) fi.value = s.fecha_inicio || '';
  if (ff) ff.value = s.fecha_fin || '';
}

async function guardarPeriodoCritico() {
  const nombre = document.getElementById('pcNombre')?.value?.trim();
  const motivo = document.getElementById('pcMotivo')?.value?.trim();
  const fi = document.getElementById('pcFechaIni')?.value;
  const ff = document.getElementById('pcFechaFin')?.value;
  const errEl = document.getElementById('pcError');

  if (!nombre) { if (errEl) errEl.textContent = 'Nombre requerido'; return; }
  if (!fi)     { if (errEl) errEl.textContent = 'Fecha inicio requerida'; return; }
  if (errEl) errEl.textContent = '';

  try {
    await api('/api/picos/periodos-criticos', {
      method: 'POST',
      body: JSON.stringify({
        nombre, motivo: motivo || null,
        fecha_inicio: fi, fecha_fin: ff || fi,
        anio: vY, sucursal_id: getSuc(),
      }),
    });
    await loadPeriodosCriticos();
    await refreshPicoDependentViews();
  } catch (e) {
    if (errEl) errEl.textContent = e.message || 'Error al guardar';
  }
}

async function eliminarPeriodoCritico(id) {
  if (!confirm('¿Eliminar este período crítico?')) return;
  try {
    await fetch(API + `/api/picos/periodos-criticos/${id}`, { method: 'DELETE' });
    await loadPeriodosCriticos();
    await refreshPicoDependentViews();
  } catch (e) {
    alert('Error al eliminar: ' + e.message);
  }
}

// ─── VENTA VS AÑO ANTERIOR ────────────────────────────────────
function ventaAnualMetricFormat(metric, value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  if (metric === 'pallets') return n.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (metric === 'bultos' || metric === 'pedidos' || metric === 'clientes') return fmtN(Math.round(n));
  return n.toLocaleString('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function syncVentaAnualFilters(data) {
  fillSelectPreserving('ventaAnualDivision', data?.opciones?.divisiones || [], '', 'Todas las divisiones');
  fillSelectPreserving('ventaAnualUnidadNegocio', data?.opciones?.unidades_negocio || [], '', 'Todas las unidades de negocio');
}

function renderVentaAnualChart(data) {
  if (!window.Chart) return ventaAnualChart;
  const el = document.getElementById('ventaAnualChart');
  if (!el) return ventaAnualChart;
  if (ventaAnualChart) ventaAnualChart.destroy();

  const metric = data?.metrica || document.getElementById('selMetrica')?.value || 'bultos';
  const labels = (data?.meses || []).map(m => m.nombre || '');
  const base = (data?.meses || []).map(m => Number(m.base ?? 0));
  const actual = (data?.meses || []).map(m => Number(m.actual ?? 0));
  const maxVal = Math.max(5, ...base.filter(v => v != null), ...actual.filter(v => v != null));

  ventaAnualChart = new Chart(el.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: `Base ${data?.anio_base ?? ''}`,
        data: base,
        borderColor: '#5b8dee',
        backgroundColor: 'rgba(91,141,238,.15)',
        pointBackgroundColor: '#5b8dee',
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
        tension: .25,
        spanGaps: true,
        labelColor: '#8fb3ff',
        valueFormatter: raw => ventaAnualMetricFormat(metric, raw),
      }, {
        label: `Actual ${data?.anio ?? ''}`,
        data: actual,
        borderColor: '#f5a623',
        backgroundColor: 'rgba(245,166,35,.16)',
        pointBackgroundColor: '#f5a623',
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
        tension: .25,
        spanGaps: true,
        labelColor: '#f5a623',
        valueFormatter: raw => ventaAnualMetricFormat(metric, raw),
      }],
    },
    plugins: [chartValueLabels],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 20 } },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#e8eaf0', boxWidth: 10 } },
        chartValueLabels: { hideZero: true, maxLabelsPerDataset: 6 },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ventaAnualMetricFormat(metric, ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: { ticks: { color: '#6b7080' }, grid: { color: 'rgba(42,46,58,.35)' } },
        y: {
          beginAtZero: true,
          suggestedMax: maxVal + 1,
          ticks: { color: '#6b7080', callback: value => ventaAnualMetricFormat(metric, value) },
          grid: { color: 'rgba(42,46,58,.35)' },
        },
      },
    },
  });

  return ventaAnualChart;
}

function renderVentaAnual(data) {
  const meta = document.getElementById('ventaAnualMeta');
  const cont = document.getElementById('ventaAnualTabla');
  const kpis = document.getElementById('ventaAnualKpis');
  if (!cont || !kpis) return;

  const metric = data?.metrica || document.getElementById('selMetrica')?.value || 'bultos';
  const metricLabel = data?.metrica_label || metricSummaryLabel(metric);
  const sucLabel = data?.filtros?.sucursal_label || selectedOptionText('selSucursal', getSuc());
  const divLabel = data?.filtros?.division_label || selectedOptionText('ventaAnualDivision', 'Todas las divisiones');
  const uniLabel = data?.filtros?.unidad_negocio_label || selectedOptionText('ventaAnualUnidadNegocio', 'Todas las unidades de negocio');
  if (meta) {
    meta.textContent = `Sucursal: ${sucLabel} | Métrica: ${metricLabel} | División: ${divLabel} | Unidad: ${uniLabel}`;
  }

  const resumen = data?.resumen || {};
  const actual = Number(resumen.actual || 0);
  const base = Number(resumen.base || 0);
  const delta = Number(resumen.delta || (actual - base));
  const deltaPct = resumen.delta_pct;
  const deltaClass = delta > 0 ? 'grn' : delta < 0 ? 'red' : 'muted';
  const deltaPctClass = deltaPct == null ? 'muted' : deltaPct > 0 ? 'grn' : deltaPct < 0 ? 'red' : 'muted';

  kpis.innerHTML = `
    <div class="kpi blu"><div class="kpi-lbl">Año actual</div><div class="kpi-val blu">${ventaAnualMetricFormat(metric, actual)}</div></div>
    <div class="kpi ora"><div class="kpi-lbl">Año base</div><div class="kpi-val ora">${ventaAnualMetricFormat(metric, base)}</div></div>
    <div class="kpi ${deltaClass}"><div class="kpi-lbl">Variación</div><div class="kpi-val ${deltaClass}">${ventaAnualMetricFormat(metric, delta)}</div><div style="font-size:10px;color:var(--muted);margin-top:4px">${deltaPct == null ? '—' : fmtPct1(deltaPct)}</div></div>
  `;

  const rows = Array.isArray(data?.meses) ? data.meses : [];
  let html = `<table class="rtbl"><thead><tr>
    <th>Mes</th>
    <th>${data?.anio_base ?? ''}</th>
    <th>${data?.anio ?? ''}</th>
    <th>Variación</th>
    <th>Variación %</th>
  </tr></thead><tbody>`;
  rows.forEach(row => {
    const rowDelta = Number(row.delta ?? 0);
    const rowPct = row.delta_pct;
    const rowDeltaClass = rowDelta > 0 ? 'var(--grn)' : rowDelta < 0 ? 'var(--red)' : 'var(--muted)';
    const rowPctClass = rowPct == null ? 'var(--muted)' : rowPct > 0 ? 'var(--grn)' : rowPct < 0 ? 'var(--red)' : 'var(--muted)';
    html += `<tr>
      <td>${esc(row.nombre || '')}</td>
      <td style="font-family:var(--mono)">${ventaAnualMetricFormat(metric, row.base)}</td>
      <td style="font-family:var(--mono)">${ventaAnualMetricFormat(metric, row.actual)}</td>
      <td style="font-family:var(--mono);color:${rowDeltaClass}">${ventaAnualMetricFormat(metric, rowDelta)}</td>
      <td style="font-family:var(--mono);color:${rowPctClass}">${rowPct == null ? '—' : fmtPct1(rowPct)}</td>
    </tr>`;
  });
  html += `</tbody><tfoot><tr>
    <td>Total</td>
    <td>${ventaAnualMetricFormat(metric, base)}</td>
    <td>${ventaAnualMetricFormat(metric, actual)}</td>
    <td style="color:${deltaClass === 'grn' ? 'var(--grn)' : deltaClass === 'red' ? 'var(--red)' : 'var(--muted)'}">${ventaAnualMetricFormat(metric, delta)}</td>
    <td style="color:${deltaPctClass === 'grn' ? 'var(--grn)' : deltaPctClass === 'red' ? 'var(--red)' : 'var(--muted)'}">${deltaPct == null ? '—' : fmtPct1(deltaPct)}</td>
  </tr></tfoot></table>`;
  cont.innerHTML = html;

  renderVentaAnualChart(data);
}

async function loadVentaAnual() {
  const seq = ++_loadVentaAnualSeq;
  if (_ventaAnualAbort) _ventaAnualAbort.abort();
  _ventaAnualAbort = new AbortController();

  const cont = document.getElementById('ventaAnualTabla');
  const kpis = document.getElementById('ventaAnualKpis');
  if (!cont || !kpis) return;
  cont.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  kpis.innerHTML = '<div class="loading"><div class="spinner"></div>Cargandoâ€¦</div>';

  const hoy = new Date();
  const anioEl = document.getElementById('ventaAnualAnio');
  const baseEl = document.getElementById('ventaAnualAnioBase');
  if (anioEl && !anioEl.value) anioEl.value = hoy.getFullYear();
  if (baseEl && !baseEl.value) baseEl.value = hoy.getFullYear() - 1;

  const suc = getSuc();
  const anio = parseInt(anioEl?.value || hoy.getFullYear(), 10);
  const anioBase = parseInt(baseEl?.value || hoy.getFullYear() - 1, 10);
  const division = document.getElementById('ventaAnualDivision')?.value || '';
  const unidadNegocio = document.getElementById('ventaAnualUnidadNegocio')?.value || '';
  const metric = document.getElementById('selMetrica')?.value || 'bultos';

  try {
    const qs = new URLSearchParams({ sucursal: suc, anio, anio_base: anioBase, metrica: metric });
    if (division) qs.set('division', division);
    if (unidadNegocio) qs.set('unidad_negocio', unidadNegocio);
    const data = await api(`/api/picos/venta-anual?${qs.toString()}`, { signal: _ventaAnualAbort.signal, timeout: 90000 });
    if (
      seq !== _loadVentaAnualSeq ||
      suc !== getSuc() ||
      anio !== parseInt(document.getElementById('ventaAnualAnio')?.value || anio, 10) ||
      anioBase !== parseInt(document.getElementById('ventaAnualAnioBase')?.value || anioBase, 10) ||
      metric !== document.getElementById('selMetrica')?.value
    ) return;
    syncVentaAnualFilters(data);
    renderVentaAnual(data);
  } catch (e) {
    if (e.name === 'AbortError') return;
    cont.innerHTML = `<div style="color:var(--red);font-size:12px">Error: ${e.message}</div>`;
    kpis.innerHTML = `<div style="color:var(--red);font-size:12px">Error: ${e.message}</div>`;
  }
}

// â”€â”€â”€ COMPARATIVO ANUAL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function initVentaAnualDefaults() {
  const periodo = document.getElementById('ventaAnualPeriodo');
  if (periodo && !periodo.dataset.init) {
    periodo.value = 'anio';
    periodo.dataset.init = '1';
  }

  const hoy = new Date();
  const anioEl = document.getElementById('ventaAnualAnio');
  const baseEl = document.getElementById('ventaAnualAnioBase');
  const mesEl = document.getElementById('ventaAnualMes');
  const desdeEl = document.getElementById('ventaAnualDesde');
  const hastaEl = document.getElementById('ventaAnualHasta');

  if (anioEl && !anioEl.value) anioEl.value = hoy.getFullYear();
  if (baseEl && !baseEl.value) baseEl.value = hoy.getFullYear() - 1;
  if (mesEl && !mesEl.value) mesEl.value = mesPad();
  if (desdeEl && !desdeEl.value) desdeEl.value = `${hoy.getFullYear()}-01`;
  if (hastaEl && !hastaEl.value) hastaEl.value = mesPad();

  syncVentaAnualPeriodoUI();
}

function syncVentaAnualMonthFilter() {
  const mesEl = document.getElementById('ventaAnualMes');
  if (!mesEl) return '';
  if (!/^\d{4}-\d{2}$/.test(mesEl.value || '')) mesEl.value = mesPad();
  return mesEl.value;
}

function syncVentaAnualRangeFilters() {
  const hoy = new Date();
  const desdeEl = document.getElementById('ventaAnualDesde');
  const hastaEl = document.getElementById('ventaAnualHasta');

  if (desdeEl && !/^\d{4}-\d{2}$/.test(desdeEl.value || '')) desdeEl.value = `${hoy.getFullYear()}-01`;
  if (hastaEl && !/^\d{4}-\d{2}$/.test(hastaEl.value || '')) hastaEl.value = mesPad();
  if (desdeEl && hastaEl && desdeEl.value > hastaEl.value) {
    const tmp = desdeEl.value;
    desdeEl.value = hastaEl.value;
    hastaEl.value = tmp;
  }

  return { desde: desdeEl?.value || '', hasta: hastaEl?.value || '' };
}

function syncVentaAnualPeriodoUI() {
  const tipo = document.getElementById('ventaAnualPeriodo')?.value || 'anio';
  const anioEl = document.getElementById('ventaAnualAnio');
  const baseEl = document.getElementById('ventaAnualAnioBase');
  const fieldIds = ['ventaAnualAnioField', 'ventaAnualAnioBaseField', 'ventaAnualMesField', 'ventaAnualDesdeField', 'ventaAnualHastaField'];
  fieldIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });

  const hoy = new Date();
  if (tipo === 'mes') {
    const mes = syncVentaAnualMonthFilter();
    const [anioMes] = mes.split('-');
    const year = Number(anioMes) || hoy.getFullYear();
    if (anioEl) anioEl.value = String(year);
    if (baseEl) baseEl.value = String(year - 1);
    const el = document.getElementById('ventaAnualMesField');
    if (el) el.style.display = '';
  } else if (tipo === 'rango') {
    const { desde, hasta } = syncVentaAnualRangeFilters();
    const year = Number((desde || '').slice(0, 4)) || hoy.getFullYear();
    if (anioEl) anioEl.value = String(year);
    if (baseEl) baseEl.value = String(year - 1);
    const desdeField = document.getElementById('ventaAnualDesdeField');
    const hastaField = document.getElementById('ventaAnualHastaField');
    if (desdeField) desdeField.style.display = '';
    if (hastaField) hastaField.style.display = '';
  } else {
    const year = Number(anioEl?.value || hoy.getFullYear()) || hoy.getFullYear();
    if (anioEl && !anioEl.value) anioEl.value = String(year);
    if (baseEl) baseEl.value = String(year - 1);
    const anioField = document.getElementById('ventaAnualAnioField');
    const baseField = document.getElementById('ventaAnualAnioBaseField');
    if (anioField) anioField.style.display = '';
    if (baseField) baseField.style.display = '';
  }
}

function reloadVentaAnualIfVisible() {
  if (!isTabVisible('tab-venta-anual')) return;
  loadVentaAnual();
}

async function onVentaAnualSucursalChange() {
  const sel = document.getElementById('ventaAnualSucursal');
  const globalSel = document.getElementById('selSucursal');
  if (!sel || !globalSel) return;
  globalSel.value = sel.value;
  await onSucursalChange();
}

function onVentaAnualPeriodoChange() {
  syncVentaAnualPeriodoUI();
  reloadVentaAnualIfVisible();
}

function syncVentaAnualFilters(data) {
  fillSelectPreserving('ventaAnualDivision', data?.opciones?.divisiones || [], '', 'Todas las divisiones');
  fillSelectPreserving('ventaAnualUnidadNegocio', data?.opciones?.unidades_negocio || [], '', 'Todas las unidades de negocio');
}

function ventaAnualQueryParams(extra = {}) {
  syncVentaAnualPeriodoUI();
  const params = new URLSearchParams();
  const sucursal = document.getElementById('ventaAnualSucursal')?.value || getSuc();
  const metric = document.getElementById('selMetrica')?.value || 'bultos';
  const periodo = document.getElementById('ventaAnualPeriodo')?.value || 'anio';
  const division = document.getElementById('ventaAnualDivision')?.value || '';
  const unidadNegocio = document.getElementById('ventaAnualUnidadNegocio')?.value || '';

  params.set('sucursal', sucursal);
  params.set('metrica', metric);
  params.set('periodo_tipo', periodo);

  if (periodo === 'mes') {
    const mes = syncVentaAnualMonthFilter();
    const [anioMes] = mes.split('-');
    const year = Number(anioMes) || new Date().getFullYear();
    params.set('anio', String(year));
    params.set('anio_base', String(year - 1));
    params.set('mes', mes);
  } else if (periodo === 'rango') {
    const { desde, hasta } = syncVentaAnualRangeFilters();
    const year = Number((desde || '').slice(0, 4)) || new Date().getFullYear();
    params.set('anio', String(year));
    params.set('anio_base', String(year - 1));
    if (desde) params.set('desde', desde);
    if (hasta) params.set('hasta', hasta);
  } else {
    const anio = parseInt(document.getElementById('ventaAnualAnio')?.value || new Date().getFullYear(), 10);
    const anioBase = parseInt(document.getElementById('ventaAnualAnioBase')?.value || anio - 1, 10);
    params.set('anio', String(Number.isFinite(anio) ? anio : new Date().getFullYear()));
    params.set('anio_base', String(Number.isFinite(anioBase) ? anioBase : (Number.isFinite(anio) ? anio - 1 : new Date().getFullYear() - 1)));
  }

  if (division) params.set('division', division);
  if (unidadNegocio) params.set('unidad_negocio', unidadNegocio);

  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });

  return params;
}

function renderVentaAnualChart(data) {
  if (!window.Chart) return ventaAnualChart;
  const el = document.getElementById('ventaAnualChart');
  if (!el) return ventaAnualChart;
  if (ventaAnualChart) ventaAnualChart.destroy();

  const metric = data?.metrica || document.getElementById('selMetrica')?.value || 'bultos';
  const puntos = Array.isArray(data?.puntos) ? data.puntos : Array.isArray(data?.meses) ? data.meses : [];
  const labels = (data?.labels || puntos.map(m => m.label || m.nombre || '')).map(v => v || '');
  const base = puntos.map(m => Number(m.base ?? 0));
  const actual = puntos.map(m => Number(m.actual ?? 0));
  const maxVal = Math.max(5, ...base.filter(v => v != null), ...actual.filter(v => v != null));

  ventaAnualChart = new Chart(el.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: data?.periodo_base_label || `Base ${data?.anio_base ?? ''}`,
        data: base,
        borderColor: '#5b8dee',
        backgroundColor: 'rgba(91,141,238,.15)',
        pointBackgroundColor: '#5b8dee',
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
        tension: .25,
        spanGaps: true,
        labelColor: '#8fb3ff',
        valueFormatter: raw => ventaAnualMetricFormat(metric, raw),
      }, {
        label: data?.periodo_label || `Actual ${data?.anio ?? ''}`,
        data: actual,
        borderColor: '#f5a623',
        backgroundColor: 'rgba(245,166,35,.16)',
        pointBackgroundColor: '#f5a623',
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
        tension: .25,
        spanGaps: true,
        labelColor: '#f5a623',
        valueFormatter: raw => ventaAnualMetricFormat(metric, raw),
      }],
    },
    plugins: [chartValueLabels],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 20 } },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#e8eaf0', boxWidth: 10 } },
        chartValueLabels: { hideZero: true, maxLabelsPerDataset: 6 },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ventaAnualMetricFormat(metric, ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: { ticks: { color: '#6b7080' }, grid: { color: 'rgba(42,46,58,.35)' } },
        y: {
          beginAtZero: true,
          suggestedMax: maxVal + 1,
          ticks: { color: '#6b7080', callback: value => ventaAnualMetricFormat(metric, value) },
          grid: { color: 'rgba(42,46,58,.35)' },
        },
      },
    },
  });

  return ventaAnualChart;
}

function renderVentaAnual(data) {
  const meta = document.getElementById('ventaAnualMeta');
  const cont = document.getElementById('ventaAnualTabla');
  const kpis = document.getElementById('ventaAnualKpis');
  if (!cont || !kpis) return;

  const metric = data?.metrica || document.getElementById('selMetrica')?.value || 'bultos';
  const metricLabel = data?.metrica_label || metricSummaryLabel(metric);
  const sucLabel = data?.filtros?.sucursal_label || selectedOptionText('ventaAnualSucursal', selectedOptionText('selSucursal', getSuc()));
  const divLabel = data?.filtros?.division_label || selectedOptionText('ventaAnualDivision', 'Todas las divisiones');
  const uniLabel = data?.filtros?.unidad_negocio_label || selectedOptionText('ventaAnualUnidadNegocio', 'Todas las unidades de negocio');
  const periodoLabel = data?.periodo_label || '-';
  const baseLabel = data?.periodo_base_label || '-';
  const periodoTipo = data?.periodo_tipo || document.getElementById('ventaAnualPeriodo')?.value || 'anio';
  const actualKpiLabel = periodoTipo === 'anio' ? 'Año actual' : periodoTipo === 'mes' ? 'Mes actual' : 'Período actual';
  const baseKpiLabel = periodoTipo === 'anio' ? 'Año base' : periodoTipo === 'mes' ? 'Mes base' : 'Período base';
  const periodColLabel = data?.granularidad === 'day' ? 'Día' : 'Período';

  if (meta) {
    meta.textContent = `Sucursal: ${sucLabel} | Métrica: ${metricLabel} | Período actual: ${periodoLabel} | Base: ${baseLabel} | División: ${divLabel} | Unidad: ${uniLabel}`;
  }

  const resumen = data?.resumen || {};
  const actual = Number(resumen.actual || 0);
  const base = Number(resumen.base || 0);
  const delta = Number(resumen.delta || (actual - base));
  const deltaPct = resumen.delta_pct;
  const deltaClass = delta > 0 ? 'grn' : delta < 0 ? 'red' : 'muted';
  const deltaPctClass = deltaPct == null ? 'muted' : deltaPct > 0 ? 'grn' : deltaPct < 0 ? 'red' : 'muted';

  kpis.innerHTML = `
    <div class="kpi blu"><div class="kpi-lbl">${actualKpiLabel}</div><div class="kpi-val blu">${ventaAnualMetricFormat(metric, actual)}</div></div>
    <div class="kpi ora"><div class="kpi-lbl">${baseKpiLabel}</div><div class="kpi-val ora">${ventaAnualMetricFormat(metric, base)}</div></div>
    <div class="kpi ${deltaClass}"><div class="kpi-lbl">Variación</div><div class="kpi-val ${deltaClass}">${ventaAnualMetricFormat(metric, delta)}</div><div style="font-size:10px;color:var(--muted);margin-top:4px">${deltaPct == null ? '—' : fmtPct1(deltaPct)}</div></div>
  `;

  const rows = Array.isArray(data?.puntos) ? data.puntos : Array.isArray(data?.meses) ? data.meses : [];
  let html = `<table class="rtbl"><thead><tr>
    <th>${periodColLabel}</th>
    <th>${esc(baseLabel)}</th>
    <th>${esc(periodoLabel)}</th>
    <th>Variación</th>
    <th>Variación %</th>
  </tr></thead><tbody>`;
  rows.forEach(row => {
    const rowDelta = Number(row.delta ?? 0);
    const rowPct = row.delta_pct;
    const rowDeltaClass = rowDelta > 0 ? 'var(--grn)' : rowDelta < 0 ? 'var(--red)' : 'var(--muted)';
    const rowPctClass = rowPct == null ? 'var(--muted)' : rowPct > 0 ? 'var(--grn)' : rowPct < 0 ? 'var(--red)' : 'var(--muted)';
    html += `<tr>
      <td>${esc(row.label || row.nombre || '')}</td>
      <td style="font-family:var(--mono)">${ventaAnualMetricFormat(metric, row.base)}</td>
      <td style="font-family:var(--mono)">${ventaAnualMetricFormat(metric, row.actual)}</td>
      <td style="font-family:var(--mono);color:${rowDeltaClass}">${ventaAnualMetricFormat(metric, rowDelta)}</td>
      <td style="font-family:var(--mono);color:${rowPctClass}">${rowPct == null ? '—' : fmtPct1(rowPct)}</td>
    </tr>`;
  });
  html += `</tbody><tfoot><tr>
    <td>Total</td>
    <td>${ventaAnualMetricFormat(metric, base)}</td>
    <td>${ventaAnualMetricFormat(metric, actual)}</td>
    <td style="color:${deltaClass === 'grn' ? 'var(--grn)' : deltaClass === 'red' ? 'var(--red)' : 'var(--muted)'}">${ventaAnualMetricFormat(metric, delta)}</td>
    <td style="color:${deltaPctClass === 'grn' ? 'var(--grn)' : deltaPctClass === 'red' ? 'var(--red)' : 'var(--muted)'}">${deltaPct == null ? '—' : fmtPct1(deltaPct)}</td>
  </tr></tfoot></table>`;
  cont.innerHTML = html;

  renderVentaAnualChart(data);
}

async function loadVentaAnual() {
  const seq = ++_loadVentaAnualSeq;
  if (_ventaAnualAbort) _ventaAnualAbort.abort();
  _ventaAnualAbort = new AbortController();
  if (ventaAnualChart) {
    ventaAnualChart.destroy();
    ventaAnualChart = null;
  }

  initVentaAnualDefaults();

  const cont = document.getElementById('ventaAnualTabla');
  const kpis = document.getElementById('ventaAnualKpis');
  if (!cont || !kpis) return;
  cont.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  kpis.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando…</div>';

  try {
    const params = ventaAnualQueryParams();
    const query = params.toString();
    const data = await api(`/api/picos/venta-anual?${query}`, { signal: _ventaAnualAbort.signal, timeout: 90000 });
    if (seq !== _loadVentaAnualSeq || query !== ventaAnualQueryParams().toString()) return;
    syncVentaAnualFilters(data);
    renderVentaAnual(data);
  } catch (e) {
    if (e.name === 'AbortError') return;
    cont.innerHTML = `<div style="color:var(--red);font-size:12px">Error: ${e.message}</div>`;
    kpis.innerHTML = `<div style="color:var(--red);font-size:12px">Error: ${e.message}</div>`;
  }
}

let _cmpAbort = null;
let _cmpSuc   = 'TODAS';
const CMP_SUC_LABELS = { 'TODAS': 'General — ambas sucursales', '1': 'Casa Central', '2': 'Dolores' };

function switchCmpSuc(suc, el) {
  _cmpSuc = suc;
  document.querySelectorAll('.plan-tabs .plan-tab').forEach(t => t.classList.remove('active'));
  if (el) el.classList.add('active');
  const lbl = document.getElementById('cmpSucLabel');
  if (lbl) lbl.textContent = CMP_SUC_LABELS[suc] || suc;
  loadComparativo();
}

function _initCmpSelectors() {
  const anioEl = document.getElementById('cmpAnio');
  const baseEl = document.getElementById('cmpAnioBase');
  if (anioEl && !anioEl.value) anioEl.value = vY;
  if (baseEl && !baseEl.value) baseEl.value = vY - 1;
}

async function loadComparativo() {
  _initCmpSelectors();
  const lbl = document.getElementById('cmpSucLabel');
  if (lbl) lbl.textContent = CMP_SUC_LABELS[_cmpSuc] || _cmpSuc;
  const cont = document.getElementById('tablaComparativo');
  if (!cont) return;
  if (_cmpAbort) _cmpAbort.abort();
  _cmpAbort = new AbortController();
  cont.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  const anio     = parseInt(document.getElementById('cmpAnio')?.value     || vY);
  const anioBase = parseInt(document.getElementById('cmpAnioBase')?.value || vY - 1);
  try {
    const data = await api(
      `/api/picos/comparativo-anual?sucursal=${_cmpSuc}&anio=${anio}&anio_base=${anioBase}`,
      { signal: _cmpAbort.signal, timeout: 90000 }
    );
    renderComparativo(data);
  } catch (e) {
    if (e.name === 'AbortError') return;
    cont.innerHTML = `<div style="color:var(--red);font-size:12px">Error: ${e.message}</div>`;
  }
}

function renderComparativo(data) {
  const cont = document.getElementById('tablaComparativo');
  if (!cont) return;
  const { anio, anio_base, meses } = data;

  const fHL  = v => v == null ? '?' : fmtN(Math.round(v));
  const fBlt = v => v == null ? '?' : fmtN(Math.round(v));
  const fInt = v => v == null ? '?' : String(Math.round(v));
  const fP1  = v => v == null ? '?' : v.toFixed(1)+'%';
  const fP2  = v => v == null ? '?' : v.toFixed(2)+'%';
  const fF1  = v => v == null ? '?' : v.toFixed(1);

  const pct  = (a,b) => (a==null||b==null||b===0)?null:Math.round((a-b)/b*1000)/10;
  const pp   = (a,b) => (a==null||b==null)?null:Math.round((a-b)*100)/100;
  const _avg = arr => arr.length ? arr.reduce((s,v)=>s+(v||0),0)/arr.length : null;
  const _sum = arr => arr.reduce((s,v)=>s+(v||0),0);

  const dCell = (v, inv=false) => {
    if (v==null) return '<td class="cmp-d eq">?</td>';
    const good = inv ? v<0 : v>0;
    const cls  = Math.abs(v)<0.5 ? 'eq' : good ? 'up' : 'dn';
    const icon = v>0.1 ? '▲' : v<-0.1 ? '▼' : '→';
    return '<td class="cmp-d '+cls+'">'+icon+Math.abs(v).toFixed(1)+'%</td>';
  };

  const sem = (m) => {
    const a=m.actual, b=m.base; let r=0;
    const nds=a?.nds??b?.nds;
    if (nds!=null) r += nds<90?2:nds<95?1:0;
    const rec=a?.pct_rec_hl ?? b?.pct_rec_hl ?? 0;
    r += rec>3?2:rec>1?1:0;
    const aus=b?.ausentismo;
    if (aus!=null) r += aus>=10?2:aus>=5?1:0;
    return r>=4 ? '<span class="sem crit" title="Riesgo alto"></span>'
         : r>=2 ? '<span class="sem warn" title="Riesgo moderado"></span>'
                : '<span class="sem ok" title="Sin riesgo"></span>';
  };

  const buildCard = (title, accent, defs) => {
    const sepRule = 'border-left:2px solid rgba(255,255,255,.32)';
    const styleAttr = (i, extra = '') => {
      const rules = [];
      if (i > 0) rules.push(sepRule);
      if (extra) rules.push(extra);
      return rules.length ? ' style="'+rules.join(';')+'"' : '';
    };
    let h1 = '<tr><th class="mes-sticky" rowspan="2">Mes</th>';
    let h2 = '<tr>';
    defs.forEach((d, i) => {
      const sp = d.deltaFn ? 3 : 2;
      h1 += '<th colspan="'+sp+'" class="sec-hdr" style="border-top:2px solid '+accent+(i > 0 ? ';'+sepRule : '')+'">'+d.label+'</th>';
      h2 += '<th class="yr"'+styleAttr(i, 'font-size:9px')+'>'+anio_base+'</th>'
          + '<th class="yr" style="font-size:9px;color:var(--acc)">'+anio+'</th>';
      if (d.deltaFn) h2 += '<th class="yr">Δ</th>';
    });
    h1 += '</tr>'; h2 += '</tr>';

    let body = '';
    meses.forEach(m => {
      const a=m.actual, b=m.base;
      const fcls = m.es_futuro ? ' class="futuro"' : '';
      const ftip = m.es_futuro ? ' title="🔮 Proyección de '+m.nombre+' '+anio_base+'"' : '';
      let tds = '<td class="mes-lbl">'+m.nombre+(m.es_futuro?' 🔮':' '+sem(m))+'</td>';
      defs.forEach((d, i) => {
        const vb=d.get(b), va=d.get(a);
        const fb = vb!=null ? d.fmt(vb) : '?';
        let fa;
        if (va!=null) {
          const col = d.color ? d.color(va) : 'inherit';
          fa = '<span style="color:'+col+'">'+d.fmt(va)+'</span>';
        } else if (m.es_futuro && vb!=null) {
          fa = '<span style="color:var(--muted);font-style:italic">'+fb+'</span>';
        } else {
          fa = '?';
        }
        const cbStyle = styleAttr(i, (vb!=null && d.color) ? 'color:'+d.color(vb) : '');
        tds += '<td'+cbStyle+'>'+fb+'</td><td>'+fa+'</td>';
        if (d.deltaFn) tds += dCell(va!=null&&vb!=null ? d.deltaFn(va,vb) : null, d.inv);
      });
      body += '<tr'+fcls+ftip+'>'+tds+'</tr>';
    });

    const mRealB = meses.filter(m=>!m.es_futuro&&m.base).map(m=>m.base);
    const mRealA = meses.filter(m=>!m.es_futuro&&m.actual).map(m=>m.actual);
    let stds = '<td class="mes-lbl" style="font-size:9px">TOTAL / PROM</td>';
    defs.forEach((d, i) => {
      const sb = d.sumFn ? d.sumFn(mRealB) : null;
      const sa = d.sumFn ? d.sumFn(mRealA) : null;
      stds += '<td'+styleAttr(i)+'>'+(sb!=null?d.fmt(sb):'?')+'</td>'
            + '<td style="color:var(--acc)">'+(sa!=null?d.fmt(sa):'?')+'</td>';
      if (d.deltaFn) stds += dCell(sb!=null&&sa!=null?d.deltaFn(sa,sb):null, d.inv);
    });
    body += '<tr class="summary">'+stds+'</tr>';

    return '<div class="cmp-card">'
      + '<div class="cmp-card-title">'
      + '<span style="display:inline-block;width:3px;height:14px;background:'+accent+';border-radius:2px;margin-right:6px"></span>'
      + title+'</div>'
      + '<div class="cmp-card-scroll">'
      + '<table class="cmp-tbl2"><thead>'+h1+h2+'</thead><tbody>'+body+'</tbody></table>'
      + '</div></div>';
  };

  const ndsColor = v => v<90?'var(--red)':v<95?'var(--acc)':'var(--grn)';
  const recColor = v => v>3?'var(--red)':v>1?'var(--acc)':'var(--grn)';
  const ausColor = v => v>=10?'var(--red)':v>=5?'var(--acc)':'inherit';

  const volCard = buildCard('📦 Volumen', 'var(--blu)', [
    {label:'HL',get:d=>d?.hl,fmt:fHL,deltaFn:pct,inv:false,
      sumFn:arr=>_sum(arr.map(d=>d?.hl||0))},
    {label:'Bultos',get:d=>d?.bultos,fmt:fBlt,deltaFn:pct,inv:false,
      sumFn:arr=>_sum(arr.map(d=>d?.bultos||0))},
    {label:'Pallets',get:d=>d?.pallets,fmt:fBlt,deltaFn:pct,inv:false,
      sumFn:arr=>_sum(arr.map(d=>d?.pallets||0))},
    {label:'PDV únicos',get:d=>d?.pdv_unicos,fmt:fInt,deltaFn:pct,inv:false,
      sumFn:arr=>{const v=arr.filter(d=>d?.pdv_unicos);return v.length?Math.round(_avg(v.map(d=>d.pdv_unicos))):null;}},
    {label:'Salidas',
      get:d=>d?.salidas_sheets > 0 ? d.salidas_sheets : d?.salidas ?? null,
      fmt:fInt,deltaFn:pct,inv:false,
      sumFn:arr=>{
        const v=arr.filter(d=>(d?.salidas_sheets||0)>0);
        if(v.length) return v.reduce((s,d)=>s+(d.salidas_sheets||0),0);
        const w=arr.filter(d=>d?.salidas);return w.length?Math.round(_avg(w.map(d=>d.salidas))):null;
      }},
    {label:'HL/Salida',
      get:d=>{const sal=d?.salidas_sheets>0?d.salidas_sheets:d?.salidas;return(d?.hl&&sal)?Math.round(d.hl/sal*10)/10:null;},
      fmt:fF1,deltaFn:pct,inv:false,sumFn:null},
  ]);

  const calCard = buildCard('📊 Calidad NDS', 'var(--grn)', [
    {label:'NDS %',get:d=>d?.nds,fmt:fP1,deltaFn:pp,inv:false,color:ndsColor,
      sumFn:arr=>{const v=arr.filter(d=>d?.nds!=null);return v.length?Math.round(_avg(v.map(d=>d.nds))*10)/10:null;}},
    {label:'% Rec. HL',get:d=>d?.pct_rec_hl,fmt:fP2,deltaFn:pp,inv:true,color:recColor,
      sumFn:arr=>{const v=arr.filter(d=>d?.pct_rec_hl!=null);return v.length?Math.round(_avg(v.map(d=>d.pct_rec_hl))*100)/100:null;}},
    {label:'% Rec. PDV',get:d=>d?.pct_rec_pdv,fmt:fP1,deltaFn:pp,inv:true,color:recColor,
      sumFn:arr=>{const v=arr.filter(d=>d?.pct_rec_pdv!=null);return v.length?Math.round(_avg(v.map(d=>d.pct_rec_pdv))*10)/10:null;}},
    {label:'Días pico',get:d=>d?.dias_pico,fmt:fInt,deltaFn:null,
      sumFn:arr=>_sum(arr.map(d=>d?.dias_pico||0))},
    {label:'Ausent. %',get:d=>d?.ausentismo,fmt:fP1,deltaFn:pp,inv:true,color:ausColor,
      sumFn:arr=>{const v=arr.filter(d=>d?.ausentismo!=null);return v.length?Math.round(_avg(v.map(d=>d.ausentismo))*10)/10:null;}},
  ]);

  // Clave de dotaci?n seg?n sucursal seleccionada en el comparativo
  const dotKey = _cmpSuc === '1' ? 'cc' : _cmpSuc === '2' ? 'dl' : 'total';
  const gDot   = d => d?.dotacion?.[dotKey] || {};
  const gS1    = d => gDot(d)?.s1 || {};
  const gS2    = d => gDot(d)?.s2 || {};

  const dotCard = buildCard('👷 Dotación', 'var(--pur)', [
    // ── 1ra Salida (Reparto) ─────────────────────────────────
    {label:'S1 Chof/día',
      get:d=>{const s=gS1(d);return s?.tiene_datos?s.avg_chof:null;},
      fmt:fF1,deltaFn:pct,inv:false,
      sumFn:arr=>{const v=arr.filter(d=>gS1(d)?.tiene_datos);return v.length?Math.round(_avg(v.map(d=>gS1(d).avg_chof))*10)/10:null;}},
    {label:'S1 Ayu/día',
      get:d=>{const s=gS1(d);return s?.tiene_datos?Math.round(((s.avg_ayu1||0)+(s.avg_ayu2||0))*10)/10:null;},
      fmt:fF1,deltaFn:pct,inv:false,sumFn:null},
    {label:'S1 Pers/día',
      get:d=>{const s=gS1(d);return s?.tiene_datos?s.avg_pers:null;},
      fmt:fF1,deltaFn:pct,inv:false,
      sumFn:arr=>{const v=arr.filter(d=>gS1(d)?.tiene_datos);return v.length?Math.round(_avg(v.map(d=>gS1(d).avg_pers))*10)/10:null;}},
    // ── 2da Salida (Recargas) ────────────────────────────────
    {label:'S2 Chof/día',
      get:d=>{const s=gS2(d);return s?.tiene_datos?s.avg_chof:null;},
      fmt:fF1,deltaFn:pct,inv:false,
      sumFn:arr=>{const v=arr.filter(d=>gS2(d)?.tiene_datos);return v.length?Math.round(_avg(v.map(d=>gS2(d).avg_chof))*10)/10:null;}},
    {label:'S2 Ayu/día',
      get:d=>{const s=gS2(d);return s?.tiene_datos?Math.round(((s.avg_ayu1||0)+(s.avg_ayu2||0))*10)/10:null;},
      fmt:fF1,deltaFn:pct,inv:false,sumFn:null},
    {label:'S2 Pers/día',
      get:d=>{const s=gS2(d);return s?.tiene_datos?s.avg_pers:null;},
      fmt:fF1,deltaFn:pct,inv:false,
      sumFn:arr=>{const v=arr.filter(d=>gS2(d)?.tiene_datos);return v.length?Math.round(_avg(v.map(d=>gS2(d).avg_pers))*10)/10:null;}},
    // ── HL/Persona total ─────────────────────────────────────
    {label:'HL/Persona',
      get:d=>{const hl=d?.hl,p=gDot(d)?.avg_personas,di=d?.dias;return(hl&&p&&di&&di>0)?Math.round(hl/di/p*10)/10:null;},
      fmt:fF1,deltaFn:pct,inv:false,sumFn:null},
    ...(_cmpSuc === 'TODAS' ? [
      {label:'CC S1/S2',
        get:d=>{const cc=d?.dotacion?.cc;if(!cc?.tiene_datos)return null;const s1=cc.s1?.tiene_datos?cc.s1.avg_chof+'':'-';const s2=cc.s2?.tiene_datos?cc.s2.avg_chof:'?';return s1+'/'+s2;},
        fmt:v=>v,deltaFn:null,sumFn:null},
      {label:'DL S1/S2',
        get:d=>{const dl=d?.dotacion?.dl;if(!dl?.tiene_datos)return null;const s1=dl.s1?.tiene_datos?dl.s1.avg_chof+'':'-';const s2=dl.s2?.tiene_datos?dl.s2.avg_chof:'?';return s1+'/'+s2;},
        fmt:v=>v,deltaFn:null,sumFn:null},
    ] : []),
  ]);

  const leyendaPie = '<div style="margin-top:6px;font-size:10.5px;color:var(--muted);display:flex;gap:16px;flex-wrap:wrap;align-items:center;padding:2px 0">'
    + '<span>🔮 Meses futuros = proyección basada en '+anio_base+'</span>'
    + '<span><span class="sem ok"></span> Sin riesgo</span>'
    + '<span><span class="sem warn"></span> Moderado</span>'
    + '<span><span class="sem crit"></span> Riesgo alto</span>'
    + '<span>HL/Salida = eficiencia por viaje &nbsp;·&nbsp; HL/Persona = productividad operativa</span>'
    + '<span style="margin-left:auto;font-family:var(--mono)">base <strong>'+anio_base+'</strong> → actual <strong style="color:var(--acc)">'+anio+'</strong></span>'
    + '</div>';
  cont.innerHTML = '<div class="cmp-grid">'+volCard+calCard+dotCard+'</div>' + leyendaPie;
}


// ─── DOTACIÓN OPERATIVA ───────────────────────────────────────
let _dotAbort = null;

function _initDotFechas() {
  const fi = document.getElementById('dotFechaIni');
  const ff = document.getElementById('dotFechaFin');
  if (fi && !fi.value) {
    const hoy = new Date();
    fi.value = `${hoy.getFullYear()}-${String(hoy.getMonth()+1).padStart(2,'0')}-01`;
  }
  if (ff && !ff.value) {
    const hoy = new Date();
    ff.value = hoy.toISOString().slice(0,10);
  }
}

async function loadDotacion() {
  _initDotFechas();
  // Inicializar selector de cobertura con el mes actual si est? vac?o
  const cobMesEl = document.getElementById('cobPicoMes');
  if (cobMesEl && !cobMesEl.value) {
    const hoy = new Date();
    cobMesEl.value = `${hoy.getFullYear()}-${String(hoy.getMonth()+1).padStart(2,'0')}`;
  }
  const ids = ['dotCasaCentral', 'dotDolores', 'dotTotal'];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  });
  if (_dotAbort) _dotAbort.abort();
  _dotAbort = new AbortController();
  const fi = document.getElementById('dotFechaIni')?.value;
  const ff = document.getElementById('dotFechaFin')?.value;
  try {
    const data = await api(
      `/api/picos/dotacion-diaria?sucursal_id=TODAS&fecha_ini=${fi}&fecha_fin=${ff}`,
      { signal: _dotAbort.signal, timeout: 60000 }
    );
    renderDotacionPanel('dotCasaCentral', data.casa_central || [], 'Casa Central');
    renderDotacionPanel('dotDolores',     data.dolores      || [], 'Dolores');
    renderDotacionPanel('dotTotal',       data.total        || [], 'Total empresa', true);
  } catch (e) {
    if (e.name === 'AbortError') return;
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = `<div style="color:var(--red);font-size:11px">${e.message}</div>`;
    });
  }
}

function renderDotacionPanel(contId, dias, titulo, esTotal = false) {
  const cont = document.getElementById(contId);
  if (!cont) return;
  if (!dias.length) {
    cont.innerHTML = '<div style="color:var(--muted);font-size:11px">Sin datos para el período.</div>';
    return;
  }

  let html = '<div style="max-height:520px;overflow-y:auto">';
  html += `<table class="dot-tbl"><thead><tr>
    <th>Fecha</th>
    ${esTotal ? '' : '<th>#</th><th>Chofer</th><th>Ayudante 1</th><th>Ayudante 2</th>'}
    <th>Salidas</th><th>Choferes</th><th>Ayu.1</th><th>Ayu.2</th><th>Total</th>
  </tr></thead><tbody>`;

  dias.forEach(d => {
    const fecha = d.fecha?.slice(5);  // MM-DD
    if (esTotal) {
      html += `<tr>
        <td style="font-weight:600;color:var(--acc)">${fecha}</td>
        <td>${d.n_salidas}</td><td>${d.n_choferes}</td>
        <td>${d.n_ayudante1}</td><td>${d.n_ayudante2}</td>
        <td style="font-weight:600;color:var(--grn)">${d.total_personas}</td>
      </tr>`;
    } else {
      // Fila cabecera del d?a
      html += `<tr class="day-header">
        <td colspan="7" style="padding-left:6px">${fecha} ? ${d.n_salidas} salidas ? ${d.total_personas} personas</td>
      </tr>`;
      // Detalle por salida
      (d.detalle || []).forEach(s => {
        html += `<tr>
          <td></td>
          <td style="color:var(--muted)">${s.nro_salida}</td>
          <td>${escHtml(s.chofer)}</td>
          <td style="color:var(--muted)">${escHtml(s.ayudante_1)}</td>
          <td style="color:var(--muted)">${escHtml(s.ayudante_2)}</td>
          <td></td><td></td><td></td><td></td>
          <td style="color:var(--grn);font-weight:600">${s.personas}</td>
        </tr>`;
      });
      // Fila resumen del d?a
      html += `<tr class="day-total">
        <td colspan="5" style="text-align:right;padding-right:8px">Totales d?a:</td>
        <td>${d.n_salidas}</td><td>${d.n_choferes}</td>
        <td>${d.n_ayudante1}</td><td>${d.n_ayudante2}</td>
        <td style="font-weight:700;color:var(--grn)">${d.total_personas}</td>
      </tr>`;
    }
  });

  html += '</tbody></table></div>';
  cont.innerHTML = html;
}

async function loadCoberturaPicos() {
  const cont = document.getElementById('coberturaPicos');
  if (!cont) return;
  const mesVal = document.getElementById('cobPicoMes')?.value;
  const sucVal = document.getElementById('cobPicoSuc')?.value || 'TODAS';
  if (!mesVal) {
    cont.innerHTML = '<div style="color:var(--acc);font-size:11px">Seleccioná un mes.</div>';
    return;
  }
  const [anio, mes] = mesVal.split('-');
  cont.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try {
    const data = await api(`/api/picos/cobertura-dotacion?anio=${anio}&mes=${parseInt(mes)}&sucursal_id=${sucVal}`, { timeout: 90000 });
    renderCoberturaPicos(data);
  } catch (e) {
    cont.innerHTML = `<div style="color:var(--red);font-size:11px">${e.message}</div>`;
  }
}

function renderCoberturaPicos(data) {
  const cont = document.getElementById('coberturaPicos');
  if (!cont) return;
  const { picos, resumen } = data;

  if (!picos || !picos.length) {
    cont.innerHTML = '<div style="color:var(--muted);font-size:11px">Sin días pico para el período seleccionado.</div>';
    return;
  }

  const pctS2 = resumen.pct_cobertura_s2 ?? 0;
  const pctColor = pctS2 >= 80 ? 'var(--grn)' : pctS2 >= 50 ? 'var(--acc)' : 'var(--red)';

  let html = `<div style="display:flex;gap:12px;margin-bottom:14px;flex-wrap:wrap">
    <div class="kpi-card" style="min-width:110px"><div class="kv" style="color:var(--acc)">${resumen.total}</div><div class="klbl">Días pico</div></div>
    <div class="kpi-card" style="min-width:110px"><div class="kv" style="color:${pctColor}">${pctS2}%</div><div class="klbl">Con doble salida</div></div>
    <div class="kpi-card" style="min-width:110px"><div class="kv" style="color:var(--grn)">${resumen.con_s2}</div><div class="klbl">2 salidas ●</div></div>
    <div class="kpi-card" style="min-width:110px"><div class="kv" style="color:var(--acc)">${resumen.sin_s2 ?? 0}</div><div class="klbl">Solo 1 salida ◐</div></div>
    <div class="kpi-card" style="min-width:110px"><div class="kv" style="color:var(--red)">${resumen.sin_datos}</div><div class="klbl">Sin datos â—‹</div></div>
    <div class="kpi-card" style="min-width:110px"><div class="kv">${resumen.avg_personas}</div><div class="klbl">Pers/día pico (prom)</div></div>
  </div>`;

  html += `<div style="overflow-x:auto"><table class="cob-tbl"><thead><tr>
    <th>Estado</th><th>Fecha</th><th>Bultos</th><th>HL</th><th>NDS</th>
    <th>Salida 1 (reparto)</th><th>Salida 2 (recarga)</th><th>Total personas</th>
  </tr></thead><tbody>`;

  picos.forEach(p => {
    const dot = p.dot || {};
    const s1  = dot.s1;
    const s2  = dot.s2;
    const sem = p.semaforo;
    const semLabel = sem === 'verde' ? 'Completo' : sem === 'amarillo' ? '1 salida' : 'Sin datos';
    const s1txt = s1 ? `${s1.personas}p · ${s1.camiones} cam.` : '?';
    const s2txt = s2
      ? `<span style="color:var(--grn);font-weight:600">${s2.personas}p · ${s2.camiones} cam.</span>`
      : `<span style="color:var(--muted)">No registrada</span>`;
    const ndsValue = p.nds ?? 100;
    const ndsColor = ndsValue < 85 ? 'var(--red)' : ndsValue < 95 ? 'var(--acc)' : 'var(--grn)';

    html += `<tr>
      <td><span class="cob-sem ${sem}">${semLabel}</span></td>
      <td>${p.fecha}</td>
      <td>${fmtN(Math.round(p.bultos))}</td>
      <td>${fmtN(Math.round(p.hectolitros))}</td>
      <td style="color:${ndsColor}">${ndsValue}%</td>
      <td>${s1txt}</td>
      <td>${s2txt}</td>
      <td style="font-weight:600">${dot.tiene_datos ? dot.total_personas : '?'}</td>
    </tr>`;
  });

  html += '</tbody></table></div>';
  cont.innerHTML = html;
}


// ─── CALIBRES ────────────────────────────────────────────────
async function loadCalibres() {
  const cont = document.getElementById('calibresTabla');
  if (!cont) return;
  const anioEl = document.getElementById('calibreAnio');
  if (anioEl && !anioEl.value) anioEl.value = new Date().getFullYear();
  cont.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  const anio = document.getElementById('calibreAnio')?.value || new Date().getFullYear();
  const suc  = document.getElementById('calibreSuc')?.value  || 'TODAS';
  const div  = document.getElementById('calibreDiv')?.value  || '';
  const med  = document.getElementById('calibreMedida')?.value || 'bultos';
  try {
    const qs = new URLSearchParams({ anio, sucursal: suc });
    if (div) qs.set('division', div);
    const data = await api('/api/articulos/bultos-por-calibre?' + qs, { timeout: 60000 });
    const divEl = document.getElementById('calibreDiv');
    if (divEl && data.divisiones?.length) {
      const cur = divEl.value;
      divEl.innerHTML = '<option value="">Todas las divisiones</option>'
        + data.divisiones.map(d => '<option value="' + escHtml(d) + '"' + (d === cur ? ' selected' : '') + '>' + escHtml(d) + '</option>').join('');
    }
    renderCalibres(data, med);
  } catch(e) {
    cont.innerHTML = '<div style="color:var(--red);font-size:12px">' + e.message + '</div>';
  }
}

let _calibreData = null;
function _onCalMedidaChange() {
  if (_calibreData) renderCalibres(_calibreData, this.value);
}

function renderCalibres(data, medida) {
  medida = medida || 'bultos';
  const cont = document.getElementById('calibresTabla');
  if (!cont) return;
  if (!data.calibres || !data.calibres.length) {
    cont.innerHTML = '<div style="color:var(--muted);font-size:12px">Sin datos.</div>';
    return;
  }
  const meses = data.meses_nombres;
  const esBultos = medida === 'bultos';
  const fmt = function(v) { return v > 0 ? fmtN(Math.round(v)) : '<span style="color:var(--muted)">—</span>'; };

  // Detectar meses con datos
  const mesesConDatos = [1,2,3,4,5,6,7,8,9,10,11,12].filter(function(m) {
    return data.calibres.some(function(c) { return (c[medida] && c[medida][m] > 0); });
  });

  let html = '<div style="overflow-x:auto"><table class="rtbl" style="font-size:11px"><thead><tr>'
    + '<th style="text-align:left;min-width:80px">Calibre</th>'
    + mesesConDatos.map(function(m) { return '<th>' + meses[m-1] + '</th>'; }).join('')
    + '<th style="font-weight:700">Total</th>'
    + '</tr></thead><tbody>';

  data.calibres.forEach(function(c) {
    const total = esBultos ? c.total_bultos : c.total_pallets;
    if (total < 1) return;
    html += '<tr>'
      + '<td style="font-weight:600;text-align:left">' + escHtml(c.calibre_label) + '</td>'
      + mesesConDatos.map(function(m) {
          const v = (c[medida] && c[medida][m]) || 0;
          return '<td style="font-family:var(--mono);text-align:right">' + fmt(v) + '</td>';
        }).join('')
      + '<td style="font-family:var(--mono);font-weight:700;text-align:right;color:var(--acc)">' + fmtN(Math.round(total)) + '</td>'
      + '</tr>';
  });

  // Fila totales
  const totales = mesesConDatos.map(function(m) {
    return data.calibres.reduce(function(s, c) { return s + ((c[medida] && c[medida][m]) || 0); }, 0);
  });
  const granTotal = data.calibres.reduce(function(s, c) {
    return s + (esBultos ? c.total_bultos : c.total_pallets);
  }, 0);
  html += '<tr style="background:var(--surf3);font-weight:700">'
    + '<td style="text-align:left">TOTAL</td>'
    + totales.map(function(v) { return '<td style="font-family:var(--mono);text-align:right;color:var(--grn)">' + fmtN(Math.round(v)) + '</td>'; }).join('')
    + '<td style="font-family:var(--mono);text-align:right;color:var(--grn)">' + fmtN(Math.round(granTotal)) + '</td>'
    + '</tr>';

  html += '</tbody></table></div>';

  // Re-render sin recarga al cambiar medida
  _calibreData = data;
  const medEl = document.getElementById('calibreMedida');
  if (medEl) {
    medEl.removeEventListener('change', _onCalMedidaChange);
    medEl.addEventListener('change', _onCalMedidaChange);
  }

  cont.innerHTML = html;
}
