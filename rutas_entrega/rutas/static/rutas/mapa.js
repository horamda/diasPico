/* Mapa de rutas de entrega — lee /api/datos y edita con PATCH /api/clientes/<id> */
(() => {
const DAYS = ['LU','MA','MI','JU','VI','SA'];
const DAYNAME = {LU:'Lunes',MA:'Martes',MI:'Miércoles',JU:'Jueves',VI:'Viernes',SA:'Sábado'};
const PCOL = {LUJU:'#2f6fde',MAVI:'#159a62',MISA:'#8a4fd0',MAJU:'#0e97ad',MASA:'#c2559b',LU:'#86a9ec',JU:'#86a9ec',MA:'#74c7a1',VI:'#74c7a1',MI:'#b89be6',SA:'#b89be6'};
const API = window.RUTAS.api, EXP = window.RUTAS.exportBase;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
const tok = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

const S = {suc:'TODAS', day:'TODOS', q:'', flt:null, sel:null, placing:false, D:null};
let byId = new Map();
const isGeo = c => c.lat != null && c.lng != null;
const sinDias = c => !c.d && !c.an;
const FLT = {
  sindias: sinDias, singeo: c => !isGeo(c) && !c.an, far: c => c.far, anulado: c => c.an && c.d,
  fuera: c => !c.pl && !c.an, cambia: c => !c.an && c.d !== c.de, pend: c => c.pend && !c.an,
};
const FLT_LABEL = {sindias:'sin días de entrega', singeo:'sin geolocalizar', far:'ubicación a revisar',
  anulado:'anulados en ERP con días', cambia:'días distintos al ERP', pend:'pendientes de subir a BEES'};

function toast(msg, err){ const t=document.createElement('div'); t.className='toast'+(err?' err':''); t.textContent=msg;
  document.body.appendChild(t); setTimeout(()=>t.remove(), 3500); }

async function api(path, opts={}) {
  const r = await fetch(API + path, {headers:{'Content-Type':'application/json'}, credentials:'same-origin', ...opts});
  const j = await r.json().catch(()=>({}));
  if (!r.ok) throw new Error(j.error || ('Error ' + r.status));
  return j;
}

// ---------- mapa ----------
const map = L.map('map', {preferCanvas:true, zoomSnap:.25}).fitBounds([[-37.1,-58.6],[-35.3,-56.8]]);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19,
  attribution:'&copy; OpenStreetMap'}).addTo(map);
const routeLayer = L.layerGroup().addTo(map);
const ptLayer = L.layerGroup().addTo(map);
const depLayer = L.layerGroup().addTo(map);

function visible() {
  const q = S.q.trim().toUpperCase();
  return S.D.clientes.filter(c => (S.suc==='TODAS' || c.suc===S.suc)
    && (S.day==='TODOS' || c.d.includes(S.day))
    && (!q || String(c.id).includes(q) || c.n.toUpperCase().includes(q) || c.rs.toUpperCase().includes(q) || c.dom.toUpperCase().includes(q))
    && (!S.flt || FLT[S.flt](c)));
}
function drawDepots() {
  depLayer.clearLayers();
  S.D.plan.depositos.filter(d => d.lat != null).forEach(d => L.marker([d.lat,d.lng], {zIndexOffset:1000,
    icon: L.divIcon({className:'', html:`<div class="depot">${esc(d.nombre.slice(0,3))}</div>`, iconSize:[30,22], iconAnchor:[15,11]})})
    .bindTooltip('Depósito ' + esc(d.nombre) + (d.direccion ? '<br>' + esc(d.direccion) : '')).addTo(depLayer));
}
function drawPoints(list) {
  ptLayer.clearLayers();
  if (S.sel && !list.some(c => c.id === S.sel)) list = [...list, byId.get(S.sel)];
  list.forEach(c => {
    if (!isGeo(c)) return;
    const sd = sinDias(c), sel = S.sel === c.id;
    const fill = c.an ? '#9a9f9b' : sd ? tok('--bad') : (PCOL[c.d] || '#8d8a5c');
    const m = L.circleMarker([c.lat,c.lng], {radius: sel?9:(sd?6:5), weight: sel?3:(c.far?2.5:1),
      color: sel ? tok('--ink') : (c.far ? tok('--warn') : 'rgba(0,0,0,.45)'), fillColor: fill, fillOpacity: c.an?.5:.9});
    m.bindTooltip(`<b>${c.id}</b> ${esc(c.n)}<br>${esc(c.loc)} · ${c.d || 'sin días'}${c.an?' · anulado en ERP':''}`);
    m.on('click', () => select(c.id));
    ptLayer.addLayer(m);
  });
}
function drawRoutes() {
  routeLayer.clearLayers();
  if (S.day === 'TODOS') return;
  const locs = Object.fromEntries(S.D.plan.localidades.map(l => [l.nombre, l]));
  const deps = Object.fromEntries(S.D.plan.depositos.map(d => [d.nombre, d]));
  S.D.plan.vehiculos.forEach(v => {
    if (S.suc !== 'TODAS' && S.suc !== v.deposito) return;
    const stops = v.plan[S.day] || []; const dep = deps[v.deposito];
    if (!stops.length || !dep || dep.lat == null) return;
    const pts = [[dep.lat,dep.lng], ...stops.map(s => locs[s]).filter(l => l && l.lat != null).map(l => [l.lat,l.lng]), [dep.lat,dep.lng]];
    L.polyline(pts, {color:v.color, weight:4, opacity:.8, dashArray:'8 7'})
      .bindTooltip(`${esc(v.deposito)} · ${esc(v.nombre)}: ${stops.map(esc).join(' → ')}`, {sticky:true}).addTo(routeLayer);
  });
}

