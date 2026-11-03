/* Shared calculations: every card and map uses the same selected clients. */
(function(root){
  const DAYS=['LU','MA','MI','JU','VI','SA'];
  function filtrar(clientes,{suc='TODAS',day='TODOS',q=''}={},extra=()=>true){
    const term=q.trim().toUpperCase();
    return clientes.filter(c=>(suc==='TODAS'||c.suc===suc)
      &&(day==='TODOS'||c.d.includes(day))
      &&(!term||[c.id,c.n,c.rs,c.dom].some(v=>String(v??'').toUpperCase().includes(term)))
      &&extra(c));
  }
  function resumir(clientes,plan,sucursal='TODAS'){
    const groups=new Map();
    for(const c of clientes){
      const key=JSON.stringify([c.suc,c.loc]);
      if(!groups.has(key))groups.set(key,{suc:c.suc,loc:c.loc,clientes:0,sin_geo:0,sin_dias:0,...Object.fromEntries(DAYS.map(d=>[d,0]))});
      const r=groups.get(key);r.clientes++;r.sin_geo+=Number(c.lat==null||c.lng==null);r.sin_dias+=Number(!c.d);
      for(const day of DAYS)r[day]+=Number(c.d.includes(day));
    }
    const carga={};
    const vehicles=plan.vehiculos.filter(v=>sucursal==='TODAS'||v.deposito===sucursal);
    for(const day of DAYS){
      const covered=new Set(),uses=new Map();
      for(const v of vehicles)for(const loc of v.plan[day]||[]){const key=JSON.stringify([v.deposito,loc]);uses.set(key,(uses.get(key)||0)+1);covered.add(key)}
      const vehiculos=vehicles.map(v=>{
        const paradas=(v.plan[day]||[]).map(loc=>({loc,n:clientes.filter(c=>c.suc===v.deposito&&c.loc===loc&&c.d.includes(day)).length,compartida:uses.get(JSON.stringify([v.deposito,loc]))>1}));
        return {id:v.id,nombre:v.nombre,deposito:v.deposito,color:v.color,capacidad:v.capacidad_clientes,paradas,total:paradas.reduce((n,p)=>n+p.n,0)};
      });
      const missing=new Map();
      for(const c of clientes)if(c.d.includes(day)&&!covered.has(JSON.stringify([c.suc,c.loc]))){const key=JSON.stringify([c.suc,c.loc]);if(!missing.has(key))missing.set(key,{loc:c.loc,suc:c.suc,n:0});missing.get(key).n++}
      carga[day]={vehiculos,sin_camion:[...missing.values()].sort((a,b)=>a.loc.localeCompare(b.loc))};
    }
    return {por_localidad:[...groups.values()].sort((a,b)=>a.suc.localeCompare(b.suc)||b.clientes-a.clientes),carga};
  }
  function indicadores(clientes, dias, ventas, efectividad) {
    const activos=clientes.filter(c=>!c.an), ids=new Set(activos.map(c=>c.id));
    const elegidos=dias.length?dias:DAYS;
    const programados=elegidos.reduce((n,d)=>n+activos.filter(c=>(c.d||'').includes(d)).length,0);
    const filas=(efectividad?.clientes||[]).filter(c=>ids.has(c.id));
    const ciclos=filas.reduce((n,c)=>n+c.visitas,0), efectivos=filas.reduce((n,c)=>n+c.efectivas,0);
    const carga=activos.reduce((n,c)=>n+(ventas?.clientes[c.id]?.drop||0),0);
    return {clientes:clientes.length, activos:activos.length, promedio:programados/elegidos.length,
      compradores:ventas?activos.filter(c=>ventas.clientes[c.id]?.compras>0).length:null,
      carga:ventas?carga:null, ciclos, efectivos, efectividad:ciclos?efectivos/ciclos:null};
  }
  function alertas(clientes, plan, dias=DAYS) {
    const activos=clientes.filter(c=>!c.an), cubiertas=new Set();
    for(const v of plan.vehiculos)for(const d of dias)for(const loc of v.plan[d]||[])cubiertas.add(JSON.stringify([v.deposito,loc,d]));
    return {sinDias:activos.filter(c=>!c.d).length,
      sinGeo:activos.filter(c=>c.lat==null||c.lng==null).length,
      sinCamion:activos.filter(c=>dias.some(d=>c.d.includes(d)&&!cubiertas.has(JSON.stringify([c.suc,c.loc,d])))).length};
  }
  const api={filtrar,resumir,indicadores,alertas};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.RutasVista=api;
})(typeof globalThis!=='undefined'?globalThis:this);
