/* Mapa de rutas de entrega — consulta clientes, días importados y ventas */
(() => {
const DAYS = ['LU','MA','MI','JU','VI','SA'];
const DAYNAME = {LU:'Lunes',MA:'Martes',MI:'Miércoles',JU:'Jueves',VI:'Viernes',SA:'Sábado'};
const DAYSHORT = {LU:'Lun',MA:'Mar',MI:'Mié',JU:'Jue',VI:'Vie',SA:'Sáb'};
const PCOL = {LUJU:'#2f6fde',MAVI:'#159a62',MISA:'#8a4fd0',MAJU:'#0e97ad',MASA:'#c2559b',LU:'#86a9ec',JU:'#86a9ec',MA:'#74c7a1',VI:'#74c7a1',MI:'#b89be6',SA:'#b89be6'};
// Paleta categórica para localidades: localidades vecinas nunca comparten color.
const LOC_PAL = ['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2','#c026d3','#65a30d','#b45309','#0f766e','#db2777','#4f46e5'];
const VER = {loc:'Localidad', dias:'Días', vol:'Volumen', estado:'Estado', venta:'Venta $'};
// Volumen: bultos por semana en 5 escalones (quintiles de los clientes con compras).
const VOL_PAL = ['#c6dcf2','#8bbbe6','#4b93d4','#2166ad','#123d75'];
let VOL_Q = [];
const volNivel = c => { const v = venta(c); if (!v || !v.bultos) return -1; let i = 0; while (i < VOL_Q.length && v.bultos_sem > VOL_Q[i]) i++; return i; };
const num = (n, d = 0) => Number(n || 0).toLocaleString('es-AR', {maximumFractionDigits: d});
const PERIODOS = [30, 60, 90];
const API = window.RUTAS.api;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
const tok = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

const S = {suc:'TODAS', day:'TODOS', q:'', flt:null, sel:null, D:null, ver:'loc', V:null, zonas:true, ctx:true, foco:null, periodo:60};
const ESTADO = {activo:'Activo', riesgo:'En riesgo', inactivo:'Inactivo', sin_compras:'Sin compras'};
const ABC_COL = {A:'#2f6fde', B:'#0e97ad', C:'#86a9ec', '-':'#9a9f9b'};
const venta = c => S.V && S.V.clientes[c.id];
const estadoDe = c => venta(c)?.estado || 'sin_compras';
const money = n => '$ ' + Math.round(n || 0).toLocaleString('es-AR');

// Preferencias del usuario (solo en este navegador)
const PREF = 'rutas.mapa.v1';
try {
  const p = JSON.parse(localStorage.getItem(PREF) || '{}');
  if (p.day === 'TODOS' || DAYS.includes(p.day)) S.day = p.day;
  if (VER[p.ver]) S.ver = p.ver;
  if (typeof p.suc === 'string') S.suc = p.suc;
  if (typeof p.zonas === 'boolean') S.zonas = p.zonas;
  if (typeof p.ctx === 'boolean') S.ctx = p.ctx;
  if ([30, 60, 90].includes(p.periodo)) S.periodo = p.periodo;
} catch {}
function savePrefs(){ try { localStorage.setItem(PREF, JSON.stringify({suc:S.suc, day:S.day, ver:S.ver, zonas:S.zonas, ctx:S.ctx, periodo:S.periodo})); } catch {} }

let byId = new Map();
let mapPositioned = false;
const isGeo = c => c.lat != null && c.lng != null;
const sinDias = c => !c.d;
const FLT = {
  sindias: sinDias, singeo: c => !isGeo(c), far: c => c.far, anulado: c => c.an && c.d,
  fuera: c => !c.pl && !c.an, cambia: c => !c.an && c.d !== c.de, pend: c => c.pend && !c.an,
};
const FLT_LABEL = {sindias:'sin días de entrega', singeo:'sin geolocalizar', far:'ubicación a revisar',
  anulado:'inactivos con días asignados', cambia:'días distintos al ERP', pend:'pendientes de subir a BEES',
  riesgo:'en riesgo de dejar de comprar', inactivo:'sin comprar hace más de 45 días', sin_compras:'sin compras en el período'};
for (const e of ['riesgo','inactivo','sin_compras']) FLT[e] = c => !c.an && estadoDe(c) === e;

function toast(msg, err){ const t=document.createElement('div'); t.className='toast'+(err?' err':''); t.setAttribute('role', err?'alert':'status'); t.textContent=msg;
  document.body.appendChild(t); setTimeout(()=>t.remove(), 3500); }

async function api(path, opts={}) {
  const r = await fetch(API + path, {headers:{'Content-Type':'application/json'}, credentials:'same-origin', ...opts});
  const j = await r.json().catch(()=>({}));
  if (r.status === 401) throw new Error('La sesión venció. Ingresá nuevamente al portal.');
  if (!r.ok) throw new Error(j.error || ('Error ' + r.status));
  return j;
}

// ---------- colores por localidad ----------
let locColor = new Map();
function asignarColores(clientes) {
  const acc = new Map();
  for (const c of clientes) {
    if (!isGeo(c) || c.far) continue;
    const p = acc.get(c.loc) || {loc:c.loc, lat:0, lng:0, n:0};
    p.lat += c.lat; p.lng += c.lng; p.n++; acc.set(c.loc, p);
  }
  const locs = [...acc.values()].map(p => ({loc:p.loc, lat:p.lat/p.n, lng:p.lng/p.n, n:p.n}))
    .sort((a,b) => b.n - a.n || a.loc.localeCompare(b.loc));
  const km = (a,b) => Math.hypot((a.lat-b.lat)*111, (a.lng-b.lng)*111*Math.cos(a.lat*Math.PI/180));
  // Cada localidad toma el color cuyo uso más cercano está más lejos: primero agota la
  // paleta y, si hay más localidades que colores, repite lo más lejos posible.
  locColor = new Map();
  for (const l of locs) {
    let mejor = LOC_PAL[0], lejos = -1;
    for (const col of LOC_PAL) {
      const d = Math.min(Infinity, ...locs.filter(o => locColor.get(o.loc) === col).map(o => km(l, o)));
      if (d > lejos) { mejor = col; lejos = d; }
    }
    locColor.set(l.loc, mejor);
  }
  for (const c of clientes) if (!locColor.has(c.loc)) locColor.set(c.loc, LOC_PAL[locColor.size % LOC_PAL.length]);
}
const colorLoc = loc => locColor.get(loc) || '#8d8a5c';

// ---------- mapa ----------
const map = L.map('map', {preferCanvas:true, zoomSnap:.25}).fitBounds([[-37.1,-58.6],[-35.3,-56.8]]);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19,
  attribution:'&copy; OpenStreetMap'}).addTo(map);
