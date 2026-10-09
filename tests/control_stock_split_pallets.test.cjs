const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {test}=require('node:test');
const html=fs.readFileSync('app/templates/control_stock.html','utf8');
const src=html.slice(html.indexOf('function splitPallets('),html.indexOf('function splitPalletsHtml('));
const c={};vm.createContext(c);vm.runInContext(src,c);

test('726 bultos con pallets de 50 separa 700 cerrados y 26 sueltos',()=>{
  const sp=c.splitPallets(726,50);
  assert.equal(sp.pallets,14);assert.equal(sp.cerrados,700);assert.equal(sp.sueltos,26);
});
test('cantidad exacta no deja sueltos y sin dato de pallet no separa',()=>{
  assert.equal(c.splitPallets(700,50).sueltos,0);
  assert.equal(c.splitPallets(726,0),null);
  assert.equal(c.splitPallets(30,50).cerrados,0);
});
