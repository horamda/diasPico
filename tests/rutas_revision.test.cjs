const {test}=require('node:test');
const assert=require('node:assert/strict');
const {analizar,diasFacturados}=require('../app/rutas/static/rutas/revision.js');

// Ranchos: día cargado VI, pero todos facturan los sábados. Pueblo: LUJU con un MISA en el medio.
const cli=(id,loc,d,lat,lng,extra={})=>({id,n:'C'+id,dom:'',suc:'CHASCOMUS',loc,d,lat,lng,an:false,far:false,...extra});
const clientes=[
 ...[1,2,3,4,5,6].map(i=>cli(i,'RANCHOS','VI',-35.5+i*.001,-58.3)),
 ...[10,11,12,13,14,15,16,17].map(i=>cli(i,'PUEBLO','LUJU',-36+(i%4)*.001,-57+Math.floor(i/4)*.001)),
 cli(20,'PUEBLO','MISA',-35.9985,-56.9975),
 cli(30,'COSTA','',-37,-56.7),
 cli(40,'RANCHOS','VI',-35.5,-58.3,{an:true}),
];
const ent=e=>({compras:Object.values(e).reduce((a,b)=>a+b,0),ent:e});
const ventas={dias:70,desde:'2026-07-01',hasta:'2026-09-08',clientes:{
 1:ent({SA:9,VI:1}),2:ent({SA:8}),3:ent({SA:6}),4:ent({SA:7}),5:ent({SA:5}),6:ent({SA:6,VI:1}),
 10:ent({LU:5,JU:5}),11:ent({LU:4,JU:6}),12:ent({LU:5,JU:4}),13:ent({LU:5,JU:5}),14:ent({LU:3,JU:5}),15:ent({LU:5,JU:5}),16:ent({LU:5,JU:5}),17:ent({LU:5,JU:5}),
 20:ent({LU:4,JU:5,MI:1}),
 30:ent({MA:4,VI:5}),
}};

test('días facturados: los que reúnen 20% o más, en orden de semana',()=>{
 assert.equal(diasFacturados({JU:5,LU:4,MI:1}),'LUJU');
 assert.equal(diasFacturados({}),'');
});
test('localidad con el día mal cargado se marca entera',()=>{
 const r=analizar(clientes,ventas);
 const ranchos=r.localidades.find(f=>f.loc==='RANCHOS');
 assert.equal(ranchos.clientes,6,'los inactivos no cuentan');
 assert.match(ranchos.notas[0].m,/Día cargado VI, se entrega SA/);
 const c1=r.clientes.find(x=>x.id===1);
 assert.deepEqual(c1.motivos,['fuera']);
 assert.equal(c1.sugerido,'SA');
});
test('cliente con días distintos a sus vecinos y que factura como ellos',()=>{
 const r=analizar(clientes,ventas);
 const c=r.clientes.find(x=>x.id===20);
 assert.ok(c.motivos.includes('aislado'));
 assert.ok(c.motivos.includes('fuera'));
 assert.equal(c.vecinos,'LUJU');
 assert.equal(c.sugerido,'LUJU');
 assert.ok(!r.clientes.some(x=>x.id===10),'los que están bien no se listan');
});
test('sin días: se sugiere el patrón según la facturación',()=>{
 const r=analizar(clientes,ventas);
 const c=r.clientes.find(x=>x.id===30);
 assert.deepEqual(c.motivos,['sindias']);
 assert.equal(c.sugerido,'MAVI');
 assert.equal(r.localidades.find(f=>f.loc==='COSTA').notas[0].m,'Sin días cargados');
});
test('filtra por sucursal',()=>{
 const r=analizar(clientes,ventas,{suc:'DOLORES'});
 assert.equal(r.resumen.activos,0);
 assert.equal(r.clientes.length,0);
});
test('día de visita cargado como entrega: se marca y se sugiere el día siguiente',()=>{
 const {trasVisita}=require('../app/rutas/static/rutas/revision.js');
 assert.equal(trasVisita('VI'),'SA');
 assert.equal(trasVisita('MISA'),'LUJU');
 assert.equal(trasVisita('DO'),'');
 const cs=[1,2,3].map(i=>cli(50+i,'LAVALLE','LU',-36.4+i*.001,-56.9,{vis:'LU'}));
 cs.push(cli(60,'NUEVO','',-36.5,-56.8,{vis:'MI'}));
 const r=analizar(cs,{dias:70,clientes:{51:ent({MA:6}),52:ent({MA:5,LU:1}),53:ent({MA:7})}});
 assert.match(r.localidades.find(f=>f.loc==='LAVALLE').notas[0].m,/Cargado el día de visita/);
 const c=r.clientes.find(x=>x.id===51);
 assert.ok(c.motivos.includes('visita'));
 assert.equal(c.visita,'LU');
 assert.equal(c.sugerido,'MA');
 assert.equal(r.clientes.find(x=>x.id===60).sugerido,'JU','sin compras: visita + 1 día');
 assert.equal(r.resumen.visita,3);
});