map.createPane('zonas').style.zIndex = 350;
const zonaLayer = L.layerGroup().addTo(map);
const ctxLayer = L.layerGroup().addTo(map);
const ptLayer = L.layerGroup().addTo(map);
const tagLayer = L.layerGroup().addTo(map);

const loading = document.createElement('div');
loading.className = 'map-loading'; loading.innerHTML = '<span class="spinner"></span>Cargando clientes…';
$('map').appendChild(loading);

function visible(){return RutasVista.filtrar(S.D.clientes,S,c=>!S.flt||FLT[S.flt](c))}
let viewData=null;
function centrarSeleccion(){const points=visible().filter(c=>isGeo(c)&&!c.far);if(points.length)map.fitBounds(points.map(c=>[c.lat,c.lng]),{padding:[50,50],maxZoom:15})}
function zoomLoc(loc){
  const pts=visible().filter(c=>c.loc===loc&&isGeo(c)&&!c.far);
  if(!pts.length){toast(`${loc}: sin clientes geolocalizados en la vista.`,true);return}
  map.fitBounds(pts.map(c=>[c.lat,c.lng]),{padding:[50,50],maxZoom:15});
  S.foco=loc; drawZonas(visible());
  clearTimeout(zoomLoc.t); zoomLoc.t=setTimeout(()=>{S.foco=null;if(S.D)drawZonas(visible())},2500);
}

function colorDe(c, sd) {
  if (S.ver === 'estado' && S.V) return {activo:tok('--ok'), riesgo:tok('--warn'), inactivo:tok('--bad'), sin_compras:'#9a9f9b'}[estadoDe(c)];
  if (S.ver === 'venta' && S.V) return ABC_COL[venta(c)?.abc || '-'];
  if (S.ver === 'vol' && S.V) { const n = volNivel(c); return n < 0 ? '#9a9f9b' : VOL_PAL[n]; }
  if (c.an) return '#9a9f9b';
  if (S.ver !== 'dias') return colorLoc(c.loc);   // también Estado/Venta sin ventas cargadas
  return sd ? tok('--bad') : (PCOL[c.d] || '#8d8a5c');
}
function drawPoints(list) {
  ptLayer.clearLayers(); ctxLayer.clearLayers();
  if (S.sel && !list.some(c => c.id === S.sel)) { S.sel=null; renderCard(); }
  // Contexto: con un día elegido, el resto de los clientes queda atenuado.
  if (S.ctx && S.day !== 'TODOS') {
    const ids = new Set(list.map(c => c.id));
    RutasVista.filtrar(S.D.clientes, {suc:S.suc, day:'TODOS', q:S.q}).forEach(c => {
      if (!isGeo(c) || ids.has(c.id) || c.an) return;
      ctxLayer.addLayer(L.circleMarker([c.lat,c.lng], {radius:3, weight:0, fillColor:'#7a817c', fillOpacity:.28, interactive:false}));
    });
  }
  list.forEach(c => {
    if (!isGeo(c)) return;
    const sd = sinDias(c), sel = S.sel === c.id;
    const borde = sel ? tok('--ink') : c.far ? tok('--warn') : (S.ver === 'loc' && sd && !c.an) ? tok('--bad') : 'rgba(0,0,0,.45)';
    const rad = S.ver === 'vol' && S.V ? 3.5 + 1.6 * Math.max(0, volNivel(c)) : (sd?6:5);
    const m = L.circleMarker([c.lat,c.lng], {radius: sel?9:rad, weight: sel?3:(c.far||(S.ver==='loc'&&sd)?2.5:1),
      color: borde, fillColor: colorDe(c, sd), fillOpacity: c.an?.5:.92});
    const v = venta(c), vt = S.V ? `<br>${ESTADO[estadoDe(c)]}${v?` · ${num(v.compras)} compras · ${num(v.bultos_sem,1)} bultos/sem`:''}` : '';
    m.bindTooltip(`<b>${c.id}</b> ${esc(c.n)}<br><i class="sw" style="background:${colorLoc(c.loc)}"></i>${esc(c.loc)} · ${c.d || 'sin días'}${c.an?' · inactivo':''}${vt}`);
    m.on('click', () => select(c.id));
    ptLayer.addLayer(m);
  });
  drawZonas(list);
}

