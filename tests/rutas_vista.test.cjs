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
const {indicadores}=require('../app/rutas/static/rutas/vista.js');
test('indicadores ponderan ciclos y cuentan una sola vez al comparar dias',()=>{
 const cs=[{id:1,d:'LUJU',an:false},{id:2,d:'LU',an:false},{id:3,d:'LU',an:true}];
 const ventas={clientes:{1:{compras:2,drop:10},3:{compras:4,drop:99}}};
 const efe={clientes:[{id:1,visitas:2,efectivas:2},{id:2,visitas:8,efectivas:2},{id:3,visitas:5,efectivas:5},{id:9,visitas:9,efectivas:9}]};
 const r=indicadores(cs,['LU','JU'],ventas,efe);
 assert.equal(r.clientes,3);assert.equal(r.activos,2);assert.equal(r.promedio,1.5);
 assert.equal(r.compradores,1);assert.equal(r.carga,10);assert.equal(r.efectividad,.4);
 assert.equal(r.ciclos,10);assert.equal(r.efectivos,4);
});
test('indicadores distinguen falta de datos de cero ventas y cero efectividad',()=>{
 const cs=[{id:1,d:'LU',an:false}];
 const sin=indicadores(cs,[],null,null);
 assert.equal(sin.promedio,1/6);assert.equal(sin.compradores,null);assert.equal(sin.efectividad,null);
 const cero=indicadores(cs,['LU'],{clientes:{}},{clientes:[{id:1,visitas:2,efectivas:0}]});
 assert.equal(cero.compradores,0);assert.equal(cero.efectividad,0);
 assert.equal(indicadores([],[],null,null).promedio,0);
});
const {alertas}=require('../app/rutas/static/rutas/vista.js');
test('alertas cuentan clientes unicos y respetan sucursal y dias seleccionados',()=>{
 const cs=[{id:1,suc:'A',loc:'X',d:'LUJU',lat:1,lng:2},{id:2,suc:'B',loc:'X',d:'LU',lat:null,lng:null},{id:3,suc:'A',loc:'X',d:'',lat:1,lng:2},{id:4,suc:'A',loc:'X',d:'LU',an:true}];
 const plan={vehiculos:[{deposito:'A',plan:{LU:['X']}}]};
 assert.deepEqual(alertas(cs,plan,['LU']),{sinDias:1,sinGeo:1,sinCamion:1});
 assert.equal(alertas(cs,plan,['LU','JU']).sinCamion,2);
 assert.equal(alertas([],plan,['LU']).sinCamion,0);
});
