const {test}=require('node:test');
const assert=require('node:assert/strict');
const {crear,csv}=require('../app/rutas/static/rutas/prioridades.js');

function element() {
  let html='', nodes=new Map();
  return {get innerHTML(){return html;},set innerHTML(value){html=value;nodes=new Map();},
    querySelector(selector){const key=selector.slice(1,-1);if(!html.includes(key))return null;if(!nodes.has(key))nodes.set(key,{});return nodes.get(key);},
    querySelectorAll(selector){const key=selector.slice(1,-1);return [...html.matchAll(new RegExp(key+'="([^"]+)"','g'))].map(m=>({dataset:{[key.slice(5)]:m[1]}}));}};
}
test('cambiar sucursal descarta respuestas en vuelo y permite volver a consultar',async()=>{
  const el=element();let suc='A',resolve,urls=[];
  const ui=crear({el,api:url=>{urls.push(url);return new Promise(r=>resolve=r);},sucursal:()=>suc,verCliente:()=>{}});
  ui.render();const task=el.querySelector('[data-generar]').onclick();
  suc='B';ui.render();resolve({disponible:false,suc:'A'});await task;
  assert.match(el.innerHTML,/B · todos/);assert.doesNotMatch(el.innerHTML,/No hay ventas importadas/);
  const task2=el.querySelector('[data-generar]').onclick();resolve({disponible:false,suc:'B'});await task2;
  assert.match(urls[1],/suc=B/);assert.match(el.innerHTML,/No hay ventas importadas/);
});
test('un error de consulta se informa sin dejar el control bloqueado',async()=>{
  const el=element();const ui=crear({el,api:async()=>{throw Error('<fallo>');},sucursal:()=> 'A',verCliente:()=>{}});
  ui.render();await el.querySelector('[data-generar]').onclick();
  assert.match(el.innerHTML,/&lt;fallo&gt;/);assert.doesNotMatch(el.innerHTML,/data-generar disabled/);
});
test('CSV conserva unidades, fechas, rechazos y neutraliza fórmulas en textos',()=>{
  const r={suc:'A',desde:'2026-10-01',hasta:'2026-10-07',anterior_desde:'2026-09-24',anterior_hasta:'2026-09-30',
    rutas:[],localidades:[],rechazos:[{suc:'A',dia:'LU',motivo:'CERRADO',comprobantes:2,clientes:1,bultos:3}],calidad_origen:{filas_sin_cliente:1},historial_suficiente:true,dias_desactualizacion:0};
  const result=csv(r,[{nivel:'alta',tipo:'caida',suc:'A',loc:'Centro',id:1,nombre:'=HYPERLINK("x")',evidencia:'50 → 20',accion:'Revisar',bultos:-3,hl:2,pallets:.5,bultos_sin_bxp:0}]);
  assert.match(result,/2026-10-01/);assert.match(result,/'=HYPERLINK\(""x""\)/);
  assert.match(result,/"-3";"2";"0.5"/);assert.match(result,/"CERRADO";"2";"1";"3"/);
});