// ---------- paneles ----------
function scope() { return S.D.clientes.filter(c => S.suc==='TODAS' || c.suc===S.suc); }
function renderLoc() {
  const sc = scope(), k = f => sc.filter(FLT[f]).length, act = sc.filter(c => !c.an);
  const kp = [['',act.length,'clientes activos',null],['',act.filter(isGeo).length,'geolocalizados',null],
    ['bad',k('sindias'),'sin días de entrega','sindias'],['bad',k('singeo'),'sin geolocalizar','singeo'],
    ['warn',k('far'),'ubicación a revisar','far'],['warn',k('anulado'),'anulados en ERP con días','anulado']];
  const rows = S.D.resumen.por_localidad.filter(r => S.suc==='TODAS' || r.suc===S.suc);
  let html = '', last = '';
  rows.forEach(r => { if (r.suc !== last) { html += `<tr class="suc"><td colspan="10">Sale de ${esc(r.suc)}</td></tr>`; last = r.suc; }
    html += `<tr data-loc="${esc(r.loc)}"><td>${esc(r.loc)}</td><td>${r.clientes}</td><td class="${r.sin_geo?'bad':''}">${r.sin_geo||'·'}</td><td class="${r.sin_dias?'bad':''}">${r.sin_dias||'·'}</td>${DAYS.map(d=>`<td class="${r[d]?'':'z'}">${r[d]||'·'}</td>`).join('')}</tr>`; });
  $('p-loc').innerHTML = `
   <div class="kpis">${kp.map(([c,n,l,f])=>`<button class="kpi ${c}" ${f?`data-f="${f}" aria-pressed="${S.flt===f}"`:'disabled style="cursor:default"'}><b>${n}</b><span>${l}</span></button>`).join('')}</div>
   ${S.flt?`<p class="note">Filtro en el mapa: <b>${FLT_LABEL[S.flt]||S.flt}</b> · <a href="#" id="clrF">quitar</a></p>`:''}
   <div><h2>Clientes activos por localidad y día</h2></div>
   <div class="tw"><table><thead><tr><th>Localidad</th><th>Act.</th><th title="Sin geolocalizar">S/geo</th><th title="Sin días">S/día</th>${DAYS.map(d=>`<th>${d}</th>`).join('')}</tr></thead><tbody>${html}</tbody></table></div>
   <p class="note">Tocá una localidad para centrar el mapa.</p>
   <div><h2>Color del punto = días asignados</h2></div>
   <div class="legend">${['LUJU','MAVI','MISA','MAJU','MASA'].map(p=>`<span><i style="background:${PCOL[p]}"></i>${p}</span>`).join('')}
     <span><i style="background:#86a9ec"></i>un solo día</span><span><i style="background:var(--bad)"></i>sin días</span><span><i style="background:#9a9f9b"></i>anulado ERP</span><span><i style="background:transparent;border:2px solid var(--warn)"></i>ubicación a revisar</span></div>`;
  $('p-loc').querySelectorAll('[data-f]').forEach(b => b.onclick = () => { S.flt = S.flt===b.dataset.f ? null : b.dataset.f; render(); });
  const cf = $('clrF'); if (cf) cf.onclick = e => { e.preventDefault(); S.flt = null; render(); };
  $('p-loc').querySelectorAll('tr[data-loc]').forEach(tr => tr.onclick = () => {
    const pts = S.D.clientes.filter(c => c.loc===tr.dataset.loc && isGeo(c) && !c.far);
    if (pts.length) map.fitBounds(pts.map(c => [c.lat,c.lng]), {padding:[40,40], maxZoom:15}); });
}
function renderDia() {
  const days = S.day==='TODOS' ? DAYS : [S.day];
  let html = `<p class="note">⇄ = localidad que ese día comparten dos camiones (el total cuenta la localidad entera). ${S.day==='TODOS' ? 'Elegí un día arriba para ver el recorrido de cada camión.' : 'Recorrido esquemático depósito → localidades → depósito.'} El plan se edita en <a href="${API.replace(/\/api$/,'')}/plan">Camiones y localidades</a>.</p>`;
  days.forEach(d => {
    const c = S.D.carga[d];
    html += `<div><h2>${DAYNAME[d]}</h2></div>`;
    c.vehiculos.filter(v => S.suc==='TODAS' || v.deposito===S.suc).forEach(v => {
      const over = v.capacidad && v.total > v.capacidad;
      html += `<div class="veh ${over?'alert':''}"><header><h3><span style="color:${v.color}">■</span> ${esc(v.deposito)} · ${esc(v.nombre)}</h3><span class="tot" ${over?'style="color:var(--bad)"':''}>${v.total}${v.capacidad?`<small style="font-size:13px;color:var(--muted)"> / ${v.capacidad}</small>`:''}</span></header>
        <div class="stops">${v.paradas.length ? v.paradas.map(p=>`<span class="pill" ${p.compartida?'title="Localidad compartida con otro camión ese día: el número es el total de la localidad"':''}>${esc(p.loc)} ${p.n}${p.compartida?' ⇄':''}</span>`).join('') : '<span class="note">Sin salida planificada</span>'}</div></div>`;
    });
    if (c.sin_camion.length) html += `<div class="veh alert"><header><h3>Con día pero sin camión ese día</h3><span class="tot" style="color:var(--bad)">${c.sin_camion.reduce((a,b)=>a+b.n,0)}</span></header><div class="stops">${c.sin_camion.map(x=>`<span class="pill bad">${esc(x.loc)} ${x.n}</span>`).join('')}</div></div>`;
  });
  $('p-dia').innerHTML = html;
}
function itemHTML(c, tag) { return `<div class="item" data-id="${c.id}"><span class="id">${c.id}</span><span class="nm">${esc(c.n)}</span>${tag}<span class="sub">${esc(c.loc)} · ${esc(c.dom)||'sin domicilio'}${c.ven?' · '+esc(c.ven):''}</span></div>`; }
function bindItems(el) { el.querySelectorAll('.item').forEach(x => x.onclick = () => select(+x.dataset.id, true)); }
function renderPen() {
  const sc = scope(), sd = sc.filter(sinDias), sg = sc.filter(FLT.singeo), fr = sc.filter(FLT.far), an = sc.filter(FLT.anulado);
  $('penN').textContent = sd.length + sg.length;
  const sec = (t,list,tag,note) => `<div><h2>${t} · ${list.length}</h2>${note?`<p class="note">${note}</p>`:''}</div><div class="list">${list.map(c=>itemHTML(c,tag(c))).join('') || '<p class="note">Nada pendiente.</p>'}</div>`;
  $('p-pen').innerHTML =
    sec('Sin días de entrega', sd, c => c.pl ? '<span class="pill bad">sin días</span>' : '<span class="pill warn">no estaba en planilla</span>', 'Clientes activos en el ERP sin días asignados.') +
    sec('Sin geolocalizar', sg, () => '<span class="pill bad">sin coord.</span>', 'Elegí uno y usá "Ubicar en el mapa".') +
    sec('Ubicación a revisar', fr, () => '<span class="pill warn">lejos</span>', 'Coordenada fuera de la provincia o a más de 15 km del centro de su localidad.') +
    sec('Anulados en ERP pero con días', an, c => `<span class="pill">${c.d}</span>`, 'No se exportan a BEES.');
  bindItems($('p-pen'));
}
function renderExp() {
  const pend = S.D.clientes.filter(FLT.pend), r = S.D.resumen;
  $('p-exp').innerHTML = `
   <div><h2>Pendientes de subir · ${pend.length}</h2><p class="note">Clientes con días cambiados en la app desde el último export marcado.</p></div>
   <div class="list">${pend.slice(0,200).map(c=>itemHTML(c,`<span class="pill ok">${c.d||'sin días'}</span>`)).join('') || '<p class="note">No hay cambios pendientes.</p>'}</div>
   <div><h2>Exportar para BEES</h2><p class="note">Formato de la hoja subirModificado (Vendor_Account_ID, Mon…Sun = FREE/NO). Excluye anulados del ERP.</p></div>
   <div class="row">
     <a class="btn primary" href="${EXP}bees.xlsx">Excel completo</a>
     <a class="btn" href="${EXP}bees.xlsx?solo_pendientes=1">Excel solo cambios</a>
     <a class="btn" href="${EXP}bees.csv">CSV completo</a>
   </div>
   <div class="row"><button class="btn" id="mkExp" ${pend.length?'':'disabled'}>Marcar cambios como subidos</button></div>
   <div><h2>Planilla vs ERP</h2><p class="note">${r.distinto_erp} clientes activos tienen días distintos a los del ERP (Fuerza de venta 1).</p></div>
   <div class="row"><button class="btn" id="fCambia">${S.flt==='cambia'?'Quitar filtro':'Ver en el mapa'}</button></div>
   <p class="status">${S.D.ultima_sync ? 'Última carga de clientes: ' + esc(S.D.ultima_sync.origen) + ' · ' + new Date(S.D.ultima_sync.fin+'Z').toLocaleString('es-AR') : ''}</p>`;
  bindItems($('p-exp'));
  $('fCambia').onclick = () => { S.flt = S.flt==='cambia' ? null : 'cambia'; render(); };
  $('mkExp').onclick = async () => { try { await api('/bees/marcar-exportados', {method:'POST'}); toast('Marcados como subidos'); await load(); } catch(e) { toast(e.message, true); } };
}

