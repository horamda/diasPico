const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../app/rutas/static/rutas/mapa.js'), 'utf8');
const context = vm.createContext({num: (n, d=0) => Number(n || 0).toFixed(d), esc: s => String(s)});
vm.runInContext(source.slice(source.indexOf('const palletTexto'), source.indexOf('const RADIOS')) + '\nthis.api = {cargaVacia, sumarCarga, agregarVolumenAnalisis, volumenAnalisisHTML, csvVolumenAnalisis};', context);
const api = context.api;
test('carga suma promedios por compra en las tres unidades y conserva faltantes', () => {
  const total = api.cargaVacia();
  api.sumarCarga(total, {drop:10, drop_hl:1, drop_pallets:.1});
  api.sumarCarga(total, {drop:20, drop_hl:2, drop_pallets:.4, bultos_sin_bxp:5});
  assert.equal(total.bultos,30); assert.equal(total.hl,3); assert.equal(total.pallets,.5);
  assert.equal(total.bultos_sin_bxp,5);
});
test('analisis agrupa por sucursal y localidad y exporta solamente clientes evaluados', () => {
  const result = {desde:'2026-10-01', hasta:'2026-10-07'};
  const clients = [{id:1,n:'Uno',suc:'A',loc:'Centro'}, {id:2,n:'Dos',suc:'B',loc:'Centro'}, {id:3,n:'Tres',suc:'A',loc:'Centro'}];
  api.agregarVolumenAnalisis(result, {clientes:{1:{bultos:10,hl:1,pallets:.1},2:{bultos:20,hl:2,pallets:.2,bultos_sin_bxp:5},4:{bultos:100,hl:100,pallets:100}}}, clients);
  assert.equal(result.volumen.bultos,30); assert.equal(result.volumen.hl,3);
  assert.equal(result.volumenLocalidades.length,2); assert.equal(result.volumenClientes.length,3);
  assert.match(api.volumenAnalisisHTML(result), /0.20 pallets\*/);
  const lines=[]; api.csvVolumenAnalisis(result,lines,String);
  assert.equal(lines.length,6); assert.match(lines[3], /A;Centro;1;Uno;10;1;0.1;0/);
  assert.match(lines[5], /A;Centro;3;Tres;0;0;0;0/);
});

test('paneles de localidades y ventas renderizan con y sin datos de volumen', () => {
  const panels = new Map();
  const element = id => { if (!panels.has(id)) panels.set(id, {innerHTML:'', querySelectorAll: () => []}); return panels.get(id); };
  Object.assign(context, {$:element, scope:()=>[], FLT:Object.fromEntries(['sindias','singeo','far','anulado'].map(k=>[k,()=>false])), venta:()=>null, isGeo:()=>true,
    viewData:{por_localidad:[]}, compActivo:()=>false, S:{day:'TODOS',periodo:7,V:null}, DAYS:['LU'],
    PERIODOS:[7,15,30,45,60,90,120], bindItems:()=>{}, money:n=>String(n)});
  vm.runInContext(source.slice(source.indexOf('function renderLoc()'), source.indexOf('function tablaComparar()')),context);
  vm.runInContext(source.slice(source.indexOf('function renderVen()'), source.indexOf('// ---------- recorridos')),context);
  vm.runInContext('renderLoc(); renderVen();',context);
  assert.match(element('p-ven').innerHTML, /No hay ventas/);
  context.S.V = {desde:'2026-10-01',hasta:'2026-10-07',dias:7};
  vm.runInContext('renderVen();',context);
  assert.match(element('p-ven').innerHTML, /pallets equivalentes/);
  assert.match(element('p-ven').innerHTML, /HL/);
});

test('recorrido con clientes y ventas renderiza las tres unidades sin bloquear el mapa',()=>{
  const panels=new Map();
  const element=id=>{if(!panels.has(id))panels.set(id,{innerHTML:'',querySelectorAll:()=>[]});return panels.get(id);};
  const clientes=[{id:1,suc:'A',loc:'Centro',d:'LU',an:false,lat:-36,lng:-57}];
  Object.assign(context,{$:element,baseSemana:()=>clientes,RutasVista:require('../app/rutas/static/rutas/vista.js'),
    DAYS:['LU'],DIASLARGO:{LU:'LUNES'},DAYNAME:{LU:'Lunes'},colorLoc:()=> '#123456',
    venta:()=>({drop:10,drop_hl:1,drop_pallets:.1}),S:{suc:'TODAS',V:{},D:{plan:{vehiculos:[{id:1,nombre:'Camion',deposito:'A',color:'#123456',capacidad_clientes:5,plan:{LU:['Centro']}}]}}}});
  vm.runInContext(source.slice(source.indexOf('function matrizLocalidades('), source.indexOf('// ---------- revisi')),context);
  vm.runInContext('renderRec();',context);
  assert.match(element('p-rec').innerHTML,/10.0 b/);assert.match(element('p-rec').innerHTML,/1.00 HL/);assert.match(element('p-rec').innerHTML,/0.10 pallets/);
});
