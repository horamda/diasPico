
// ─────────────────────────────────────────────────────────────────
// SIMULADOR LOGÍSTICO
// ─────────────────────────────────────────────────────────────────

let _simlResultadoActual = null;
const RIESGO_COLOR = { BAJO: 'var(--grn)', MEDIO: 'var(--acc)', ALTO: '#e08c2a', CRITICO: 'var(--red)' };

function switchSimlTab(t, el) {
  document.querySelectorAll('#tab-simulador .plan-tab').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
  ['form', 'avance', 'cierre', 'lista'].forEach(p => {
    const panel = document.getElementById('siml-panel-' + p);
    if (panel) panel.style.display = p === t ? '' : 'none';
  });
  if (t === 'lista')  cargarListaSimulaciones();
  if (t === 'avance') cargarSelectsSimulacion('simlAvanceId');
  if (t === 'cierre') cargarSelectsSimulacion('simlCierreId');
}

let _simlSucursales = []; // cache de sucursales para "simular todas"

function initSimulador() {
  const sel = document.getElementById('simlSucursal');
  if (!sel) return;
  if (sel.options.length <= 1) {
    fetch(API + '/api/sucursales').then(r => r.json()).then(d => {
      _simlSucursales = d.sucursales || [];
      sel.innerHTML = '<option value="TODAS">General (todas las sucursales)</option>' +
        _simlSucursales.map(s => `<option value="${esc(s.id)}">${esc(s.nombre || s.id)}</option>`).join('');
      sel.value = getSuc() || 'TODAS';
    }).catch(() => {});
  }
  const anioEl = document.getElementById('simlAnio');
  const mesEl  = document.getElementById('simlMes');
  if (anioEl && !anioEl.value) anioEl.value = vY;
  if (mesEl  && !mesEl.value)  mesEl.value  = vM + 1;
  // Llenar años en el filtro de lista
  const listaAnio = document.getElementById('simlListaAnio');
  if (listaAnio && listaAnio.options.length <= 1) {
    const cur = new Date().getFullYear();
    for (let y = cur; y >= cur - 4; y--) {
      const o = document.createElement('option');
      o.value = y; o.textContent = y;
      listaAnio.appendChild(o);
    }
  }
}

function simlSucursalChanged() {
  _simlResultadoActual = null;
  const btn = document.getElementById('simlBtnGuardar');
  if (btn) btn.disabled = true;
}

function _simlParams() {
  return {
    empresa_id:           '1',
    sucursal_id:          document.getElementById('simlSucursal')?.value || 'TODAS',
    anio:                 parseInt(document.getElementById('simlAnio')?.value || vY),
    mes:                  parseInt(document.getElementById('simlMes')?.value || (vM + 1)),
    crecimiento_esperado: parseFloat(document.getElementById('simlCrecVal')?.value || 0),
    ausentismo_esperado:  parseFloat(document.getElementById('simlAusVal')?.value || 5),
    camiones_disponibles: parseFloat(document.getElementById('simlCamiones')?.value || 0),
    dias_trabajados:      parseInt(document.getElementById('simlDias')?.value || 22),
    dias_pico_esperados:  parseInt(document.getElementById('simlDiasPico')?.value || 0),
    observaciones:        document.getElementById('simlObs')?.value || '',
  };
}

async function ejecutarSimulacion() {
  const msg = document.getElementById('simlMsg');
  const btn = document.getElementById('simlBtnGuardar');
  const res = document.getElementById('simlResultado');
  if (!res) return;
  res.innerHTML = '<div class="loading"><div class="spinner"></div>Calculando simulación…</div>';
  if (msg) { msg.textContent = ''; msg.style.color = ''; }
  if (btn)  btn.disabled = true;
  _simlResultadoActual = null;
  try {
    const data = await api('/api/simulaciones/calcular', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(_simlParams()),
    });
    _simlResultadoActual = data;
    if (btn) btn.disabled = false;
    renderSimulacion(data, res);
  } catch(e) {
    res.innerHTML = `<div class="box" style="color:var(--red);padding:20px">${esc(e.message)}</div>`;
    if (msg) { msg.textContent = '⚠ ' + e.message; msg.style.color = 'var(--red)'; }
  }
}

async function guardarSimulacion() {
  if (!_simlResultadoActual) return;
  const msg = document.getElementById('simlMsg');
  if (msg) { msg.textContent = 'Guardando…'; msg.style.color = 'var(--muted)'; }
  const btn = document.getElementById('simlBtnGuardar');
  if (btn) btn.disabled = true;
  try {
    const data = await api('/api/simulaciones/guardar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(_simlParams()),
    });
    if (msg) { msg.textContent = `✓ Guardada (ID ${data.id})`; msg.style.color = 'var(--grn)'; }
  } catch(e) {
    if (msg) { msg.textContent = '⚠ ' + e.message; msg.style.color = 'var(--red)'; }
    if (btn) btn.disabled = false;
  }
}