// Envolvente convexa (monotone chain) de [lat,lng], ampliada ~400 m para que los puntos queden adentro.
function hull(pts) {
  const p = [...new Map(pts.map(x => [x.join(), x])).values()].sort((a,b) => a[1]-b[1] || a[0]-b[0]);
  if (p.length < 3) return p;
  const cross = (o,a,b) => (a[1]-o[1])*(b[0]-o[0]) - (a[0]-o[0])*(b[1]-o[1]);
  const lo = [], up = [];
  for (const x of p) { while (lo.length >= 2 && cross(lo.at(-2), lo.at(-1), x) <= 0) lo.pop(); lo.push(x); }
  for (const x of [...p].reverse()) { while (up.length >= 2 && cross(up.at(-2), up.at(-1), x) <= 0) up.pop(); up.push(x); }
  const h = lo.slice(0,-1).concat(up.slice(0,-1));
  const cy = h.reduce((t,x) => t+x[0], 0)/h.length, cx = h.reduce((t,x) => t+x[1], 0)/h.length;
  return h.map(([y,x]) => { const d = Math.hypot(y-cy, x-cx) || 1e-9, k = (d + .004)/d; return [cy + (y-cy)*k, cx + (x-cx)*k]; });
}
function drawZonas(list) {
  zonaLayer.clearLayers(); tagLayer.clearLayers();
  const g = new Map();
  for (const c of list) {
    if (c.an) continue;
    const x = g.get(c.loc) || {loc:c.loc, n:0, pts:[], carga:0};
    x.n++; x.carga += venta(c)?.drop || 0; if (isGeo(c) && !c.far) x.pts.push([c.lat, c.lng]); g.set(c.loc, x);
  }
  const zonas = S.zonas && S.day !== 'TODOS', carga = !!S.V && S.day !== 'TODOS';
  for (const x of g.values()) {
    if (!x.pts.length) continue;
    const col = colorLoc(x.loc), foco = S.foco === x.loc;
    if (zonas || foco) {
      const h = hull(x.pts), style = {pane:'zonas', color:col, weight:foco?3.5:2, opacity:.95, fillColor:col,
        fillOpacity:foco?.28:.13, dashArray:foco?null:'6 5', interactive:false};
      if (h.length >= 3) zonaLayer.addLayer(L.polygon(h, style));
      else {
        const lat = x.pts.reduce((t,p)=>t+p[0],0)/x.pts.length, lng = x.pts.reduce((t,p)=>t+p[1],0)/x.pts.length;
        const r = Math.max(450, ...x.pts.map(p => map.distance([lat,lng], p) + 350));
        zonaLayer.addLayer(L.circle([lat,lng], {...style, radius:r}));
      }
    }
    const norte = Math.max(...x.pts.map(p => p[0])), lng = x.pts.reduce((t,p)=>t+p[1],0)/x.pts.length;
    const m = L.marker([norte + .0035, lng], {keyboard:false, riseOnHover:true, icon:L.divIcon({className:'loc-tag-wrap', iconSize:null,
      html:`<span class="loc-tag${foco?' foco':''}" style="--c:${col}" title="Acercar a ${esc(x.loc)}${carga?' · carga estimada: promedio de bultos por entrega de sus clientes':''}">${esc(x.loc)}<b>${x.n}</b>${carga?`<em>~${num(x.carga)} b</em>`:''}</span>`})});
    m.on('click', () => zoomLoc(x.loc));
    tagLayer.addLayer(m);
  }
}

// ---------- controles sobre el mapa ----------
const Tools = L.Control.extend({options:{position:'topright'}, onAdd(){
  const d = L.DomUtil.create('div', 'map-tools');
  d.innerHTML = `<button type="button" data-t="centrar" title="Encuadrar los clientes de la vista">Centrar</button>
    <button type="button" data-t="zonas" title="Sombrear la zona de cada localidad con entregas el día elegido">Zonas</button>
    <button type="button" data-t="ctx" title="Mostrar atenuados los clientes de otros días">Otros días</button>`;
  L.DomEvent.disableClickPropagation(d);
  d.querySelectorAll('button').forEach(b => b.onclick = () => {
    if (b.dataset.t === 'centrar') return centrarSeleccion();
    S[b.dataset.t] = !S[b.dataset.t]; savePrefs(); renderTools(); drawPoints(visible());
  });
  return d;
}});
const tools = new Tools().addTo(map);
function renderTools(){
  const el = tools.getContainer(), dia = S.day !== 'TODOS';
  for (const k of ['zonas','ctx']) { const b = el.querySelector(`[data-t="${k}"]`); b.setAttribute('aria-pressed', S[k]); b.disabled = !dia; }
  el.querySelector('[data-t="zonas"]').title = dia ? 'Sombrear la zona de cada localidad con entregas el día elegido' : 'Elegí un día para ver las zonas';
}

