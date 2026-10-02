const {test}=require('node:test');
const assert=require('node:assert/strict');
const {filtrar,resumir}=require('../app/rutas/static/rutas/vista.js');
const clientes=[
 {id:1,n:'Uno',rs:'',dom:'',suc:'CHASCOMUS',loc:'CASTELLI',d:'LUJU',lat:-36,lng:-57},
 {id:2,n:'Dos',rs:'',dom:'',suc:'CHASCOMUS',loc:'CASTELLI',d:'MA',lat:-36,lng:-57},
 {id:3,n:'Tres',rs:'',dom:'',suc:'DOLORES',loc:'DOLORES',d:'LU',lat:null,lng:null},
 {id:4,n:'Cuatro',rs:'',dom:'',suc:'DOLORES',loc:'DOLORES',d:'',lat:-36,lng:-57},
];
const plan={vehiculos:[{id:1,nombre:'Camión',deposito:'CHASCOMUS',plan:{LU:['CASTELLI'],MA:['CASTELLI']}}]};
test('lunes actualiza mapa, localidades y carga con los mismos clientes',()=>{
 const visible=filtrar(clientes,{day:'LU'}),summary=resumir(visible,plan);
 assert.deepEqual(visible.map(c=>c.id),[1,3]);
 assert.equal(summary.por_localidad.reduce((n,r)=>n+r.clientes,0),2);
 assert.equal(summary.por_localidad.reduce((n,r)=>n+r.sin_geo,0),1);
 assert.equal(summary.carga.LU.vehiculos[0].total,1);
 assert.equal(summary.carga.LU.sin_camion[0].n,1);
 assert.equal(summary.carga.MA.vehiculos[0].total,0);
});
test('sucursal y día se combinan y excluyen huérfanos de otras sucursales',()=>{
 const visible=filtrar(clientes,{day:'LU',suc:'CHASCOMUS'});
 const summary=resumir(visible,plan,'CHASCOMUS');
 assert.deepEqual(visible.map(c=>c.id),[1]);
 assert.equal(summary.carga.LU.sin_camion.length,0);
});
test('búsqueda, indicadores y selección vacía conservan totales coherentes',()=>{
 assert.equal(filtrar(clientes,{day:'LU',q:'Dos'}).length,0);
 const summary=resumir([],plan);
 assert.equal(summary.por_localidad.length,0);
 assert.equal(summary.carga.LU.vehiculos[0].total,0);
 assert.equal(filtrar(clientes,{day:'TODOS'},c=>!c.d)[0].id,4);
});
test('un vehículo de otra sucursal no cubre la localidad reasignada',()=>{
 const summary=resumir(filtrar(clientes,{day:'LU'}),{vehiculos:[{id:9,deposito:'DOLORES',plan:{LU:['CASTELLI']}}]});
 assert.equal(summary.carga.LU.vehiculos[0].total,0);
 assert.equal(summary.carga.LU.sin_camion.find(r=>r.loc==='CASTELLI').n,1);
});