// ---------- ficha de cliente ----------
let card = null, draft = null, banner = null, tmpMk = null;
function select(id, fly) {
  S.sel = id; const c = byId.get(id); if (!c) return;
  draft = {d:c.d, lat:c.lat, lng:c.lng, nota:c.nota};
  if (fly && isGeo(c)) map.flyTo([c.lat,c.lng], Math.max(map.getZoom(), 15), {duration:.6});
  renderCard(); drawPoints(visible());
}
function renderCard() {
  if (card) card.remove(); card = null; if (!S.sel) return;
  const c = byId.get(S.sel); if (!c) return;
  const dirty = draft.d!==c.d || draft.lat!==c.lat || draft.lng!==c.lng || (draft.nota||'')!==(c.nota||'');
  card = document.createElement('div'); card.className = 'card';
  const gm = isGeo(draft) ? `https://www.google.com/maps?q=${draft.lat},${draft.lng}` : `https://www.google.com/maps/search/${encodeURIComponent(c.dom+', '+c.loc+', Buenos Aires')}`;
  card.innerHTML = `<button class="x" aria-label="Cerrar">×</button>
   <h3>${esc(c.n)}</h3>
   <dl class="kv"><dt>Cliente</dt><dd class="mono">${c.id}${c.pend?' · <span class="pill ok">pendiente BEES</span>':''}</dd>
    <dt>Razón social</dt><dd>${esc(c.rs)}</dd><dt>Domicilio</dt><dd>${esc(c.dom)||'—'}, ${esc(c.loc)}</dd>
    <dt>Sale de</dt><dd>${esc(c.suc)}</dd><dt>Vendedor</dt><dd>${esc(c.ven)||'—'} · ruta ${esc(c.rv)||'—'}</dd>
    <dt>Horario</dt><dd>${esc(c.h)||'—'}</dd><dt>Días en ERP</dt><dd>${c.de||'ninguno'}${c.an?' · <span class="pill bad">anulado</span>':''}</dd>
    <dt>Ubicación</dt><dd class="mono">${isGeo(draft)?draft.lat.toFixed(5)+', '+draft.lng.toFixed(5):'sin coordenadas'}${c.corr?' · corregida':''}${c.far?' <span class="pill warn">a revisar</span>':''}</dd></dl>
   <div class="days" role="group" aria-label="Días de entrega">${DAYS.map(d=>`<button class="day" data-d="${d}" aria-pressed="${draft.d.includes(d)}">${d}</button>`).join('')}</div>
   <textarea class="nota" id="nota" placeholder="Nota (ej. entregar por el portón de atrás)">${esc(draft.nota)}</textarea>
   <div class="row"><button class="btn primary" id="sv" ${dirty?'':'disabled'}>Guardar</button>
     <button class="btn" id="pl">${S.placing?'Tocá el mapa…':'Ubicar en el mapa'}</button>
     ${c.corr?'<button class="btn" id="rv">Usar ubicación del ERP</button>':''}
     <a class="btn" href="${gm}" target="_blank" rel="noopener">Google Maps ↗</a></div>`;
  document.getElementById('map').appendChild(card);
  L.DomEvent.disableClickPropagation(card); L.DomEvent.disableScrollPropagation(card);
  card.querySelector('.x').onclick = () => { S.sel = null; S.placing = false; togglePlacing(); renderCard(); drawPoints(visible()); };
  card.querySelectorAll('.day').forEach(b => b.onclick = () => { const set = new Set(draft.d.match(/../g) || []); const d = b.dataset.d;
    set.has(d) ? set.delete(d) : set.add(d); draft.d = DAYS.filter(x => set.has(x)).join(''); renderCard(); });
  card.querySelector('#nota').oninput = e => { draft.nota = e.target.value; card.querySelector('#sv').disabled = false; };
  card.querySelector('#pl').onclick = () => { S.placing = !S.placing; togglePlacing(); renderCard(); };
  card.querySelector('#sv').onclick = () => save(c, draft);
  const rv = card.querySelector('#rv'); if (rv) rv.onclick = () => save(c, {...draft, lat:null, lng:null}, true);
}
function togglePlacing() {
  if (banner) { banner.remove(); banner = null; }
  map.getContainer().style.cursor = S.placing ? 'crosshair' : '';
  if (S.placing) { banner = document.createElement('div'); banner.className = 'banner'; banner.textContent = 'Tocá el mapa donde está el cliente'; $('map').appendChild(banner); }
}
map.on('click', e => { if (!S.placing || !S.sel) return;
  draft.lat = +e.latlng.lat.toFixed(6); draft.lng = +e.latlng.lng.toFixed(6); S.placing = false; togglePlacing(); renderCard();
  if (tmpMk) tmpMk.remove(); tmpMk = L.circleMarker(e.latlng, {radius:10, color:tok('--accent'), weight:3, fillOpacity:0}).addTo(map); });