const Legend = L.Control.extend({options:{position:'bottomright'}, onAdd(){
  const d = L.DomUtil.create('div', 'map-legend');
  L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d);
  return d;
}});
const legend = new Legend().addTo(map);
let legendOpen = true;
function renderLegend(list) {
  const el = legend.getContainer(); let body = '';
  if (S.ver === 'loc') {
    const n = new Map(); list.forEach(c => { if (!c.an) n.set(c.loc, (n.get(c.loc)||0) + 1); });
    body = [...n].sort((a,b) => b[1]-a[1]).map(([loc,k]) =>
      `<button type="button" class="lg-loc" data-loc="${esc(loc)}"><i class="sw" style="background:${colorLoc(loc)}"></i><span>${esc(loc)}</span><b>${k}</b></button>`).join('')
      || '<p class="note">Sin clientes en la vista.</p>';
  } else if (S.ver === 'dias') {
    body = ['LUJU','MAVI','MISA','MAJU','MASA'].map(p => `<span><i class="sw" style="background:${PCOL[p]}"></i>${p}</span>`).join('')
      + `<span><i class="sw" style="background:#86a9ec"></i>Un solo día</span><span><i class="sw" style="background:var(--bad)"></i>Sin días</span>`;
  } else if (!S.V) {
    body = '<p class="note">No hay ventas cargadas.</p>';
  } else if (S.ver === 'vol') {
    const r = [0, ...VOL_Q];
    body = VOL_PAL.map((col, i) => `<span><i class="sw" style="background:${col}"></i>${i < VOL_Q.length ? `${num(r[i],1)}–${num(VOL_Q[i],1)}` : `más de ${num(r[i],1)}`} bultos/sem</span>`).join('')
      + '<span><i class="sw" style="background:#9a9f9b"></i>Sin compras</span><p class="note">El tamaño del punto también crece con el volumen.</p>';
  } else if (S.ver === 'estado') {
    body = [['--ok','Activo'],['--warn','En riesgo'],['--bad','Inactivo']].map(([v,l]) => `<span><i class="sw" style="background:var(${v})"></i>${l}</span>`).join('')
      + '<span><i class="sw" style="background:#9a9f9b"></i>Sin compras</span>';
  } else {
    body = [['A','A · 80% de la venta'],['B','B · siguiente 15%'],['C','C · último 5%'],['-','Sin venta']].map(([k,l]) => `<span><i class="sw" style="background:${ABC_COL[k]}"></i>${l}</span>`).join('');
  }
  const extra = `<span><i class="sw" style="background:#9a9f9b"></i>Inactivo en el maestro</span><span><i class="sw ring"></i>Ubicación a revisar</span>`;
  el.innerHTML = `<details ${legendOpen?'open':''}><summary>Color: ${VER[S.ver]}</summary><div class="lg-body ${S.ver==='loc'?'lg-scroll':''}">${body}</div>${S.ver==='loc'?'':`<div class="lg-body">${extra}</div>`}</details>`;
  el.querySelector('details').ontoggle = e => { legendOpen = e.target.open; };
  el.querySelectorAll('[data-loc]').forEach(b => b.onclick = () => zoomLoc(b.dataset.loc));
}

// ---------- paneles ----------
function scope(){return visible()}
function renderLoc() {
  const sc = scope(), k = f => sc.filter(FLT[f]).length;
  const kp = [['',sc.length,'clientes filtrados',null],['',sc.filter(isGeo).length,'geolocalizados',null],
    ['bad',k('sindias'),'sin días de entrega','sindias'],['bad',k('singeo'),'sin geolocalizar','singeo'],
    ['warn',k('far'),'ubicación a revisar','far'],['warn',k('anulado'),'inactivos con días asignados','anulado']];
  const rows=viewData.por_localidad;
  const days=S.day==='TODOS'?DAYS:[S.day];
  let html = '', last = '';
  rows.forEach(r => { if (r.suc !== last) { html += `<tr class="suc"><td colspan="${4+days.length}">Sale de ${esc(r.suc)}</td></tr>`; last = r.suc; }
    html += `<tr data-loc="${esc(r.loc)}" tabindex="0"><td><i class="sw" style="background:${colorLoc(r.loc)}"></i>${esc(r.loc)}</td><td>${r.clientes}</td><td class="${r.sin_geo?'bad':''}">${r.sin_geo||'·'}</td><td class="${r.sin_dias?'bad':''}">${r.sin_dias||'·'}</td>${days.map(d=>`<td class="${r[d]?'':'z'}">${r[d]||'·'}</td>`).join('')}</tr>`; });
  $('p-loc').innerHTML = `
   <div class="kpis">${kp.map(([c,n,l,f])=>`<button class="kpi ${c}" ${f?`data-f="${f}" aria-pressed="${S.flt===f}"`:'disabled style="cursor:default"'}><b>${n}</b><span>${l}</span></button>`).join('')}</div>
   ${S.flt?`<p class="note">Filtro aplicado: <b>${FLT_LABEL[S.flt]||S.flt}</b> · <a href="#" id="clrF">quitar</a></p>`:''}
   <div><h2>${S.day==='TODOS'?'Clientes por localidad y día':'Localidades con entrega el '+DAYNAME[S.day].toLowerCase()}</h2></div>
   ${rows.length?`<div class="tw"><table><thead><tr><th>Localidad</th><th>Clientes</th><th title="Sin geolocalizar">S/geo</th><th title="Sin días">S/día</th>${days.map(d=>`<th>${d}</th>`).join('')}</tr></thead><tbody>${html}</tbody></table></div>
   <p class="note">Tocá una localidad para acercar el mapa y resaltar su zona.</p>`:'<p class="empty">No hay clientes para los filtros elegidos.</p>'}`;
  $('p-loc').querySelectorAll('[data-f]').forEach(b => b.onclick = () => { S.flt = S.flt===b.dataset.f ? null : b.dataset.f; render(); });
  const cf = $('clrF'); if (cf) cf.onclick = e => { e.preventDefault(); S.flt = null; render(); };
  $('p-loc').querySelectorAll('tr[data-loc]').forEach(tr => { tr.onclick = () => zoomLoc(tr.dataset.loc);
    tr.onkeydown = e => { if (e.key === 'Enter') zoomLoc(tr.dataset.loc); }; });
}
function renderDia() {
  const days = S.day==='TODOS' ? DAYS : [S.day];
  $('p-dia').innerHTML = days.map(d => {
    const clients=scope().filter(c=>c.d.includes(d));
    return `<h2>${DAYNAME[d]} · ${clients.length} clientes</h2><div class="list">${clients.map(c=>itemHTML(c,`<span class="pill">${esc(c.suc)}</span>`)).join('')||'<p class="note">No hay clientes para los filtros seleccionados.</p>'}</div>`;
  }).join('');
  bindItems($('p-dia'));
}
function itemHTML(c, tag) { return `<div class="item" data-id="${c.id}" tabindex="0"><span class="id">${c.id}</span><span class="nm">${esc(c.n)}</span>${tag}<span class="sub"><i class="sw" style="background:${colorLoc(c.loc)}"></i>${esc(c.loc)} · ${esc(c.dom)||'sin domicilio'}${c.ven?' · '+esc(c.ven):''}</span></div>`; }
function bindItems(el) { el.querySelectorAll('.item').forEach(x => { x.onclick = () => select(+x.dataset.id, true);
  x.onkeydown = e => { if (e.key === 'Enter') select(+x.dataset.id, true); }; }); }
