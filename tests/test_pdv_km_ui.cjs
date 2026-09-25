const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness() {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, {
      value: id === 'pdvKmRate' ? '2500' : '', innerHTML: '', textContent: '', disabled: false,
      handlers: {}, addEventListener(event, cb) { this.handlers[event] = cb; },
      checkValidity() { return true; }, reportValidity() {}
    });
    return elements.get(id);
  };
  const requests = [];
  const context = { window: {}, document: {getElementById: get}, URLSearchParams, AbortController,
    Date, setTimeout, fetch(url, options) { return new Promise(resolve => requests.push({url, options, resolve})); }
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/pdv-km-cost.js'), 'utf8'), context);
  return {get, requests, render: context.window.renderPdvKmCosts};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function response(cost = 20000, items) {
  return {ok: true, json: async () => ({ok: true, data: {
    configurado: true, tarifa: 2500, desde: '2026-09-01', hasta: '2026-09-30', mensaje: 'Cálculo',
    items: items || [{cliente:'1',nombre:'<script>malicious</script>',sucursal:'1',cluster:'Ganador',
      atenciones:1,atenciones_con_km:1,pendientes:0,km_asignados:8,costo:cost,costo_por_atencion:cost,
      costo_por_bulto:2000,costo_sobre_venta:20,estado:'Calculado',visitas:[]}]
  }})};
}
(async () => {
  const h = harness();
  h.render({sucursal:'1',q:''});
  assert.match(h.requests[0].url, /tarifa=2500/);
  assert.match(h.requests[0].url, /metodo=prorrateo/);
  h.requests[0].resolve(response()); await tick();
  assert.match(h.get('pdvKmTable').innerHTML, /20\.000,00/);
  assert.match(h.get('pdvKmTable').innerHTML, /&lt;script&gt;/);
  assert.doesNotMatch(h.get('pdvKmTable').innerHTML, /<script>/);
  assert.equal(h.get('pdvKmExport').disabled, false);
  h.render({sucursal:'1',q:'no coincide'});
  assert.match(h.get('pdvKmTable').innerHTML, /Sin clientes/);
  assert.equal(h.requests.length, 1);
  h.get('pdvKmRate').value = '3000';
  h.get('pdvKmForm').handlers.submit({preventDefault(){}});
  assert.match(h.requests[1].url, /tarifa=3000/);
  h.render({sucursal:'2',q:''});
  assert.equal(h.requests[1].options.signal.aborted, true);
  h.requests[2].resolve(response(25000)); await tick();
  h.requests[1].resolve(response(999999)); await tick();
  assert.match(h.get('pdvKmTable').innerHTML, /25\.000,00/);
  assert.doesNotMatch(h.get('pdvKmTable').innerHTML, /999\.999/);
  h.get('pdvKmMethod').value = 'tramos';
  h.get('pdvKmMethod').handlers.change();
  assert.match(h.requests[3].url, /metodo=tramos/);
  const missing = harness();
  missing.render({});
  missing.requests[0].resolve({ok:true,json:async()=>({ok:true,data:{configurado:false,mensaje:'Falta conectar'}})});
  await tick();
  assert.equal(missing.get('pdvKmStatus').textContent, 'Falta conectar');
  assert.equal(missing.get('pdvKmTable').innerHTML, '');
  assert.equal(missing.get('pdvKmExport').disabled, true);
  console.log('PDV km UI: tariff, rendering, escaping, filters, stale responses and missing connection OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