async function save(c, d, revert) {
  const body = {};
  if (d.d !== c.d) body.dias = d.d;
  if (revert || d.lat !== c.lat || d.lng !== c.lng) { body.lat = d.lat; body.lng = d.lng; }
  if ((d.nota||'') !== (c.nota||'')) body.nota = d.nota;
  try {
    const r = await api('/clientes/' + c.id, {method:'PATCH', body: JSON.stringify(body)});
    Object.assign(c, r.cliente); toast('Guardado'); if (tmpMk) { tmpMk.remove(); tmpMk = null; }
    await load(true);
  } catch (e) { toast(e.message, true); }
}

// ---------- controles ----------
function seg(el, opts, key) {
  el.innerHTML = opts.map(([v,l]) => `<button data-v="${v}" aria-pressed="${S[key]===v}">${l}</button>`).join('');
  el.querySelectorAll('button').forEach(b => b.onclick = () => { S[key] = b.dataset.v; render(); });
}
function render() {
  const sucs = [...new Set(S.D.plan.depositos.map(d => d.nombre))];
  seg($('sucSeg'), [['TODAS','Todas'], ...sucs.map(s => [s, s.charAt(0)+s.slice(1).toLowerCase()])], 'suc');
  seg($('daySeg'), [['TODOS','Semana'], ...DAYS.map(d => [d,d])], 'day');
  const v = visible(); drawPoints(v); drawRoutes();
  renderLoc(); renderDia(); renderPen(); renderExp();
  if (S.sel) { const c = byId.get(S.sel); if (c && !card) renderCard(); }
  const geo = v.filter(isGeo).length;
  $('sub').textContent = `${v.length} clientes en vista · ${geo} en el mapa${v.length-geo?` · ${v.length-geo} sin coordenadas`:''}${S.day!=='TODOS'?' · '+DAYNAME[S.day]:''}`;
}
document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
  document.querySelectorAll('.tab').forEach(x => x.setAttribute('aria-selected', x===t));
  ['loc','dia','pen','exp'].forEach(k => $('p-'+k).hidden = ('t-'+k) !== t.id); });
let qt; $('q').addEventListener('input', e => { clearTimeout(qt); qt = setTimeout(() => { S.q = e.target.value; render();
  const v = visible().filter(isGeo); if (S.q && v.length && v.length < 40) map.fitBounds(v.map(c => [c.lat,c.lng]), {padding:[50,50], maxZoom:15}); }, 200); });

async function load(keepCard) {
  try {
    S.D = await api('/datos');
    byId = new Map(S.D.clientes.map(c => [c.id, c]));
    if (keepCard && S.sel) { const c = byId.get(S.sel); draft = {d:c.d, lat:c.lat, lng:c.lng, nota:c.nota}; }
    drawDepots(); render(); renderCard();
  } catch (e) { $('sub').textContent = 'No se pudieron cargar los datos: ' + e.message; }
}
load();
})();
