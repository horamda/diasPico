/* Prioridades operativas. Consulta explícita, filtros locales y exportación del resultado. */
(function(root) {
  const PERIODOS = [7,15,30,45,60,90,120];
  const LABEL = {sin_compras:'Sin compras',actividad:'Actividad interrumpida',sin_dias:'Sin días',ubicacion:'Ubicación a revisar',
    bxp:'BxP faltantes',frecuencia:'Frecuencia a revisar',caida:'Caída de volumen',rechazos:'Rechazos repetidos',
    distancia:'Alejado y bajo volumen',sin_camion:'Sin camión',compartida:'Carga compartida',capacidad:'Tope de clientes excedido'};
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = (v,d=1) => v == null ? '—' : Number(v).toLocaleString('es-AR',{maximumFractionDigits:d});
  const pct = v => v == null ? 'Sin base' : `${v>0?'+':''}${num(v*100,0)}%`;
  const vol = v => `${num(v.bultos)} b · ${num(v.hl,2)} HL · ${num(v.pallets,2)} pallets${v.bultos_sin_bxp ? '*' : ''}`;
  const table = (heads, rows) => `<div class="tw"><table><thead><tr>${heads.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.join('') || `<tr><td colspan="${heads.length}">Sin datos para esta selección.</td></tr>`}</tbody></table></div>`;
  const csvCell = v => { let s=String(v ?? ''); if (/^[=+@\-]/.test(s) && typeof v !== 'number') s="'"+s; return `"${s.replace(/"/g,'""')}"`; };
  function csv(r, alertas) {
    const rows=[['PRIORIDADES',r.suc,r.desde,r.hasta],['Nivel','Tipo','Sucursal','Localidad','Cliente','Nombre','Evidencia','Acción','Base del volumen','Bultos','HL','Pallets','Bultos sin BxP']];
    for(const a of alertas) rows.push([a.nivel,LABEL[a.tipo],a.suc,a.loc,a.id,a.nombre,a.evidencia,a.accion,a.tipo==='capacidad'?'Carga habitual estimada':'Volumen del periodo',a.bultos,a.hl,a.pallets,a.bultos_sin_bxp]);
    rows.push([],['CARGA ESTIMADA POR CAMION; NO SUMAR FILAS COMPARTIDAS'],['Sucursal','Camión','Día','Clientes','Tope clientes','Compartida','Bultos habituales','HL habituales','Pallets habituales','Bultos escenario alto','HL escenario alto','Pallets escenario alto','Clientes sin base','Bultos sin BxP']);
    for(const x of r.rutas) rows.push([x.suc,x.nombre,x.dia,x.clientes,x.capacidad_clientes,x.compartida?'SI':'NO',x.bultos,x.hl,x.pallets,x.alta.bultos,x.alta.hl,x.alta.pallets,x.sin_base,x.bultos_sin_bxp]);
    rows.push([],['EVOLUCION',r.anterior_desde,r.anterior_hasta,'vs',r.desde,r.hasta],['Sucursal','Localidad','Bultos','HL','Pallets','Bultos anteriores','HL anteriores','Pallets anteriores','Variación bultos (fracción)','Variación HL (fracción)','Variación pallets (fracción)','Concentración top 3']);
    for(const x of r.localidades) rows.push([x.suc,x.loc,x.bultos,x.hl,x.pallets,x.anterior.bultos,x.anterior.hl,x.anterior.pallets,x.variacion.bultos,x.variacion.hl,x.variacion.pallets,x.top3_pct]);
    rows.push([],['RECHAZOS POR FECHA DE COMPROBANTE'],['Sucursal','Día','Motivo','Comprobantes','Clientes','Bultos rechazados']);
    for(const x of r.rechazos) rows.push([x.suc,x.dia,x.motivo,x.comprobantes,x.clientes,x.bultos]);
    rows.push([],['CALIDAD GLOBAL'],...Object.entries(r.calidad_origen),['Días desde última fecha cargada',r.dias_desactualizacion],['Historial alcanza período anterior',r.historial_suficiente?'SI':'NO']);
    return '\ufeff'+rows.map(row=>row.map(csvCell).join(';')).join('\r\n');
  }
  function crear({el, api, sucursal, verCliente}) {
    const state={dias:60,res:null,busy:false,error:'',tipo:'',nivel:'',q:'',limite:100,request:0};
    const filtradas=()=>state.res.alertas.filter(a=>(!state.tipo||a.tipo===state.tipo)&&(!state.nivel||a.nivel===state.nivel)&&`${a.nombre} ${a.id??''} ${a.loc} ${a.suc}`.toLowerCase().includes(state.q.toLowerCase()));
    async function generar() {
      const request=++state.request, suc=sucursal(), dias=state.dias;
      state.busy=true;state.error='';state.res=null;render();
      try { const r=await api(`/ventas/prioridades?dias=${dias}&suc=${encodeURIComponent(suc)}`);
        if(request===state.request&&suc===sucursal()) state.res=r;
      } catch(e) { if(request===state.request)state.error=e.message; }
      finally { if(request===state.request){state.busy=false;render();} }
    }
    function render() {
      const r=state.res;
      const head=`<div class="rec-head"><div><h2>Prioridades operativas</h2><p class="note">${esc(sucursal())} · todos sus clientes activos. No aplica el filtro de día, búsqueda ni días asignados del mapa.</p></div>
        <div class="rv-acc"><div class="seg seg-sm" role="group" aria-label="Período del diagnóstico">${PERIODOS.map(d=>`<button data-prid="${d}" aria-pressed="${d===state.dias}" ${state.busy?'disabled':''}>${d} d</button>`).join('')}</div>
        <button class="btn primary" data-generar ${state.busy?'disabled':''}>${state.busy?'Analizando…':'Generar diagnóstico'}</button>${r?.disponible?'<button class="btn" data-csv>Descargar CSV</button><button class="btn" data-print>Imprimir informe</button>':''}</div></div>`;
      if(!r?.disponible) {
        el.innerHTML=head+`<p class="empty" role="status">${state.error?esc(state.error):state.busy?'Consultando ventas, historial y recorridos…':r?'No hay ventas importadas para analizar.':'Elegí el período y generá el diagnóstico.'}</p>`;
      } else {
        const alertas=filtradas();
        el.innerHTML=head+`<div class="pri-report">
          <p class="status">${r.clientes} clientes activos · ${esc(r.desde)} a ${esc(r.hasta)} · comparación: ${esc(r.anterior_desde)} a ${esc(r.anterior_hasta)}.</p>
          <div class="pri-notice"><b>Son señales para revisar, no entregas confirmadas.</b> Se usan comprobantes y el plan actual. La carga habitual suma promedios por compra; no son pedidos pendientes. No se modifica ninguna ruta.</div>
          ${r.dias_desactualizacion>2?`<p class="warn">Última fecha cargada hace ${r.dias_desactualizacion} días. Actividad calculada al cierre de esos datos, no a hoy.</p>`:''}
          ${r.dias_desactualizacion<0?'<p class="bad">Hay fechas futuras en ventas: revisar antes de decidir.</p>':''}
          ${!r.historial_suficiente?'<p class="warn">El historial no alcanza el inicio del período anterior. Comparaciones parciales; no se generan alertas de caída.</p>':''}
          ${r.dias<30?'<p class="note">Ventana corta: no se sugieren cambios de frecuencia; puede haber pocos ciclos para evaluar.</p>':''}
          <div class="vtot"><div><b>${r.alertas.filter(a=>a.nivel==='alta').length}</b><span>prioridad alta</span></div><div><b>${r.alertas.length}</b><span>señales (un cliente puede tener varias)</span></div><div><b>${num(r.volumen.hl,2)}</b><span>HL del período</span></div><div><b>${num(r.volumen.pallets,2)}${r.volumen.bultos_sin_bxp?'*':''}</b><span>pallets del período</span></div></div>
          <details><summary>Criterios y límites del análisis</summary><p>Inactivo: más de 45 días sin compra. En riesgo: más de 2,5 veces la frecuencia histórica y al menos 21 días. La frecuencia usa 120 días y exige 3 fechas de compra; las devoluciones no reactivan clientes.</p><p>Caída: al menos 30% en bultos y 3 compras en el período anterior. Frecuencia a revisar: 30 días o más, 3 compras, al menos 2 días asignados, compras semanales por debajo de la mitad de los días asignados y volumen por compra menor a la mitad de la mediana local (mínimo 5 clientes con volumen). Son umbrales de revisión, no decisiones automáticas.</p><p>Alejamiento: más de 5 km en línea recta al cliente más cercano de la misma sucursal con un día compartido, más bajo volumen local. No estima kilómetros de ruta ni rentabilidad. Concentración: porcentaje de bultos de los 3 mayores clientes. El histórico refleja datos importados; su antigüedad no garantiza que no falten importaciones.</p><p>* Pallets parciales cuando faltan BxP. No hay capacidad física de camiones en HL/pallets: la ocupación usa solo el tope de clientes disponible.</p></details>
          <h2>Qué revisar primero</h2>
          <div class="pri-categories">${r.resumen.map(x=>`<button class="btn" data-tipo="${x.tipo}" aria-pressed="${state.tipo===x.tipo}">${LABEL[x.tipo]} · ${x.alertas}<small>${x.clientes} clientes · ${vol(x)}</small></button>`).join('')||'<p>Sin alertas con los criterios actuales.</p>'}</div>
          <div class="rv-fil"><label>Prioridad <select data-nivel><option value="">Todas</option><option value="alta" ${state.nivel==='alta'?'selected':''}>Alta</option><option value="media" ${state.nivel==='media'?'selected':''}>Media</option></select></label><label>Cliente o localidad <input data-buscar type="search" value="${esc(state.q)}"></label><button class="btn" data-clear>Limpiar filtros</button><span>${alertas.length} señales</span></div>
          ${table(['Prioridad','Cliente / recorrido','Señal y evidencia','Acción sugerida','Volumen involucrado'],alertas.slice(0,state.limite).map(a=>`<tr><td class="${a.nivel==='alta'?'bad':'warn'}">${a.nivel}</td><td>${a.id!=null?`<button class="btn" data-cliente="${a.id}">#${a.id} ${esc(a.nombre)}</button>`:esc(a.nombre)}<small>${esc(a.suc)} · ${esc(a.loc)}</small></td><td><b>${LABEL[a.tipo]}</b><br>${esc(a.evidencia)}</td><td>${esc(a.accion)}</td><td>${a.id!=null||a.tipo==='capacidad'?vol(a):'No atribuible'}<small>${a.tipo==='capacidad'?'Carga habitual estimada':'Volumen del período; no es pérdida estimada'}</small></td></tr>`))}
          ${alertas.length>state.limite?'<button class="btn" data-mas>Mostrar 100 más</button>':''}
          <h2>Carga por día · clientes contados una vez por día</h2><p class="note">Compará días para detectar desequilibrios. Los clientes con varios días aparecen en cada uno; no sumar como volumen semanal vendido.</p>
          ${table(['Día','Clientes','Carga habitual','Escenario alto','Sin compras en ventana'],r.dias_carga.map(x=>`<tr><td>${x.dia}</td><td>${x.clientes}</td><td>${vol(x)}</td><td>${x.alta.bultos==null?'Base insuficiente':vol({...x.alta,bultos_sin_bxp:x.bultos_sin_bxp})}</td><td>${x.sin_base}</td></tr>`))}
          <h2>Carga y concentración por camión</h2><p class="note">Escenario alto = suma del percentil 90 por cliente (mínimo 5 fechas de compra por cliente); no es un pico simultáneo observado. La carga de localidades compartidas no se puede repartir sin asignación individual.</p>
          ${table(['Sucursal / camión','Día','Clientes / tope','Carga habitual','Escenario alto','Top 3 clientes','Base'],r.rutas.map(x=>`<tr><td>${esc(x.suc)}<br>${esc(x.nombre)}</td><td>${x.dia}</td><td class="${x.ocupacion_clientes>1?'bad':''}">${x.clientes} / ${x.capacidad_clientes||'sin tope'}${x.ocupacion_clientes!=null?`<small>${num(x.ocupacion_clientes*100,0)}% del tope de clientes</small>`:''}</td><td>${vol(x)}${x.compartida?'<small class="warn">Compartida: no sumar entre camiones</small>':''}</td><td>${x.alta.bultos==null?'Base insuficiente':vol({...x.alta,bultos_sin_bxp:x.bultos_sin_bxp})}</td><td>${x.top3_pct==null?'—':num(x.top3_pct*100,0)+'%'}</td><td>${x.sin_base} sin compras</td></tr>`))}
          <h2>Evolución por localidad</h2><p class="note">Períodos de ${r.dias} días completos y consecutivos, anclados en la última fecha importada. Sin base positiva anterior no se calcula porcentaje. Las devoluciones reducen el volumen neto.</p>
          ${table(['Sucursal / localidad','Actual','Anterior','Bultos / HL / pallets por semana','Variación bultos / HL / pallets','Top 3 clientes'],r.localidades.map(x=>`<tr><td>${esc(x.suc)}<br>${esc(x.loc)}</td><td>${vol(x)}</td><td>${vol(x.anterior)}</td><td>${num(x.bultos_sem)} / ${num(x.hl_sem,2)} / ${num(x.pallets_sem,2)}</td><td>${!r.historial_suficiente?'Historial parcial':`${pct(x.variacion.bultos)} / ${pct(x.variacion.hl)} / ${x.bultos_sin_bxp||x.anterior.bultos_sin_bxp?'Parcial':pct(x.variacion.pallets)}`}</td><td>${x.top3_pct==null?'—':num(x.top3_pct*100,0)+'%'}</td></tr>`))}
          <h2>Rechazos por sucursal, día y motivo</h2><p class="note">Día de la fecha del comprobante; no acredita el día de la visita física ni el camión que realizó la entrega.</p>
          ${table(['Sucursal','Día','Motivo','Comprobantes','Clientes','Bultos rechazados'],r.rechazos.map(x=>`<tr><td>${esc(x.suc)}</td><td>${x.dia}</td><td>${esc(x.motivo)}</td><td>${x.comprobantes}</td><td>${x.clientes}</td><td>${num(x.bultos)}</td></tr>`))}
          <h2>Calidad del origen · todas las sucursales</h2><p>${r.calidad_origen.filas_sin_cliente} líneas sin cliente vinculado · ${r.calidad_origen.filas_sin_articulo} sin artículo en maestro · ${r.calidad_origen.filas_sin_hl} de mercadería sin HL. Estas líneas pueden dejar incompletos los totales. En esta sucursal: ${num(r.volumen.bultos_sin_bxp)} bultos sin BxP.</p>
        </div>`;
      }
      el.querySelector('[data-generar]').onclick=generar;
      el.querySelectorAll('[data-prid]').forEach(b=>b.onclick=()=>{state.dias=+b.dataset.prid;state.res=null;state.limite=100;render();});
      el.querySelectorAll('[data-tipo]').forEach(b=>b.onclick=()=>{state.tipo=state.tipo===b.dataset.tipo?'':b.dataset.tipo;state.limite=100;render();});
      el.querySelectorAll('[data-cliente]').forEach(b=>b.onclick=()=>verCliente(+b.dataset.cliente));
      const on=(selector,event,fn)=>{const x=el.querySelector(selector);if(x)x[event]=fn;};
      on('[data-nivel]','onchange',e=>{state.nivel=e.target.value;state.limite=100;render();});
      on('[data-buscar]','onchange',e=>{state.q=e.target.value;state.limite=100;render();});
      on('[data-clear]','onclick',()=>{state.tipo='';state.nivel='';state.q='';state.limite=100;render();});
      on('[data-mas]','onclick',()=>{state.limite+=100;render();});
      on('[data-csv]','onclick',()=>{const blob=new Blob([csv(r,filtradas())],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`prioridades_${r.suc}_${r.hasta}_${r.dias}d.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
      on('[data-print]','onclick',()=>{const w=window.open('','_blank');if(!w)return;w.opener=null;const limite=state.limite;state.limite=Infinity;render();const report=el.querySelector('.pri-report').innerHTML;state.limite=limite;render();w.document.write(`<!doctype html><html lang="es"><meta charset="utf-8"><title>Prioridades operativas</title><style>body{font:12px system-ui;margin:24px;color:#17251d}table{border-collapse:collapse;width:100%;margin:10px 0}td,th{padding:6px;border-bottom:1px solid #ccc;text-align:left}small{display:block}h2{margin-top:24px}button,input,select,.rv-fil,.pri-categories{display:none}button[data-cliente]{display:inline;border:0;background:none;font:inherit;color:inherit;padding:0}.bad{color:#a21d24}.warn{color:#805900}.vtot{display:flex;gap:30px}.vtot span{display:block}@media print{tr{break-inside:avoid}}</style><h1>Prioridades · ${esc(r.suc)}</h1>${report}<p>Informe con ${filtradas().length} alertas filtradas. Carga, evolución y calidad corresponden a toda la sucursal seleccionada.</p></html>`);w.document.close();w.focus();w.print();});
    }
    let suc=sucursal();
    return {render(){if(suc!==sucursal()){suc=sucursal();state.request++;state.busy=false;state.res=null;state.error='';}render();},invalidar(){state.request++;state.busy=false;state.res=null;state.error='';render();}};
  }
  const api={crear,csv};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.RutasPrioridades=api;
})(typeof globalThis!=='undefined'?globalThis:this);
