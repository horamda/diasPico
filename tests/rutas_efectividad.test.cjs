const {test}=require('node:test');
const assert=require('node:assert/strict');
const {analizar}=require('../app/rutas/static/rutas/efectividad.js');

// Período: lunes 2026-09-07 a domingo 2026-09-27 (3 semanas). Visita los lunes; la factura llega el martes.
const fechas=(cl)=>({desde:'2026-09-07',hasta:'2026-09-27',clientes:cl});
const c=(id,vis,extra={})=>({id,n:'C'+id,loc:'PUEBLO',suc:'DOLORES',d:'MA',vis,an:false,...extra});

test('cuenta visitas por semana y venta antes de la visita siguiente',()=>{
 const r=analizar([c(1,'LU')],fechas({1:[['2026-09-08',1],['2026-09-16',0]]}));
 const x=r.clientes[0];
 // Lunes 7, 14 y 21: el ciclo del 21 termina el 28 (fuera del período) y no cuenta.
 assert.equal(x.visitas,2);
 assert.equal(x.efectivas,2,'martes 8 y miércoles 16 caen en sus ciclos');
 assert.equal(x.pct,1);
 assert.equal(x.semanas,3);
 assert.equal(x.semCompra,2);
 assert.equal(x.bees,.5);
 assert.equal(r.porDia.find(d=>d.dia==='LU').visitas,2);
});
test('dos visitas por semana con una compra semanal dan 50%',()=>{
 const r=analizar([c(2,'LUJU')],fechas({2:[['2026-09-08',1],['2026-09-15',1],['2026-09-22',1]]}));
 const x=r.clientes[0];
 assert.equal(x.visitas,5,'lu7 ju10 lu14 ju17 lu21 (ju24 termina el 28)');
 assert.equal(x.efectivas,3);
 assert.equal(x.semCompra,3);
});
test('agrupa por localidad, marca clientes sin ventas y excluye inactivos',()=>{
 const r=analizar([c(1,'LU'),c(3,'LU'),c(4,'LU',{an:true})],fechas({1:[['2026-09-08',0]]}));
 assert.equal(r.resumen.clientes,2);
 assert.equal(r.resumen.ceros,1);
 const l=r.localidades[0];
 assert.equal(l.loc,'PUEBLO'); assert.equal(l.visitas,4); assert.equal(l.efectivas,1);
 assert.equal(r.clientes[0].id,3,'primero el de menor efectividad');
});