function renderPen() {
  const sc = scope(), sd = sc.filter(sinDias), sg = sc.filter(FLT.singeo), fr = sc.filter(FLT.far), an = sc.filter(FLT.anulado);
  $('penN').textContent = (sd.length + sg.length) || '';
  const sec = (t,list,tag,note) => `<div><h2>${t} · ${list.length}</h2>${note?`<p class="note">${note}</p>`:''}</div><div class="list">${list.map(c=>itemHTML(c,tag(c))).join('') || '<p class="note">Nada pendiente.</p>'}</div>`;
  $('p-pen').innerHTML =
    sec('Sin días de entrega', sd, c => c.pl ? '<span class="pill bad">sin días</span>' : '<span class="pill warn">no estaba en planilla</span>', 'Clientes filtrados sin días asignados.') +
    sec('Sin geolocalizar', sg, () => '<span class="pill bad">sin coord.</span>', 'Clientes sin coordenadas disponibles.') +
    sec('Ubicación a revisar', fr, () => '<span class="pill warn">lejos</span>', 'Coordenada fuera de la provincia o a más de 15 km del centro de su localidad.') +
    sec('Inactivos con días asignados', an, c => `<span class="pill">${c.d}</span>`, 'Revisá si corresponde quitarles los días de entrega.');
  bindItems($('p-pen'));
}
function renderExp(){
  $('p-exp').innerHTML=`<h2>Rutas de entrega · Solo consulta</h2><p>${scope().length} clientes · ${S.day==='TODOS'?'Semana':DAYNAME[S.day]} · ${esc(S.suc==='TODAS'?'Todas las sucursales':S.suc)}</p>
   <p class="note">Al elegir un día, cada localidad con entregas se sombrea con su color y muestra cuántos clientes tiene. Tocá la etiqueta para acercarte.</p>
   <p class="note">Los días provienen del archivo importado: un 1 en LUNES a SÁBADO indica visita ese día. Las columnas de BEES no se usan.</p>
   <h2>Atajos de teclado</h2><dl class="kv"><dt><kbd>0</kbd>–<kbd>6</kbd></dt><dd>Semana, lunes a sábado</dd><dt><kbd>/</kbd></dt><dd>Buscar cliente</dd><dt><kbd>Esc</kbd></dt><dd>Cerrar la ficha</dd></dl>
   <p class="status">${S.D.ultima_sync?'Última actualización: '+esc(S.D.ultima_sync.origen)+' · '+esc((S.D.ultima_sync.fin||'').replace('T',' ').slice(0,16)):'Sin actualización registrada.'}</p>`;
}
function renderVen() {
  const el = $('p-ven');
  if (!S.V) { el.innerHTML = '<h2>Ventas</h2><p class="empty">No hay ventas importadas en el período. Se cargan desde Importaciones de datos → Ventas detalle.</p>'; return; }
  const act = scope().filter(c => !c.an), cnt = e => act.filter(c => estadoDe(c) === e).length;
  const tot = k => act.reduce((t, c) => t + (venta(c)?.[k] || 0), 0);
  const kp = [['',cnt('activo'),'activos',null],['warn',cnt('riesgo'),'en riesgo','riesgo'],
    ['bad',cnt('inactivo'),'inactivos (+45 días)','inactivo'],['',cnt('sin_compras'),'sin compras','sin_compras']];
  const lista = (e, n) => act.filter(c => estadoDe(c) === e).sort((a, b) => (venta(b)?.bultos || 0) - (venta(a)?.bultos || 0)).slice(0, n);
  const top = act.filter(venta).sort((a, b) => venta(b).bultos - venta(a).bultos).slice(0, 15);
  const tag = c => { const v = venta(c); return v ? `<span class="pill">${num(v.bultos_sem,1)} b/sem</span><span class="pill">${v.dias_sin} d</span>` : ''; };
  el.innerHTML = `<p class="status">Ventas importadas del ${esc(S.V.desde)} al ${esc(S.V.hasta)} (60 días) · sin remitos ni comodatos · volumen de mercadería</p>
   <div class="vtot"><div title="Una compra por cliente y día · ${num(tot('comprobantes'))} comprobantes"><b>${num(tot('compras'))}</b><span>compras</span></div><div><b>${num(tot('bultos'))}</b><span>bultos</span></div><div><b>${num(tot('hl'),1)}</b><span>HL</span></div><div><b>${money(tot('neto'))}</b><span>venta neta</span></div></div>
   <div class="kpis">${kp.map(([c,n,l,f])=>`<button class="kpi ${c}" ${f?`data-f="${f}" aria-pressed="${S.flt===f}"`:'disabled style="cursor:default"'}><b>${n}</b><span>${l}</span></button>`).join('')}</div>
   <p class="note">En riesgo: lleva más de 2,5 veces su frecuencia habitual sin comprar (mínimo 21 días). Inactivo: más de 45 días.</p>
   <h2>Mayor volumen</h2><div class="list">${top.map(c => itemHTML(c, `<span class="pill">${num(venta(c).bultos)} b</span>`)).join('') || '<p class="note">Sin datos.</p>'}</div>
   <h2>En riesgo · mayor volumen primero</h2><div class="list">${lista('riesgo', 40).map(c => itemHTML(c, tag(c))).join('') || '<p class="note">Ninguno.</p>'}</div>
   <h2>Inactivos · mayor volumen primero</h2><div class="list">${lista('inactivo', 40).map(c => itemHTML(c, tag(c))).join('') || '<p class="note">Ninguno.</p>'}</div>`;
  el.querySelectorAll('[data-f]').forEach(b => b.onclick = () => { S.flt = S.flt===b.dataset.f ? null : b.dataset.f; render(); });
  bindItems(el);
}