function renderSimulacion(data, container) {
  const b    = data.base    || {};
  const p    = data.plan    || {};
  const r    = data.riesgo  || {};
  const recom= data.recomendaciones || [];
  const apr  = data.aprendizaje || {};
  const mes  = MESES[(data.params?.mes || 1) - 1] || '';
  const anio = data.params?.anio || '';
  const mesBase  = MESES[(b.mes || 1) - 1] || '';
  const anioBase = b.anio || '';
  const rColor   = RIESGO_COLOR[r.nivel] || 'var(--muted)';

  const n2 = v => Number(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 1 });
  const n0 = v => Number(v || 0).toLocaleString('es-AR');

  const varPct = (plan, base) => {
    const b2 = Number(base || 0);
    if (!b2) return '—';
    const d = ((Number(plan || 0) - b2) / b2 * 100).toFixed(1);
    const c = d > 0 ? 'var(--acc)' : (d < 0 ? 'var(--blu)' : 'var(--muted)');
    return `<span style="color:${c}">${d > 0 ? '+' : ''}${d}%</span>`;
  };

  const riesgoBadge = `<span style="background:${rColor};color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:12px">${r.nivel || '—'} (${r.score || 0})</span>`;

  const kpis = [
    { lbl: 'HL plan',          val: n2(p.hl_plan),             cls: 'blu' },
    { lbl: 'Bultos plan',      val: n0(p.bultos_plan),         cls: 'blu' },
    { lbl: 'Pallets plan',     val: n2(p.pallets_plan),        cls: 'blu' },
    { lbl: 'PDV plan',         val: n0(p.pdv_plan),            cls: 'ora' },
    { lbl: 'Camiones/día',     val: n2(p.camiones_necesarios), cls: 'ora' },
    { lbl: 'Personas',         val: n0(p.personas_necesarias), cls: 'ora' },
    { lbl: 'Salidas',          val: n0(p.salidas_necesarias),  cls: 'grn' },
    { lbl: 'Cam. día pico',    val: n2(p.camiones_dia_pico),   cls: 'red' },
    { lbl: 'Per. día pico',    val: n0(p.personas_dia_pico),   cls: 'red' },
    { lbl: 'Sal. día pico',    val: n0(p.salidas_dia_pico),    cls: 'red' },
    { lbl: 'Cam. adicionales', val: n2(p.camiones_adicionales),cls: (p.camiones_adicionales > 0) ? 'red' : 'grn' },
    { lbl: 'Riesgo',           val: riesgoBadge,               cls: '' },
  ];

  const kpiHtml = `<div class="kpi-grid" style="grid-template-columns:repeat(4,1fr)">${kpis.map(k =>
    `<div class="kpi ${k.cls}"><div class="kpi-lbl">${k.lbl}</div><div class="kpi-val" style="font-size:16px;font-family:var(--mono)">${k.val}</div></div>`
  ).join('')}</div>`;

  const rows = [
    ['HL',       b.hl,         p.hl_plan],
    ['Bultos',   b.bultos,     p.bultos_plan],
    ['Pallets',  b.pallets,    p.pallets_plan],
    ['PDV',      b.pdv_unicos, p.pdv_plan],
    ['Salidas',  b.salidas,    p.salidas_necesarias],
    ['Camiones', b.camiones,   p.camiones_necesarios],
    ['Personas', b.personas,   p.personas_necesarias],
  ];
  const tablaHtml = `
    <table class="rtbl">
      <thead><tr><th>Indicador</th><th>${mesBase} ${anioBase} (base)</th><th>${mes} ${anio} (simulado)</th><th>Variación</th></tr></thead>
      <tbody>${rows.map(([lbl, vb, vp]) =>
        `<tr><td>${lbl}</td><td style="text-align:right">${n2(vb)}</td><td style="text-align:right;font-weight:600">${n2(vp)}</td><td style="text-align:center">${varPct(vp, vb)}</td></tr>`
      ).join('')}</tbody>
    </table>`;

  const recomHtml = recom.length
    ? `<ul style="list-style:none;display:flex;flex-direction:column;gap:8px">${recom.map(r2 =>
        `<li style="background:var(--surf2);border-left:3px solid var(--acc);padding:8px 12px;border-radius:0 6px 6px 0;font-size:12px">▸ ${esc(r2)}</li>`
      ).join('')}</ul>`
    : '<span style="color:var(--muted);font-size:12px">Sin recomendaciones.</span>';

  const riesgoDetalle = (r.detalle || []).length
    ? `<ul style="list-style:none;display:flex;flex-direction:column;gap:5px;margin-top:6px">${r.detalle.map(d2 =>
        `<li style="font-size:11px;color:var(--muted)">• ${esc(d2)}</li>`
      ).join('')}</ul>` : '';

  const aprHtml = apr.aplicado
    ? `<div style="margin-top:8px;padding:8px;background:var(--surf3);border-radius:6px;font-size:11px;color:var(--muted)">
        ✦ Ajuste por aprendizaje (${apr.registros} cierres) —
        Camiones ×${Number(apr.factores?.camiones||1).toFixed(3)} |
        Personas ×${Number(apr.factores?.personas||1).toFixed(3)} |
        Salidas ×${Number(apr.factores?.salidas||1).toFixed(3)}
       </div>` : '';

  container.innerHTML = `
    <div class="box">
      <div class="sec" style="margin-bottom:10px">Proyección — ${mes} ${anio} (base: ${mesBase} ${anioBase})</div>
      ${kpiHtml}${aprHtml}
    </div>
    <div class="chart-grid" style="margin-top:12px">
      <div class="box">
        <div class="sec" style="margin-bottom:10px">Comparativo base vs simulado</div>
        ${tablaHtml}
      </div>
      <div class="box">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
          <div class="sec">Riesgo operativo</div>${riesgoBadge}
        </div>
        ${riesgoDetalle}
        <div class="sec" style="margin-top:14px;margin-bottom:8px">Recomendaciones</div>
        ${recomHtml}
      </div>
    </div>`;
}

