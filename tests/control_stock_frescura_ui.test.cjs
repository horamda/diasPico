const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {test}=require('node:test');
const html=fs.readFileSync('app/templates/control_stock.html','utf8');
const load=html.slice(html.indexOf('async function loadControlFrescura('),html.indexOf('async function loadDiferenciasFrescura('));
function context(overrides={}){
  const control={disabled:false};
  const c={URLSearchParams,frescuraSession:null,frSessionControls(){},frescuraLoading:false,frescuraDirty:true,frescuraDiscardApproved:false,
    frescuraContext:{fecha:'2026-09-09',sucursal:'1'},
    fechaFrescura:{value:'2026-09-10'},sucursalFrescura:{value:'1'},
    document:{querySelectorAll:()=>[control],getElementById:()=>({value:""})},frescuraControlStatus:{textContent:''},
    confirmarRecargaFrescura:async()=>false,today:()=> '2026-09-10',
    fetch:async()=>{throw Error('Unexpected request')},...overrides};
  vm.createContext(c);vm.runInContext(load,c);return {c,control};
}
test('cancel keeps edits and restores date without requesting stock',async()=>{
  const {c}=context();await c.loadControlFrescura(true);
  assert.equal(c.fechaFrescura.value,'2026-09-09');
  assert.equal(c.frescuraDirty,true);assert.equal(c.frescuraLoading,false);
});
test('network failure preserves edits and enables retry',async()=>{
  const {c,control}=context({confirmarRecargaFrescura:async()=>true,fetch:async()=>{throw Error('Offline')}});
  await c.loadControlFrescura(true);
  assert.equal(c.frescuraDirty,true);assert.equal(control.disabled,false);
  assert.equal(c.frescuraLoading,false);assert.match(c.frescuraControlStatus.textContent,/Offline/);
});
test('forced reload sends one request and concurrent click is ignored',async()=>{
  let calls=0;let requested='';
  const {c}=context({frescuraDirty:false,confirmarRecargaFrescura:async()=>true,
    fetch:async url=>{calls++;requested=url;throw Error('Stop after request')}});
  await Promise.all([c.loadControlFrescura(true),c.loadControlFrescura(true)]);
  assert.equal(calls,1);assert.match(requested,/force_sync=1/);
  assert.match(requested,/frescura-planilla/);
});
test('template inline scripts parse',()=>{
  for(const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)){
    const source=match[1].replace(/\{\{[\s\S]*?\}\}/g,'null');
    new vm.Script(source);
  }
});
const distributionCode=html.slice(html.indexOf('function botonDistribucionFrescura('),html.indexOf('function frescuraInput('));
test('pallet distribution applies 1800 bultos and retains three expiry dates',()=>{
  const elements=new Map();
  const row={codigo_articulo:'7634',descripcion_articulo:'Producto',stock_sistema_bultos:1800,stock_sistema_unidades:0,
    fecha_vencimiento_sistema:'2026-10-01',distribucion_fechas:[
      {referencia:'Pallets 1 al 10',bultos:1000,unidades:0,fecha_vencimiento:'2026-10-01',revision:'OK'},
      {referencia:'Pallets 11 al 16',bultos:600,unidades:0,fecha_vencimiento:'2026-11-01',revision:'NO_OK'},
      {referencia:'Pallets 17 y 18',bultos:200,unidades:0,fecha_vencimiento:'2026-12-01',revision:'NO_OK'}]};
  const c={structuredClone,frescuraSession:{estado:'activo'},frScheduleDraft(){},frSessionControls(){},frescuraRows:[row],frescuraDirty:false,fechaFrescura:{value:'2026-09-09'},
    esc:String,fechaCorta:String,parseLocalDate:v=>new Date(v),estadoFrescuraDesdeDias:()=> 'CRITICO',
    modalOverlay:{innerHTML:'',classList:{add(){}}},closeModal(){},renderFrescuraMobileCards(){},actualizarTotalesFrescura(){},
    document:{body:{style:{}},querySelectorAll:()=>[],getElementById:id=>{
      if(!elements.has(id)) elements.set(id,{style:{}});return elements.get(id);
    }}};
  vm.createContext(c);vm.runInContext(distributionCode,c);c.abrirDistribucionFrescura(0);
  elements.get('frApplyGroups').onclick();
  assert.equal(row._control_b,1800);assert.equal(row.distribucion_fechas.length,3);
  assert.equal(row.fecha_vencimiento,'2026-10-01');assert.equal(c.frescuraDirty,true);
});
test('1800 bultos with 100 per pallet creates 18 pending physical checks',()=>{
  const elements=new Map();
  const row={codigo_articulo:'7634',descripcion_articulo:'Producto',stock_sistema_bultos:1800,stock_sistema_unidades:0,bultos_por_pallet:100,fecha_vencimiento_sistema:'2026-10-01'};
  const c={structuredClone,frescuraSession:{estado:'activo'},frScheduleDraft(){},frSessionControls(){},frescuraRows:[row],frescuraDirty:false,fechaFrescura:{value:'2026-09-09'},
    esc:String,fechaCorta:String,parseLocalDate:v=>new Date(v),estadoFrescuraDesdeDias:()=> 'CRITICO',
    modalOverlay:{innerHTML:'',classList:{add(){}}},closeModal(){},renderFrescuraMobileCards(){},actualizarTotalesFrescura(){},
    document:{body:{style:{}},querySelectorAll:()=>[],getElementById:id=>{if(!elements.has(id))elements.set(id,{style:{}});return elements.get(id)}}};
  vm.createContext(c);vm.runInContext(distributionCode,c);c.abrirDistribucionFrescura(0);
  assert.match(elements.get('frDistributionRows').innerHTML,/Pallet 18/);
  elements.get('frApplyGroups').onclick();
  assert.equal(row.distribucion_fechas.length,18);
  assert.ok(row.distribucion_fechas.every(g=>g.revision==='PENDIENTE'));
  assert.equal(row._control_b,1800);
});
const sessionSource=fs.readFileSync('app/static/control_frescura_session.js','utf8');
test('pending physical checks cannot be counted as fully reviewed',()=>{
  const source=sessionSource.slice(sessionSource.indexOf('function frReviewed('),sessionSource.indexOf('function frNoOkTable('));
  const c={};vm.createContext(c);vm.runInContext(source,c);
  assert.equal(c.frReviewed({_control_ok:'PENDIENTE'}),false);
  assert.equal(c.frReviewed({distribucion_fechas:[{revision:'OK'},{revision:'PENDIENTE'}]}),false);
  assert.equal(c.frReviewed({distribucion_fechas:[{revision:'OK'},{revision:'NO_OK'}]}),true);
});
test('session script parses and historical missing time is not zero',()=>{
  new vm.Script(sessionSource);
  const source=sessionSource.slice(sessionSource.indexOf('function frDuration('),sessionSource.indexOf('function frBranch('));
  const c={};vm.createContext(c);vm.runInContext(source,c);
  assert.equal(c.frDuration(null),'Sin medicion');
  assert.equal(c.frDuration(900),'00:15:00');
  assert.equal(c.frDuration(90000),'25:00:00');
});