// ---------- ficha de consulta ----------
let card=null;
function select(id,fly){
  S.sel=id;const c=byId.get(id);if(!c)return;
  if(fly&&isGeo(c))map.flyTo([c.lat,c.lng],Math.max(map.getZoom(),15),{duration:.6});
  renderCard();drawPoints(visible());
}
function cerrarCard(){S.sel=null;renderCard();drawPoints(visible())}
function renderCard(){
  if(card)card.remove();card=null;if(!S.sel)return;
  const c=byId.get(S.sel);if(!c)return;
  card=document.createElement('div');card.className='card';card.setAttribute('role','dialog');card.setAttribute('aria-label','Ficha del cliente '+c.id);
  const gm=isGeo(c)?`https://www.google.com/maps?q=${c.lat},${c.lng}`:`https://www.google.com/maps/search/${encodeURIComponent(c.dom+', '+c.loc+', Buenos Aires')}`;
  card.innerHTML=`<button class="x" aria-label="Cerrar ficha (Esc)">×</button>
    <div class="card-head"><span class="mono">#${c.id}</span><span class="loc-chip" style="--c:${colorLoc(c.loc)}">${esc(c.loc)}</span>${c.an?'<span class="pill">Inactivo</span>':''}${c.far?'<span class="pill warn">Ubicación a revisar</span>':''}</div>
    <h3>${esc(c.n)}</h3>
    <div class="dchips" aria-label="Días de entrega">${DAYS.map(d=>`<span class="dchip${c.d.includes(d)?' on':''}" title="${DAYNAME[d]}">${d}</span>`).join('')}</div>
    <dl class="kv"><dt>Domicilio</dt><dd>${esc(c.dom)||'—'}, ${esc(c.loc)}</dd><dt>Sale de</dt><dd>${esc(c.suc)}</dd><dt>Horario</dt><dd>${esc(c.h)||'—'}</dd>${c.ven?`<dt>Vendedor</dt><dd>${esc(c.ven)}</dd>`:''}<dt>Nota</dt><dd>${esc(c.nota)||'—'}</dd></dl>
    <div class="row"><a class="btn" href="${gm}" target="_blank" rel="noopener">Ver en Google Maps</a><button class="btn" id="history">Historial</button></div><div id="clientHistory" role="status"></div>
    <section id="clientSales" class="pv" aria-live="polite"><p class="status">Consultando compras...</p></section>`;
  $('map').appendChild(card);L.DomEvent.disableClickPropagation(card);L.DomEvent.disableScrollPropagation(card);
  card.querySelector('.x').onclick=cerrarCard;
  cargarVentas(c, card.querySelector('#clientSales'));
  card.querySelector('#history').onclick=async()=>{
    const target=card.querySelector('#clientHistory');target.textContent='Consultando historial...';
    try{const rows=await api('/clientes/'+c.id+'/historial');target.innerHTML=rows.length?rows.map(r=>`<p><strong>${esc(r.campo)}</strong>: ${esc(r.antes??'—')} → ${esc(r.despues??'—')}<br><small>${esc(r.usuario||'Sin usuario')} · ${esc(r.fecha)}</small></p>`).join(''):'Sin cambios registrados.'}catch(e){target.textContent=e.message}
  };
}