async function cargarListaSimulaciones() {
  const el = document.getElementById('simlLista');
  if (!el) return;
  el.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando…</div>';
  try {
    // Traer todas (sin filtro de sucursal, para poder mostrar comparativo)
    const data = await api(`/api/simulaciones?limit=200`);
    let rows = data.simulaciones || [];

    // Filtrar por año/mes si están seleccionados
    const filtroAnio = parseInt(document.getElementById('simlListaAnio')?.value || 0);
    const filtroMes  = parseInt(document.getElementById('simlListaMes')?.value  || 0);
    if (filtroAnio) rows = rows.filter(s => s.anio === filtroAnio);
    if (filtroMes)  rows = rows.filter(s => s.mes  === filtroMes);

    if (!rows.length) {
      el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--muted)">Sin simulaciones guardadas para el período seleccionado.</div>';
      document.getElementById('simlComparacion').style.display = 'none';
      return;
    }

    const rColor = lv => RIESGO_COLOR[lv] || 'var(--muted)';
    const eColor = e  => e === 'CERRADA' ? 'var(--muted)' : e === 'EN_AVANCE' ? 'var(--acc)' : 'var(--grn)';

    // Agrupar por período para mostrar indicador de comparación
    const porPeriodo = {};
    rows.forEach(s => {
      const k = `${s.anio}-${s.mes}`;
      if (!porPeriodo[k]) porPeriodo[k] = [];
      porPeriodo[k].push(s);
    });

    el.innerHTML = `<table class="rtbl">
      <thead><tr><th>ID</th><th>Período</th><th>Sucursal</th><th>Crec.%</th><th>HL plan</th><th>Cam.nec.</th><th>Per.nec.</th><th>Riesgo</th><th>Estado</th><th></th></tr></thead>
      <tbody>${rows.map(s => {
        const k = `${s.anio}-${s.mes}`;
        const multi = (porPeriodo[k]?.length || 1) > 1;
        return `<tr>
          <td style="font-family:var(--mono);font-size:11px">#${s.id}</td>
          <td>${MESES[(s.mes||1)-1]} ${s.anio}${multi ? ` <button class="btn sm" style="padding:1px 5px;font-size:9px" onclick="mostrarComparacion(${s.anio},${s.mes})">≡</button>` : ''}</td>
          <td><span style="font-weight:${s.sucursal_id==='TODAS'?'600':'400'};color:${s.sucursal_id==='TODAS'?'var(--acc)':'var(--txt)'}">${esc(s.sucursal_id)}</span></td>
          <td style="text-align:right">${Number(s.crecimiento_esperado||0).toFixed(1)}%</td>
          <td style="text-align:right">${Number(s.hl_plan||0).toLocaleString('es-AR',{maximumFractionDigits:0})}</td>
          <td style="text-align:right">${Number(s.camiones_necesarios||0).toFixed(1)}</td>
          <td style="text-align:right">${Number(s.personas_necesarias||0).toFixed(0)}</td>
          <td><span style="color:${rColor(s.riesgo_nivel)};font-weight:600">${s.riesgo_nivel||'—'}</span></td>
          <td><span style="color:${eColor(s.estado)}">${s.estado||'—'}</span></td>
          <td><button class="btn sm" onclick="verSimulacion(${s.id})">Ver</button></td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;

    // Mostrar comparación automática si hay un período con múltiples sucursales
    const periodosMulti = Object.entries(porPeriodo).filter(([,v]) => v.length > 1);
    if (filtroAnio && filtroMes && periodosMulti.length > 0) {
      mostrarComparacion(filtroAnio, filtroMes, rows);
    } else {
      document.getElementById('simlComparacion').style.display = 'none';
    }
  } catch(e) {
    el.innerHTML = `<div style="color:var(--red);padding:16px">⚠ ${esc(e.message)}</div>`;
  }
}

