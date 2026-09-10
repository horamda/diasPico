const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {test}=require('node:test');
const html=fs.readFileSync('app/templates/control_stock.html','utf8');
const load=html.slice(html.indexOf('async function loadControlFrescura('),html.indexOf('async function loadDiferenciasFrescura('));
function context(overrides={}){
  const control={disabled:false};
  const c={URLSearchParams,frescuraLoading:false,frescuraDirty:true,frescuraDiscardApproved:false,
    frescuraContext:{fecha:'2026-09-09',sucursal:'1'},
    fechaFrescura:{value:'2026-09-10'},sucursalFrescura:{value:'1'},
    document:{querySelectorAll:()=>[control]},frescuraControlStatus:{textContent:''},
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