async function cargarVentas(c, el) {
  const dias = PERIODOS.includes(S.periodo) ? S.periodo : 60;
  el.innerHTML = '<p class="status"><span class="spinner"></span> Consultando compras...</p>';
  let r;
  try { r = await api(`/clientes/${c.id}/ventas?dias=${dias}`); }
  catch (e) { if (el.isConnected) el.innerHTML = `<p class="status">No se pudieron consultar las compras: ${esc(e.message)}</p>`; return; }
  if (!el.isConnected) return;
  const selector = `<div class="seg seg-sm" role="group" aria-label="Período">${PERIODOS.map(p => `<button type="button" data-p="${p}" aria-pressed="${p===dias}">${p} d</button>`).join('')}</div>`;
  const head = `<div class="pv-head"><h2>Compras y volumen</h2>${selector}</div>`;
  const m = r.metricas;
  if (!m) {
    el.innerHTML = head + `<p class="empty">Sin compras entre el ${esc(r.desde || '—')} y el ${esc(r.hasta || '—')}.</p>`;
  } else {
    const ref = r.referencia, cls = {activo:'ok', riesgo:'warn', inactivo:'bad'}[m.estado] || '';
    const vsRef = ref && ref.drop ? Math.round((m.drop / ref.drop - 1) * 100) : null;
    const tend = m.tend == null ? null : Math.round(m.tend * 100);
    const asig = r.asignados || '', totEnt = Object.values(m.ent).reduce((a, b) => a + b, 0) || 1;
    const dias7 = [...DAYS, ...(m.ent.DO ? ['DO'] : [])];
    const barras = dias7.map(d => { const n = m.ent[d] || 0, pct = Math.round(n / totEnt * 100);
      return `<div class="wd${asig.includes(d)?' asig':''}" title="${n} entregas (${pct}%)${asig.includes(d)?' · día asignado':''}"><i style="height:${Math.max(pct, 3)}%"></i><b>${pct}%</b><span>${d}</span></div>`; }).join('');
    const maxB = Math.max(1, ...r.semanas.map(s => s.bultos)), W = r.semanas.length;
    const spark = `<svg class="spark" viewBox="0 0 ${W * 10} 44" preserveAspectRatio="none" role="img" aria-label="Bultos por semana">${r.semanas.map((s, i) =>
      `<rect x="${i * 10 + 1}" y="${44 - Math.max(1, s.bultos / maxB * 42)}" width="8" height="${Math.max(1, s.bultos / maxB * 42)}" rx="1.5"><title>Semana del ${s.desde}: ${num(s.bultos,1)} bultos · ${num(s.hl,2)} HL · ${s.compras} compras</title></rect>`).join('')}</svg>`;
    const kpi = (t, v, sub, k='') => `<div class="pv-kpi ${k}"><span>${t}</span><b>${v}</b>${sub?`<small>${sub}</small>`:''}</div>`;
    el.innerHTML = head + `<p class="status">${esc(r.desde)} al ${esc(r.hasta)} · ventas importadas, sin remitos ni comodatos</p>
      <div class="pv-tags"><span class="pill ${cls}">${ESTADO[m.estado]}</span><span class="pill" title="Clasificación ABC por venta neta">ABC ${esc(m.abc)}</span>${tend!=null?`<span class="pill ${tend<-15?'warn':''}" title="Bultos de la segunda mitad del período contra la primera">${tend>0?'▲':'▼'} ${Math.abs(tend)}%</span>`:''}<span class="pill" title="Compras con al menos un pedido por BEES">BEES ${Math.round(m.bees * 100)}%</span></div>
      <div class="pv-kpis">
        ${kpi('Compras', num(m.compras), m.comprobantes > m.compras ? `${num(m.comprobantes)} comprobantes` : 'un comprobante por día')}
        ${kpi('Frecuencia', m.frec != null ? `cada ${num(m.frec,1)} d` : '—', `última hace ${m.dias_sin} d`, m.estado === 'activo' ? '' : cls)}
        ${kpi('Bultos', num(m.bultos), `${num(m.hl,1)} HL · ${num(m.bultos_sem,1)}/sem`)}
        ${kpi('Por compra', `${num(m.drop,1)} b`, ref ? `${vsRef>0?'+':''}${vsRef}% vs ${esc(ref.localidad)} (${num(ref.drop,1)})` : `${num(m.drop_hl,2)} HL`)}
        ${kpi('Venta neta', money(m.neto), `ticket ${money(m.ticket)}`)}
        ${kpi('Rechazo', `${num(m.rech_pct * 100, 1)}%`, `${num(m.rech,1)} bultos`, m.rech_pct > .05 ? 'bad' : '')}
      </div>
      <h3>Días en que recibe</h3><div class="wdays">${barras}</div>
      <p class="note">${r.sugerencia ? `${Math.round(r.sugerencia.en_dia * 100)}% de sus entregas cae en sus días asignados (${asig || 'sin días'}). Recibe más: ${esc(r.sugerencia.dias) || '—'}.` : 'Pocas entregas para comparar con los días asignados.'}</p>
      <h3>Bultos por semana</h3>${spark}
      ${r.ultimos.length ? `<h3>Últimas compras</h3><div class="tw"><table><thead><tr><th>Fecha</th><th>Comprob.</th><th>Bultos</th><th>HL</th><th>Neto</th><th>Rech.</th></tr></thead><tbody>${r.ultimos.slice(0, 8).map(u => `<tr title="${esc(u.docs.join(', '))} · ${esc(u.origen)}${u.motivo ? ' · ' + esc(u.motivo) : ''}"><td>${esc(u.fecha.slice(5).split('-').reverse().join('/'))}</td><td>${u.comprobantes > 1 ? `${u.comprobantes} · ` : ''}${esc(u.tipo)}</td><td>${num(u.bultos,1)}</td><td>${num(u.hl,2)}</td><td>${money(u.neto)}</td><td class="${u.rech ? 'bad' : 'z'}">${u.rech ? num(u.rech,1) : '·'}</td></tr>`).join('')}</tbody></table></div>` : ''}
      ${r.articulos.length ? `<h3>Más comprado</h3><ol class="arts">${r.articulos.slice(0, 6).map(a => `<li><span>${esc(a.articulo)}</span><b>${num(a.bultos,1)} b</b></li>`).join('')}</ol>` : ''}
      ${Object.keys(m.motivos || {}).length ? `<p class="note">Motivos de rechazo: ${Object.entries(m.motivos).map(([k, n]) => `${esc(k)} (${n})`).join(', ')}</p>` : ''}`;
  }
  el.querySelectorAll('[data-p]').forEach(b => b.onclick = () => { S.periodo = +b.dataset.p; savePrefs(); cargarVentas(c, el); });
}