function mostrarComparacion(anio, mes, rowsCache) {
  const comp = document.getElementById('simlComparacion');
  const tabla = document.getElementById('simlComparacionTabla');
  if (!comp || !tabla) return;

  const rows = rowsCache || [];
  const del_periodo = rows.filter(s => s.anio === anio && s.mes === mes);
  if (del_periodo.length < 2) { comp.style.display = 'none'; return; }

  // Ordenar: TODAS primero, luego el resto
  del_periodo.sort((a, b) => {
    if (a.sucursal_id === 'TODAS') return -1;
    if (b.sucursal_id === 'TODAS') return  1;
    return a.sucursal_id.localeCompare(b.sucursal_id);
  });

  const n2 = v => Number(v||0).toLocaleString('es-AR', {maximumFractionDigits:1});
  const n0 = v => Number(v||0).toLocaleString('es-AR', {maximumFractionDigits:0});
  const rColor = lv => RIESGO_COLOR[lv] || 'var(--muted)';

  tabla.innerHTML = `
    <div style="font-size:11px;color:var(--muted);margin-bottom:8px">${MESES[mes-1]} ${anio} — ${del_periodo.length} simulaciones</div>
    <div style="overflow-x:auto">
    <table class="rtbl">
      <thead>
        <tr>
          <th>Indicador</th>
          ${del_periodo.map(s => `<th style="color:${s.sucursal_id==='TODAS'?'var(--acc)':'var(--txt)'}">${esc(s.sucursal_id)}</th>`).join('')}
        </tr>
      </thead>
      <tbody>
        <tr><td>HL plan</td>${del_periodo.map(s => `<td style="text-align:right">${n2(s.hl_plan)}</td>`).join('')}</tr>
        <tr><td>Camiones necesarios</td>${del_periodo.map(s => `<td style="text-align:right">${n2(s.camiones_necesarios)}</td>`).join('')}</tr>
        <tr><td>Personas necesarias</td>${del_periodo.map(s => `<td style="text-align:right">${n0(s.personas_necesarias)}</td>`).join('')}</tr>
        <tr><td>Camiones día pico</td>${del_periodo.map(s => `<td style="text-align:right">${n2(s.camiones_dia_pico)}</td>`).join('')}</tr>
        <tr><td>Personas día pico</td>${del_periodo.map(s => `<td style="text-align:right">${n0(s.personas_dia_pico)}</td>`).join('')}</tr>
        <tr><td>Cam. adicionales</td>${del_periodo.map(s => `<td style="text-align:right;color:${Number(s.camiones_adicionales||0)>0?'var(--red)':'var(--grn)'}">${n2(s.camiones_adicionales)}</td>`).join('')}</tr>
        <tr><td>Crecimiento %</td>${del_periodo.map(s => `<td style="text-align:right">${Number(s.crecimiento_esperado||0).toFixed(1)}%</td>`).join('')}</tr>
        <tr><td>Riesgo</td>${del_periodo.map(s => `<td style="text-align:center"><span style="color:${rColor(s.riesgo_nivel)};font-weight:600">${s.riesgo_nivel||'—'}</span></td>`).join('')}</tr>
        <tr><td>Estado</td>${del_periodo.map(s => `<td style="text-align:center;font-size:11px">${s.estado||'—'}</td>`).join('')}</tr>
      </tbody>
    </table></div>`;
  comp.style.display = '';
}