test('workflow guides preparation, paused review, completion and final result',()=>{
  const elements=new Map();
  const c={frescuraRows:[{_control_ok:'PENDIENTE'},{_control_ok:'OK'}],frescuraSession:null,
    document:{getElementById(id){if(!elements.has(id))elements.set(id,{setAttribute(k,v){this[k]=v},removeAttribute(k){delete this[k]}});return elements.get(id)}}};
  vm.createContext(c);
  vm.runInContext(sessionSource.slice(sessionSource.indexOf('function frReviewed('),sessionSource.indexOf('function frNoOkTable(')),c);
  vm.runInContext(sessionSource.slice(sessionSource.indexOf('function frUpdateWorkflow('),sessionSource.indexOf('let frLastPending')),c);
  c.frUpdateWorkflow();
  assert.equal(elements.get('frStepPrepare')['aria-current'],'step');
  assert.equal(elements.get('frNextPending').disabled,true);
  c.frescuraSession={estado:'activo'};c.frUpdateWorkflow();
  assert.equal(elements.get('frStepReview')['aria-current'],'step');
  assert.equal(elements.get('frNextPending').disabled,false);
  assert.equal(elements.get('frReviewProgress').value,1);
  c.frescuraSession.estado='pausado';c.frUpdateWorkflow();
  assert.equal(elements.get('frNextPending').disabled,true);
  c.frescuraSession.estado='activo';c.frescuraRows[0]._control_ok='NO_OK';c.frUpdateWorkflow();
  assert.equal(elements.get('frStepFinish')['aria-current'],'step');
  assert.equal(elements.get('frNextPending').disabled,true);
  c.frescuraSession.estado='finalizado';c.frUpdateWorkflow();
  assert.match(elements.get('frReviewHint').textContent,/finalizado/);
});

for(const syncStatus of [undefined,{estado_alerta:'ok',auto_sync:{ok:true}}]){
  test(`successful lot load with ${syncStatus?'available':'missing'} sync status`,async()=>{
    let rendered=false;
    const row={codigo_articulo:'7634',lote:'L1',stock_sistema_bultos:25};
    const {c}=context({confirmarRecargaFrescura:async()=>true,
      fetch:async()=>({ok:true,json:async()=>({ok:true,fecha:'2026-09-10',sucursal:'1',dia:'jueves',rows:[row],total_lotes:1,frescura_status:syncStatus})}),
      observacionesFrescura:{value:''},frFecha:{},frArticulos:{},frLotes:{},frTotal:{},
      fechaCorta:String,fmt:{format:String},renderControlFrescuraRows(){rendered=true},
      actualizarTotalesFrescura(){},loadDiferenciasFrescura(){}});
    vm.runInContext(html.slice(html.indexOf('function mostrarEstadoFrescura('),html.indexOf('let sucursalesDisponibles')),c);
    c.document.getElementById=()=>({value:'',classList:{toggle(){}}});
    await c.loadControlFrescura();
    assert.equal(rendered,true);
    assert.equal(c.frescuraLoaded,true);
    assert.equal(c.frescuraRows[0],row);
    assert.equal(c.frescuraDirty,false);
    assert.match(c.frescuraControlStatus.textContent,/Planilla lista/);
  });
}