// ---------- controles ----------
function setDay(v){ S.day=v; S.sel=null; renderCard(); savePrefs(); if(S.D){render();centrarSeleccion()} }
function seg(el, opts, key) {
  el.innerHTML = opts.map(([v,l,n,t]) => `<button type="button" data-v="${esc(v)}" aria-pressed="${S[key]===v}"${t?` title="${esc(t)}"`:''}><span>${esc(l)}</span>${n!=null?`<small>${n}</small>`:''}</button>`).join('');
  el.querySelectorAll('button').forEach(b => b.onclick = () => {
    if (key === 'day') return setDay(b.dataset.v);
    S[key] = b.dataset.v; S.sel=null; renderCard(); savePrefs(); if(S.D){render(); if(key==='suc')centrarSeleccion()}
  });
}
function render() {
  const sucs = [...new Set(S.D.plan.depositos.map(d => d.nombre))];
  if(S.D.clientes.some(c=>c.suc==='SIN ASIGNAR'))sucs.push('SIN ASIGNAR');
  if(S.suc!=='TODAS'&&!sucs.includes(S.suc))S.suc='TODAS';
  seg($('sucSeg'), [['TODAS','Todas'], ...sucs.map(s => [s, s.charAt(0)+s.slice(1).toLowerCase()])], 'suc');
  const base = RutasVista.filtrar(S.D.clientes, {suc:S.suc, day:'TODOS', q:S.q}, c => !c.an);
  seg($('daySeg'), [['TODOS','Semana',null,'Toda la semana (tecla 0)'], ...DAYS.map((d,i) => [d, DAYSHORT[d], base.filter(c=>c.d.includes(d)).length, `${DAYNAME[d]} · clientes activos (tecla ${i+1})`])], 'day');
  seg($('verSeg'), Object.entries(VER).map(([k,l]) => [k,l]), 'ver');
  const v = visible(); viewData=RutasVista.resumir(v,S.D.plan,S.suc); drawPoints(v);
  renderLoc(); renderDia(); renderPen(); renderExp(); renderVen(); renderLegend(v); renderTools();
  if (S.sel) { const c = byId.get(S.sel); if (c && !card) renderCard(); }
  const geo = v.filter(isGeo).length, nloc = new Set(v.filter(c=>!c.an).map(c=>c.loc)).size;
  $('sub').textContent = `${S.day!=='TODOS'?DAYNAME[S.day]+' · ':''}${v.length} clientes en ${nloc} localidades · ${geo} en el mapa${v.length-geo?` · ${v.length-geo} sin coordenadas`:''}`;
}
document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
  document.querySelectorAll('.tab').forEach(x => x.setAttribute('aria-selected', x===t));
  ['loc','dia','pen','ven','exp'].forEach(k => $('p-'+k).hidden = ('t-'+k) !== t.id); });
let qt; $('q').addEventListener('input', e => { clearTimeout(qt); qt = setTimeout(() => { S.q = e.target.value; if(!S.D)return; render();
  const v = visible().filter(isGeo); if (S.q && v.length && v.length < 40) map.fitBounds(v.map(c => [c.lat,c.lng]), {padding:[50,50], maxZoom:15}); }, 200); });

document.addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target.closest?.('input,select,textarea')) { if (e.key === 'Escape') e.target.blur(); return; }
  if (e.key === '/') { e.preventDefault(); $('q').focus(); return; }
  if (e.key === 'Escape' && S.sel) { cerrarCard(); return; }
  const i = '0123456'.indexOf(e.key);
  if (i >= 0 && e.key.length === 1 && S.D) setDay(i ? DAYS[i-1] : 'TODOS');
});

let loadRequest=0;
async function load() {
  const request=++loadRequest;
  loading.hidden=false;
  try {
    const params=new URLSearchParams({activos:$('activeClients').value,dias_asignados:$('assignedDays').value});
    const [data, ventas] = await Promise.all([api('/datos?'+params), api('/ventas/comportamiento').catch(() => null)]);
    if(request!==loadRequest)return;
    S.D=data; S.V=ventas && ventas.comprobantes ? ventas : null;
    if (S.V) { const vs = Object.values(S.V.clientes).map(v => v.bultos_sem).filter(v => v > 0).sort((a,b) => a-b);
      VOL_Q = vs.length >= 5 ? [.2,.4,.6,.8].map(q => vs[Math.floor(q * (vs.length - 1))]) : []; }
    byId = new Map(S.D.clientes.map(c => [c.id, c]));
    asignarColores(S.D.clientes);
    render(); renderCard();
    if(!mapPositioned){const points=visible().filter(c=>isGeo(c)&&!c.far);if(points.length){map.fitBounds(points.map(c=>[c.lat,c.lng]),{padding:[30,30],maxZoom:13});mapPositioned=true}}
    if(!S.D.clientes.length)$('sub').textContent='No hay clientes cargados. Actualizá el maestro e importá los días desde Importaciones de datos.';
  } catch (e) { if(request===loadRequest){$('sub').textContent = 'No se pudieron cargar los datos: ' + e.message; toast('No se pudieron cargar los datos', true)} }
  finally { if(request===loadRequest)loading.hidden=true; }
}
$('refreshView').onclick=()=>load();
for(const id of ['activeClients','assignedDays'])$(id).onchange=()=>{S.sel=null;S.flt=null;renderCard();load()};
load();
})();