async function verSimulacion(id) {
  try {
    const data   = await api(`/api/simulaciones/${id}`);
    const sim    = data.simulacion || {};
    const recom  = sim.recomendaciones || [];
    const cierre = data.cierre;
    const avances= data.avances || [];
    const rColor = RIESGO_COLOR[sim.riesgo_nivel] || 'var(--muted)';
    const n2 = v => Number(v||0).toLocaleString('es-AR', {minimumFractionDigits:0, maximumFractionDigits:1});

    let html = `<div style="max-width:700px">
      <div class="sec" style="margin-bottom:10px">#${sim.id} — ${MESES[(sim.mes||1)-1]} ${sim.anio} (${esc(sim.sucursal_id)})</div>
      <div class="kpi-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:12px">
        ${[['HL plan',n2(sim.hl_plan),'blu'],['Camiones',n2(sim.camiones_necesarios),'ora'],
           ['Personas',n2(sim.personas_necesarias),'ora'],['Cam. pico',n2(sim.camiones_dia_pico),'red'],
           ['Per. pico',n2(sim.personas_dia_pico),'red'],
           ['Riesgo',`<span style="color:${rColor};font-weight:700">${sim.riesgo_nivel||'—'}</span>`,'']
          ].map(([l,v,c]) => `<div class="kpi ${c}"><div class="kpi-lbl">${l}</div><div class="kpi-val" style="font-size:14px">${v}</div></div>`).join('')}
      </div>`;

    if (recom.length) {
      html += `<div class="sec" style="margin-bottom:6px">Recomendaciones</div>
        <ul style="list-style:none;display:flex;flex-direction:column;gap:5px;margin-bottom:12px">
          ${recom.map(r2 => `<li style="font-size:11px;background:var(--surf2);padding:6px 10px;border-radius:4px">▸ ${esc(r2)}</li>`).join('')}
        </ul>`;
    }
    if (avances.length) {
      html += `<div class="sec" style="margin-bottom:6px">Avances (${avances.length})</div>
        <table class="rtbl" style="margin-bottom:12px">
          <thead><tr><th>Días</th><th>HL real</th><th>Cam. real</th><th>Disp. HL%</th><th>Fecha</th></tr></thead>
          <tbody>${avances.map(a => {
            const col = _simlSemColor(a.dispersion_hl_pct);
            return `<tr><td>${a.dias_transcurridos}</td><td style="text-align:right">${n2(a.hl_real)}</td><td style="text-align:right">${n2(a.camiones_real)}</td><td style="text-align:right;color:${col}">${a.dispersion_hl_pct != null ? Number(a.dispersion_hl_pct).toFixed(1)+'%' : '—'}</td><td style="font-size:10px;color:var(--muted)">${(a.created_at||'').slice(0,16)}</td></tr>`;
          }).join('')}</tbody>
        </table>`;
    }
    if (cierre) {
      const n1 = v => v != null ? (Number(v) > 0 ? '+' : '') + Number(v).toFixed(1) + '%' : '—';
      const col= v => { const a = Math.abs(Number(v||0)); return a <= 5 ? 'var(--grn)' : a <= 10 ? 'var(--acc)' : 'var(--red)'; };
      html += `<div class="sec" style="margin-bottom:6px;color:var(--grn)">✔ Cerrado</div>
        <table class="rtbl"><thead><tr><th>Métrica</th><th>Error %</th></tr></thead><tbody>
          ${[['HL','error_hl_pct'],['Camiones','error_camiones_pct'],['Personas','error_personas_pct'],['Salidas','error_salidas_pct']].map(([l,k]) =>
            `<tr><td>${l}</td><td style="text-align:right;color:${col(cierre[k])}">${n1(cierre[k])}</td></tr>`).join('')}
        </tbody></table>
        ${cierre.conclusiones ? `<div style="margin-top:8px;font-size:11px;color:var(--muted)">${esc(cierre.conclusiones)}</div>` : ''}`;
    }
    html += '</div>';

    let modal = document.getElementById('simlModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'simlModal';
      modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:999;display:flex;align-items:center;justify-content:center;padding:20px';
      modal.innerHTML = `<div style="background:var(--surf);border:1px solid var(--brd);border-radius:10px;padding:20px;max-width:740px;width:100%;max-height:80vh;overflow-y:auto;position:relative">
        <button onclick="document.getElementById('simlModal').remove()" style="position:absolute;top:12px;right:14px;background:none;border:none;color:var(--muted);font-size:16px;cursor:pointer">✕</button>
        <div id="simlModalBody"></div></div>`;
      document.body.appendChild(modal);
    }
    document.getElementById('simlModalBody').innerHTML = html;
  } catch(e) {
    alert('Error al cargar: ' + e.message);
  }
}

function _simlSemColor(pct) {
  const abs = Math.abs(Number(pct||0));
  if (abs <= 5)  return 'var(--grn)';
  if (abs <= 10) return 'var(--acc)';
  return 'var(--red)';
}

async function cargarSelectsSimulacion(selectId) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  try {
    const suc  = document.getElementById('simlSucursal')?.value || 'TODAS';
    const data = await api(`/api/simulaciones?sucursal_id=${encodeURIComponent(suc)}&limit=50`);
    const rows = (data.simulaciones || []).filter(s => s.estado !== 'CERRADA');
    sel.innerHTML = rows.length
      ? rows.map(s => `<option value="${s.id}">${MESES[(s.mes||1)-1]} ${s.anio} — ${esc(s.sucursal_id)} (#${s.id})</option>`).join('')
      : '<option value="">Sin simulaciones abiertas</option>';
  } catch(e) {
    sel.innerHTML = '<option value="">Error al cargar</option>';
  }
}

