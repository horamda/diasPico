/* Mapa de rutas de entrega — consulta clientes y días importados */
(() => {
const DAYS = ['LU','MA','MI','JU','VI','SA'];
const DAYNAME = {LU:'Lunes',MA:'Martes',MI:'Miércoles',JU:'Jueves',VI:'Viernes',SA:'Sábado'};
const PCOL = {LUJU:'#2f6fde',MAVI:'#159a62',MISA:'#8a4fd0',MAJU:'#0e97ad',MASA:'#c2559b',LU:'#86a9ec',JU:'#86a9ec',MA:'#74c7a1',VI:'#74c7a1',MI:'#b89be6',SA:'#b89be6'};
const API = window.RUTAS.api;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
const tok = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

const S = {suc:'TODAS', day:'TODOS', q:'', flt:null, sel:null, D:null};
let byId = new Map();
let mapPositioned=false;
const isGeo = c => c.lat != null && c.lng != null;
const sinDias = c => !c.d;
const FLT = {
  sindias: sinDias, singeo: c => !isGeo(c), far: c => c.far, anulado: c => c.an && c.d,
  fuera: c => !c.pl && !c.an, cambia: c => !c.an && c.d !== c.de, pend: c => c.pend && !c.an,
};
const FLT_LABEL = {sindias:'sin días de entrega', singeo:'sin geolocalizar', far:'ubicación a revisar',
  anulado:'inactivos con días asignados', cambia:'días distintos al ERP', pend:'pendientes de subir a BEES'};

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
const ptLayer = L.layerGroup().addTo(map);

function visible(){return RutasVista.filtrar(S.D.clientes,S,c=>!S.flt||FLT[S.flt](c))}
let viewData=null;
function centrarSeleccion(){const points=visible().filter(isGeo);if(points.length)map.fitBounds(points.map(c=>[c.lat,c.lng]),{padding:[40,40],maxZoom:15})}
function drawPoints(list) {
  ptLayer.clearLayers();
  if (S.sel && !list.some(c => c.id === S.sel)) { S.sel=null; renderCard(); }
  list.forEach(c => {
    if (!isGeo(c)) return;
    const sd = sinDias(c), sel = S.sel === c.id;
    const fill = c.an ? '#9a9f9b' : sd ? tok('--bad') : (PCOL[c.d] || '#8d8a5c');
    const m = L.circleMarker([c.lat,c.lng], {radius: sel?9:(sd?6:5), weight: sel?3:(c.far?2.5:1),
      color: sel ? tok('--ink') : (c.far ? tok('--warn') : 'rgba(0,0,0,.45)'), fillColor: fill, fillOpacity: c.an?.5:.9});
    m.bindTooltip(`<b>${c.id}</b> ${esc(c.n)}<br>${esc(c.loc)} · ${c.d || 'sin días'}${c.an?' · inactivo':''}`);
    m.on('click', () => select(c.id));
    ptLayer.addLayer(m);
  });
}
// ---------- paneles ----------
function scope(){return visible()}
function renderLoc() {
  const sc = scope(), k = f => sc.filter(FLT[f]).length, act = sc.filter(c => !c.an);
  const kp = [['',sc.length,'clientes filtrados',null],['',sc.filter(isGeo).length,'geolocalizados',null],
    ['bad',k('sindias'),'sin días de entrega','sindias'],['bad',k('singeo'),'sin geolocalizar','singeo'],
    ['warn',k('far'),'ubicación a revisar','far'],['warn',k('anulado'),'inactivos con días asignados','anulado']];
  const rows=viewData.por_localidad;
  const days=S.day==='TODOS'?DAYS:[S.day];
  let html = '', last = '';
  rows.forEach(r => { if (r.suc !== last) { html += `<tr class="suc"><td colspan="${4+days.length}">Sale de ${esc(r.suc)}</td></tr>`; last = r.suc; }
    html += `<tr data-loc="${esc(r.loc)}"><td>${esc(r.loc)}</td><td>${r.clientes}</td><td class="${r.sin_geo?'bad':''}">${r.sin_geo||'·'}</td><td class="${r.sin_dias?'bad':''}">${r.sin_dias||'·'}</td>${days.map(d=>`<td class="${r[d]?'':'z'}">${r[d]||'·'}</td>`).join('')}</tr>`; });
  $('p-loc').innerHTML = `
   <div class="kpis">${kp.map(([c,n,l,f])=>`<button class="kpi ${c}" ${f?`data-f="${f}" aria-pressed="${S.flt===f}"`:'disabled style="cursor:default"'}><b>${n}</b><span>${l}</span></button>`).join('')}</div>
   ${S.flt?`<p class="note">Filtro aplicado: <b>${FLT_LABEL[S.flt]||S.flt}</b> · <a href="#" id="clrF">quitar</a></p>`:''}
   <div><h2>Clientes filtrados por localidad y día</h2></div>
   <div class="tw"><table><thead><tr><th>Localidad</th><th>Clientes</th><th title="Sin geolocalizar">S/geo</th><th title="Sin días">S/día</th>${days.map(d=>`<th>${d}</th>`).join('')}</tr></thead><tbody>${html}</tbody></table></div>
   <p class="note">Tocá una localidad para centrar el mapa.</p>
   <div><h2>Color del punto = días asignados</h2></div>
   <div class="legend">${['LUJU','MAVI','MISA','MAJU','MASA'].map(p=>`<span><i style="background:${PCOL[p]}"></i>${p}</span>`).join('')}
     <span><i style="background:#86a9ec"></i>un solo día</span><span><i style="background:var(--bad)"></i>sin días</span><span><i style="background:#9a9f9b"></i>inactivo</span><span><i style="background:transparent;border:2px solid var(--warn)"></i>ubicación a revisar</span></div>`;
  $('p-loc').querySelectorAll('[data-f]').forEach(b => b.onclick = () => { S.flt = S.flt===b.dataset.f ? null : b.dataset.f; render(); });
  const cf = $('clrF'); if (cf) cf.onclick = e => { e.preventDefault(); S.flt = null; render(); };
  $('p-loc').querySelectorAll('tr[data-loc]').forEach(tr => tr.onclick = () => {
    const pts = scope().filter(c => c.loc===tr.dataset.loc && isGeo(c) && !c.far);
    if (pts.length) map.fitBounds(pts.map(c => [c.lat,c.lng]), {padding:[40,40], maxZoom:15}); });
}
function renderDia() {
  const days = S.day==='TODOS' ? DAYS : [S.day];
  $('p-dia').innerHTML = days.map(d => {
    const clients=scope().filter(c=>c.d.includes(d));
    return `<h2>${DAYNAME[d]} ? ${clients.length} clientes</h2><div class="list">${clients.map(c=>itemHTML(c,`<span class="pill">${esc(c.suc)}</span>`)).join('')||'<p class="note">No hay clientes para los filtros seleccionados.</p>'}</div>`;
  }).join('');
  bindItems($('p-dia'));
}
function itemHTML(c, tag) { return `<div class="item" data-id="${c.id}"><span class="id">${c.id}</span><span class="nm">${esc(c.n)}</span>${tag}<span class="sub">${esc(c.loc)} · ${esc(c.dom)||'sin domicilio'}${c.ven?' · '+esc(c.ven):''}</span></div>`; }
function bindItems(el) { el.querySelectorAll('.item').forEach(x => x.onclick = () => select(+x.dataset.id, true)); }
function renderPen() {
  const sc = scope(), sd = sc.filter(sinDias), sg = sc.filter(FLT.singeo), fr = sc.filter(FLT.far), an = sc.filter(FLT.anulado);
  $('penN').textContent = sd.length + sg.length;
  const sec = (t,list,tag,note) => `<div><h2>${t} · ${list.length}</h2>${note?`<p class="note">${note}</p>`:''}</div><div class="list">${list.map(c=>itemHTML(c,tag(c))).join('') || '<p class="note">Nada pendiente.</p>'}</div>`;
  $('p-pen').innerHTML =
    sec('Sin días de entrega', sd, c => c.pl ? '<span class="pill bad">sin días</span>' : '<span class="pill warn">no estaba en planilla</span>', 'Clientes filtrados sin días asignados.') +
    sec('Sin geolocalizar', sg, () => '<span class="pill bad">sin coord.</span>', 'Clientes sin coordenadas disponibles.') +
    sec('Ubicación a revisar', fr, () => '<span class="pill warn">lejos</span>', 'Coordenada fuera de la provincia o a más de 15 km del centro de su localidad.') +
    sec('Inactivos con días asignados', an, c => `<span class="pill">${c.d}</span>`, 'Revisá si corresponde quitarles los días de entrega.');
  bindItems($('p-pen'));
}
function renderExp(){
  $('p-exp').innerHTML=`<h2>Rutas de entrega · Solo consulta</h2><p>${scope().length} clientes · ${S.day==='TODOS'?'Semana':DAYNAME[S.day]} · ${esc(S.suc==='TODAS'?'Todas las sucursales':S.suc)}</p><p class="note">Los días provienen del archivo importado: un 1 en LUNES a SÁBADO indica visita ese día. Las columnas de BEES no se usan.</p><p class="note">Los recorridos conectan localidades en línea recta. La carga por vehículo es una estimación de cobertura.</p><p class="status">${S.D.ultima_sync?'Última actualización del maestro: '+esc(S.D.ultima_sync.fin):'Sin actualización registrada.'}</p>`;
}

// ---------- ficha de consulta ----------
let card=null;
function select(id,fly){
  S.sel=id;const c=byId.get(id);if(!c)return;
  if(fly&&isGeo(c))map.flyTo([c.lat,c.lng],Math.max(map.getZoom(),15),{duration:.6});
  renderCard();drawPoints(visible());
}
function renderCard(){
  if(card)card.remove();card=null;if(!S.sel)return;
  const c=byId.get(S.sel);if(!c)return;
  card=document.createElement('div');card.className='card';
  const gm=isGeo(c)?`https://www.google.com/maps?q=${c.lat},${c.lng}`:`https://www.google.com/maps/search/${encodeURIComponent(c.dom+', '+c.loc+', Buenos Aires')}`;
  card.innerHTML=`<button class="x" aria-label="Cerrar">×</button><h3>${esc(c.n)}</h3>
    <dl class="kv"><dt>Cliente</dt><dd>${c.id}</dd><dt>Domicilio</dt><dd>${esc(c.dom)}, ${esc(c.loc)}</dd><dt>Sale de</dt><dd>${esc(c.suc)}</dd><dt>Estado</dt><dd>${c.an?'Inactivo':'Activo'}</dd><dt>Días de entrega</dt><dd>${DAYS.filter(d=>c.d.includes(d)).map(d=>DAYNAME[d]).join(', ')||'Sin días asignados'}</dd><dt>Horario</dt><dd>${esc(c.h)||'—'}</dd><dt>Nota</dt><dd>${esc(c.nota)||'—'}</dd></dl>
    <div class="row"><a class="btn" href="${gm}" target="_blank" rel="noopener">Ver ubicación</a><button class="btn" id="history">Historial</button></div><div id="clientHistory" role="status"></div>`;
  $('map').appendChild(card);L.DomEvent.disableClickPropagation(card);L.DomEvent.disableScrollPropagation(card);
  card.querySelector('.x').onclick=()=>{S.sel=null;renderCard();drawPoints(visible())};
  card.querySelector('#history').onclick=async()=>{
    const target=card.querySelector('#clientHistory');target.textContent='Consultando historial...';
    try{const rows=await api('/clientes/'+c.id+'/historial');target.innerHTML=rows.length?rows.map(r=>`<p><strong>${esc(r.campo)}</strong>: ${esc(r.antes??'—')} → ${esc(r.despues??'—')}<br><small>${esc(r.usuario||'Sin usuario')} · ${esc(r.fecha)}</small></p>`).join(''):'Sin cambios registrados.'}catch(e){target.textContent=e.message}
  };
}

// ---------- controles ----------
function seg(el, opts, key) {
  el.innerHTML = opts.map(([v,l]) => `<button data-v="${esc(v)}" aria-pressed="${S[key]===v}">${esc(l)}</button>`).join('');
  el.querySelectorAll('button').forEach(b => b.onclick = () => { S[key] = b.dataset.v; S.sel=null; renderCard(); if(S.D){render();centrarSeleccion()} });
}
function render() {
  const sucs = [...new Set(S.D.plan.depositos.map(d => d.nombre))];
  if(S.D.clientes.some(c=>c.suc==='SIN ASIGNAR'))sucs.push('SIN ASIGNAR');
  seg($('sucSeg'), [['TODAS','Todas'], ...sucs.map(s => [s, s.charAt(0)+s.slice(1).toLowerCase()])], 'suc');
  seg($('daySeg'), [['TODOS','Semana'], ...DAYS.map(d => [d,DAYNAME[d]])], 'day');
  const v = visible(); viewData=RutasVista.resumir(v,S.D.plan,S.suc); drawPoints(v);
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

let loadRequest=0;
async function load(keepCard) {
  const request=++loadRequest;
  try {
    const params=new URLSearchParams({activos:$('activeClients').value,dias_asignados:$('assignedDays').value});
    const data=await api('/datos?'+params);
    if(request!==loadRequest)return;
    S.D=data;
    byId = new Map(S.D.clientes.map(c => [c.id, c]));
    
    render(); renderCard();
    if(!mapPositioned){const points=visible().filter(c=>isGeo(c)&&!c.far);if(points.length){map.fitBounds(points.map(c=>[c.lat,c.lng]),{padding:[30,30],maxZoom:13});mapPositioned=true}}
    if(!S.D.clientes.length)$('sub').textContent='No hay clientes cargados para visualizar.';
  } catch (e) { if(request===loadRequest)$('sub').textContent = 'No se pudieron cargar los datos: ' + e.message; }
}
$('refreshView').onclick=()=>load();
for(const id of ['activeClients','assignedDays'])$(id).onchange=()=>{S.sel=null;S.flt=null;renderCard();load()};
load();
})();
