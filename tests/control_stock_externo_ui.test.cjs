const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {test}=require('node:test');
const html=fs.readFileSync('app/templates/control_stock.html','utf8');
const script=html.slice(html.indexOf('function mostrarExterno('),html.indexOf('function draftKey('));
function setup(fetch){
  const c={URLSearchParams,fetch,esc:s=>String(s).replaceAll('<','&lt;'),fmt:new Intl.NumberFormat('es-AR'),today:()=> '2026-10-01'};
  for(const id of ['externoNuevo','externoHistorial','extHistDetalle','extHistLista','extHistStatus','extHistSucursal','extHistDesde','extHistHasta','extHistResponsable','sucursalExterno','fechaExterno'])c[id]={value:'',hidden:false,innerHTML:'',textContent:'',scrollIntoView(){}};
  c.extHistSucursal.value='1';vm.createContext(c);vm.runInContext(script,c);return c;
}
test('history error clears previous results and explains failure',async()=>{
  const c=setup(async()=>{throw Error('Sin conexión')});c.extHistLista.innerHTML='old';
  await c.cargarHistorialExterno();assert.equal(c.extHistLista.innerHTML,'');assert.equal(c.extHistDetalle.hidden,true);assert.match(c.extHistStatus.textContent,/Sin conexión/);
});
test('saved result opens exact control and preserves selected branch',async()=>{
  const urls=[];const c=setup(async url=>{urls.push(url);return {ok:true,json:async()=>url.includes('conteo_id')?{ok:true,control:{id:23,fecha:'2026-09-25',responsable:'Externo'},items:[]}:{ok:true,rows:[]}}});
  c.fechaExterno.value='2026-09-25';await c.verResultadoExterno(23,'2');
  assert.equal(c.externoNuevo.hidden,true);assert.equal(c.externoHistorial.hidden,false);
  assert.match(urls[1],/conteo_id=23&sucursal=2/);assert.match(c.extHistDetalle.innerHTML,/#23/);
});
test('legacy detail shows missing reference and escapes descriptions',async()=>{
  const c=setup(async()=>({ok:true,json:async()=>({ok:true,control:{id:1},items:[{id_articulo:4,descripcion:'<script>',stock:10,stock_referencia_bultos:null}]})}));
  await c.cargarDetalleExterno(1,'1');assert.match(c.extHistDetalle.innerHTML,/Sin referencia histórica/);assert.ok(!c.extHistDetalle.innerHTML.includes('<script>'));
});