async function registrarAvance() {
  const msg = document.getElementById('simlAvanceMsg');
  const id  = parseInt(document.getElementById('simlAvanceId')?.value || 0);
  if (!id) { if (msg) { msg.textContent = 'Seleccioná una simulación'; msg.style.color = 'var(--red)'; } return; }
  if (msg) { msg.textContent = 'Guardando…'; msg.style.color = 'var(--muted)'; }
  try {
    const payload = {
      dias_transcurridos: parseInt(document.getElementById('simlAvanceDias')?.value || 0),
      hl_real:       parseFloat(document.getElementById('simlAvHl')?.value       || 0),
      bultos_real:   parseFloat(document.getElementById('simlAvBultos')?.value   || 0),
      pallets_real:  parseFloat(document.getElementById('simlAvPallets')?.value  || 0),
      pdv_real:      parseFloat(document.getElementById('simlAvPdv')?.value      || 0),
      salidas_real:  parseFloat(document.getElementById('simlAvSalidas')?.value  || 0),
      camiones_real: parseFloat(document.getElementById('simlAvCamiones')?.value || 0),
      personas_real: parseFloat(document.getElementById('simlAvPersonas')?.value || 0),
      rechazos_real: parseFloat(document.getElementById('simlAvRechazos')?.value || 0),
    };
    const data = await api(`/api/simulaciones/${id}/avance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (msg) { msg.textContent = '✓ Avance registrado'; msg.style.color = 'var(--grn)'; }
    renderAvanceResultado(data);
  } catch(e) {
    if (msg) { msg.textContent = '⚠ ' + e.message; msg.style.color = 'var(--red)'; }
  }
}

function renderAvanceResultado(data) {
  const el  = document.getElementById('simlAvanceResultado');
  if (!el) return;
  const sem = data.semaforos || {};
  const av  = data.avance   || {};
  const metricas = [['HL','dispersion_hl_pct'],['Bultos','dispersion_bultos_pct'],
    ['Pallets','dispersion_pallets_pct'],['PDV','dispersion_pdv_pct'],
    ['Salidas','dispersion_salidas_pct'],['Camiones','dispersion_camiones_pct'],['Personas','dispersion_personas_pct']];
  el.innerHTML = `<div class="box">
    <div class="sec" style="margin-bottom:10px">Avance al día ${av.dias_transcurridos} (${(Number(av.avance_esperado||0)*100).toFixed(0)}% del mes)</div>
    <table class="rtbl">
      <thead><tr><th>Métrica</th><th>Dispersión vs plan</th><th>Semáforo</th></tr></thead>
      <tbody>${metricas.map(([lbl, key]) => {
        const d = av[key];
        const sc = sem[key] || 'verde';
        const col = sc === 'verde' ? 'var(--grn)' : (sc === 'amarillo' ? 'var(--acc)' : 'var(--red)');
        return `<tr><td>${lbl}</td><td style="text-align:right;color:${col}">${d != null ? (d > 0 ? '+' : '') + Number(d).toFixed(1) + '%' : '—'}</td><td style="text-align:center"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${col}"></span></td></tr>`;
      }).join('')}</tbody>
    </table>
  </div>`;
}

async function cerrarSimulacion() {
  const msg = document.getElementById('simlCierreMsg');
  const id  = parseInt(document.getElementById('simlCierreId')?.value || 0);
  if (!id) { if (msg) { msg.textContent = 'Seleccioná una simulación'; msg.style.color = 'var(--red)'; } return; }
  if (!confirm('¿Cerrar esta simulación? Se guardará el aprendizaje para mejorar futuras simulaciones.')) return;
  if (msg) { msg.textContent = 'Cerrando…'; msg.style.color = 'var(--muted)'; }
  try {
    const payload = {
      hl_real:         parseFloat(document.getElementById('simlCiHl')?.value          || 0),
      bultos_real:     parseFloat(document.getElementById('simlCiBultos')?.value       || 0),
      pallets_real:    parseFloat(document.getElementById('simlCiPallets')?.value      || 0),
      pdv_real:        parseFloat(document.getElementById('simlCiPdv')?.value          || 0),
      salidas_real:    parseFloat(document.getElementById('simlCiSalidas')?.value      || 0),
      camiones_real:   parseFloat(document.getElementById('simlCiCamiones')?.value     || 0),
      personas_real:   parseFloat(document.getElementById('simlCiPersonas')?.value     || 0),
      rechazos_real:   parseFloat(document.getElementById('simlCiRechazos')?.value     || 0),
      dias_pico_real:  parseInt(document.getElementById('simlCiDiasPico')?.value       || 0),
      ausentismo_real: parseFloat(document.getElementById('simlCiAusentismo')?.value   || 0),
      up_real:         0,
      conclusiones:    document.getElementById('simlCiConclusiones')?.value            || '',
    };
    const data = await api(`/api/simulaciones/${id}/cerrar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (msg) { msg.textContent = '✓ Mes cerrado y aprendizaje guardado'; msg.style.color = 'var(--grn)'; }
    renderCierreResultado(data);
  } catch(e) {
    if (msg) { msg.textContent = '⚠ ' + e.message; msg.style.color = 'var(--red)'; }
  }
}

function renderCierreResultado(data) {
  const el = document.getElementById('simlCierreResultado');
  if (!el) return;
  const c  = data.cierre      || {};
  const ap = data.aprendizaje || {};
  const n1 = v => v != null ? (Number(v) > 0 ? '+' : '') + Number(v).toFixed(1) + '%' : '—';
  const col= v => { const a = Math.abs(Number(v||0)); return a <= 5 ? 'var(--grn)' : a <= 10 ? 'var(--acc)' : 'var(--red)'; };
  el.innerHTML = `<div class="box">
    <div class="sec" style="margin-bottom:10px;color:var(--grn)">✔ Simulación cerrada</div>
    <table class="rtbl">
      <thead><tr><th>Métrica</th><th>Error vs plan</th></tr></thead>
      <tbody>${[['HL','error_hl_pct'],['Bultos','error_bultos_pct'],['PDV','error_pdv_pct'],
         ['Salidas','error_salidas_pct'],['Camiones','error_camiones_pct'],['Personas','error_personas_pct']]
        .map(([lbl, k]) => `<tr><td>${lbl}</td><td style="text-align:right;color:${col(c[k])}">${n1(c[k])}</td></tr>`).join('')}
      </tbody>
    </table>
    <div style="margin-top:10px;padding:8px;background:var(--surf3);border-radius:6px;font-size:11px;color:var(--muted)">
      Factores guardados — Camiones ×${Number(ap.factor_ajuste_camiones||1).toFixed(3)} |
      Personas ×${Number(ap.factor_ajuste_personas||1).toFixed(3)} |
      Salidas ×${Number(ap.factor_ajuste_salidas||1).toFixed(3)}
    </div>
  </div>`;
}
// ── Simular todas las sucursales + general ──────────────────────────────

async function simularTodasYGuardar() {
  const msg = document.getElementById('simlMsg');
  const btn = document.getElementById('simlBtnTodas');
  const baseParams = _simlParams();
  const sucSeleccionada = baseParams.sucursal_id;

  // Determinar qué sucursales guardar
  // Si ya eligió una específica: guardar esa + TODAS
  // Si eligió TODAS: guardar solo la general
  const targets = [];

  if (sucSeleccionada !== 'TODAS') {
    targets.push({ sucursal_id: sucSeleccionada, label: sucSeleccionada });
  }
  targets.push({ sucursal_id: 'TODAS', label: 'General (TODAS)' });

  if (!confirm(`¿Guardar simulación para:\n${targets.map(t => '• ' + t.label).join('\n')}\n\nPara ${MESES[baseParams.mes - 1]} ${baseParams.anio}?`)) return;

  if (btn) btn.disabled = true;
  if (msg) { msg.textContent = `Guardando (0/${targets.length})…`; msg.style.color = 'var(--muted)'; }

  const resultados = [];
  let errores = 0;

  for (let i = 0; i < targets.length; i++) {
    const t = targets[i];
    if (msg) msg.textContent = `Guardando ${t.label} (${i + 1}/${targets.length})…`;
    try {
      const params = { ...baseParams, sucursal_id: t.sucursal_id };
      const data = await api('/api/simulaciones/guardar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });
      resultados.push({ label: t.label, id: data.id, riesgo: data.riesgo?.nivel || '—', ok: true });
    } catch(e) {
      resultados.push({ label: t.label, error: e.message, ok: false });
      errores++;
    }
  }

  if (btn) btn.disabled = false;

  const resumen = resultados.map(r =>
    r.ok ? `✓ ${r.label} — ID #${r.id} (riesgo: ${r.riesgo})` : `✗ ${r.label} — ${r.error}`
  ).join('\n');

  if (errores === 0) {
    if (msg) { msg.textContent = `✓ ${resultados.length} simulaciones guardadas`; msg.style.color = 'var(--grn)'; }
  } else {
    if (msg) { msg.textContent = `${resultados.length - errores}/${resultados.length} guardadas (${errores} errores)`; msg.style.color = 'var(--acc)'; }
  }

  // Mostrar detalle
  const res = document.getElementById('simlResultado');
  if (res) {
    res.innerHTML = `<div class="box">
      <div class="sec" style="margin-bottom:10px">Resumen de guardado</div>
      <table class="rtbl">
        <thead><tr><th>Sucursal</th><th>ID</th><th>Riesgo</th><th>Estado</th></tr></thead>
        <tbody>
          ${resultados.map(r => `<tr>
            <td style="font-weight:${r.label.includes('TODAS')?'600':'400'}">${esc(r.label)}</td>
            <td>${r.ok ? '#' + r.id : '—'}</td>
            <td>${r.riesgo || '—'}</td>
            <td style="color:${r.ok?'var(--grn)':'var(--red)'}">${r.ok ? '✓ OK' : '✗ ' + esc(r.error||'')}</td>
          </tr>`).join('')}
        </tbody>
      </table>
      <div style="margin-top:10px;font-size:11px;color:var(--muted)">Podés ver el comparativo en la pestaña <strong>Guardadas</strong>.</div>
    </div>`;
  }
}
// ── Cargar sugerencias desde el sistema ──────────────────────────────────────

async function cargarSugerencias() {
  const btn   = document.getElementById('simlBtnSugerir');
  const msgEl = document.getElementById('simlSugerenciasMsg');
  const anio  = parseInt(document.getElementById('simlAnio')?.value || 0);
  const mes   = parseInt(document.getElementById('simlMes')?.value  || 0);
  const suc   = document.getElementById('simlSucursal')?.value || 'TODAS';

  if (!anio || !mes) {
    if (msgEl) { msgEl.textContent = 'Seleccioná año y mes primero'; msgEl.style.color = 'var(--red)'; }
    return;
  }

  if (btn) btn.disabled = true;
  if (msgEl) { msgEl.textContent = 'Consultando el sistema…'; msgEl.style.color = 'var(--muted)'; }

  ['simlFuenteDias','simlFuenteDiasPico','simlFuenteCrec','simlFuenteCamiones'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.style.display = 'none'; el.textContent = ''; }
  });

  try {
    const qs   = `empresa_id=1&sucursal_id=${encodeURIComponent(suc)}&anio=${anio}&mes=${mes}`;
    const data = await api(`/api/simulaciones/sugerir?${qs}`);
    const sug  = data.sugerencias || {};
    const ftes = data.fuentes     || {};
    let aplicados = 0;

    function _set(inputId, fuenteId, key, syncSliderId) {
      if (sug[key] == null) return;
      const inp = document.getElementById(inputId);
      if (inp) { inp.value = sug[key]; aplicados++; }
      if (syncSliderId) {
        const sl = document.getElementById(syncSliderId);
        if (sl) sl.value = sug[key];
      }
      const fEl = document.getElementById(fuenteId);
      if (fEl && ftes[key]) {
        fEl.textContent = '↑ ' + ftes[key];
        fEl.style.display = 'block';
      }
    }

    _set('simlDias',     'simlFuenteDias',     'dias_trabajados');
    _set('simlDiasPico', 'simlFuenteDiasPico', 'dias_pico_esperados');
    _set('simlCrecVal',  'simlFuenteCrec',     'crecimiento_esperado', 'simlCrecSlider');
    _set('simlCamiones', 'simlFuenteCamiones', 'camiones_disponibles');

    if (aplicados > 0) {
      if (msgEl) {
        msgEl.textContent = `✓ ${aplicados} campo${aplicados > 1 ? 's' : ''} cargado${aplicados > 1 ? 's' : ''} automáticamente`;
        msgEl.style.color = 'var(--blu)';
      }
    } else {
      if (msgEl) { msgEl.textContent = 'Sin datos históricos disponibles para este período'; msgEl.style.color = 'var(--muted)'; }
    }
  } catch(e) {
    if (msgEl) { msgEl.textContent = '⚠ ' + e.message; msgEl.style.color = 'var(--red)'; }
  } finally {
    if (btn) btn.disabled = false;
  }
}
async function syncPlanillaOperativa() {
  const btn   = document.getElementById('simlBtnSync');
  const msgEl = document.getElementById('simlSyncMsg');
  if (btn) btn.disabled = true;
  if (msgEl) { msgEl.textContent = 'Sincronizando desde Google Sheets…'; msgEl.style.color = 'var(--muted)'; }
  try {
    const resp = await fetch(API + '/api/sync/sheets-operativo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ empresa_id: '1' }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);
    const n    = data.insertados ?? 0;
    const errs = data.errores ?? [];
    const det  = data.detalle ?? [];
    // Línea de resumen
    let txt = `✓ ${n} registros procesados`;
    if (errs.length) txt += ` · ${errs.length} error${errs.length > 1 ? 'es' : ''}`;
    if (msgEl) { msgEl.textContent = txt; msgEl.style.color = errs.length ? 'var(--acc)' : 'var(--grn)'; }
    // Detalle en consola para diagnóstico
    console.table(det.map(d => ({tab: d.url_tag, csv: d.filas_csv, parseadas: d.filas_parseadas, ok: d.upsertados, error: d.error||''})));
    if (errs.length) console.warn('Sync errores:', errs);
  } catch(e) {
    if (msgEl) { msgEl.textContent = '⚠ ' + e.message; msgEl.style.color = 'var(--red)'; }
  } finally {
    if (btn) btn.disabled = false;
  }
}
// ─── FIN SIMULADOR LOGÍSTICO ─────────────────────────────────────────────
