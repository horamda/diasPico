let frescuraSession = null;
let frescuraSessionReceivedAt = 0;
let frescuraSessionRequest = false;
let frescuraDraftTimer = null;
let frescuraLastReport = [];

function frDuration(seconds){
  if(seconds==null) return 'Sin medicion';
  const n=Math.max(0,Math.floor(Number(seconds)));
  return `${String(Math.floor(n/3600)).padStart(2,'0')}:${String(Math.floor(n/60)%60).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;
}
function frBranch(id){return String(id)==='2'?'Dolores':'Casa Central'}
function frDraft(){return {rows:frescuraRows,observaciones:observacionesFrescura.value}}
async function frRequest(url, method, payload){
  const res=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:payload?JSON.stringify(payload):undefined});
  const data=await res.json();
  if(!res.ok||data.ok===false) throw Error(data.error||'No se pudo guardar la sesion');
  return data;
}
function frReceiveSession(session){frescuraSession=session;frescuraSessionReceivedAt=Date.now();frSessionControls()}
function frSessionControls(){
  frUpdateWorkflow();
  const active=frescuraSession?.estado==='activo';
  const running=!!frescuraSession&&frescuraSession.estado!=='finalizado';
  const notice=document.getElementById('frEditNotice');
  if(notice)notice.hidden=active;
  const message=document.getElementById('frEditMessage');
  if(message)message.textContent=frescuraSession?.estado==='pausado'
    ?'El control está pausado. Reanudalo para modificar cantidades o fechas.'
    :frescuraSession?.estado==='finalizado'
      ?'Este control está finalizado. Iniciá otro control para registrar cambios.'
      :'Para modificar cantidades o fechas, seleccioná un responsable e iniciá el control.';
  const edit=document.getElementById('frEditAction');
  if(edit){edit.disabled=frescuraSessionRequest;edit.textContent=frescuraSession?.estado==='pausado'?'Reanudar para editar':'Iniciar para editar'}
  for(const id of ['sucursalFrescura','fechaFrescura','responsableFrescura','actualizarFrescuraBtn']){
    const el=document.getElementById(id);if(el)el.disabled=running;
  }
  const start=document.getElementById('frStart');if(start)start.disabled=running||frescuraSessionRequest;
  const pause=document.getElementById('frPause');if(pause){pause.disabled=!running||frescuraSessionRequest;pause.textContent=active?'Pausar y guardar borrador':'Reanudar'}
  const save=document.getElementById('guardarFrescuraBtn');if(save)save.disabled=!active||frescuraSessionRequest;
  for(const area of ['frescuraControlBody','frescuraControlCards']){
    document.getElementById(area)?.querySelectorAll('input,select,button').forEach(el=>el.disabled=!active);
  }
  if(active) aplicarDistribucionesFrescura();
  if(active) frescuraRows.forEach((r,idx)=>{
    if(!r.distribucion_fechas?.length)document.querySelectorAll(`[data-fr-real="${idx}"]`).forEach(el=>el.disabled=r._control_ok!=='NO_OK');
  });
  const leave=document.getElementById('frLeave');if(leave)leave.disabled=frescuraSession?.estado!=='pausado'||frescuraSessionRequest;
  const obs=document.getElementById('observacionesFrescura');if(obs)obs.disabled=!active;
}
async function habilitarEdicionFrescura(){
  if(frescuraSessionRequest)return;
  if(frescuraSession?.estado==='pausado')return pausarControlFrescura();
  if(!responsableFrescura.value){
    responsableFrescura.scrollIntoView({behavior:'smooth',block:'center'});
    responsableFrescura.focus();
    await modalAlert('Seleccioná el responsable y luego pulsá Iniciar para editar.');
    return;
  }
  return iniciarControlFrescura();
}
function frUpdateWorkflow(){
  const total=frescuraRows.length;
  const reviewed=frescuraRows.filter(frReviewed).length;
  const active=frescuraSession?.estado==='activo';
  const finished=frescuraSession?.estado==='finalizado';
  const step=finished||(active&&total>0&&reviewed===total)?'frStepFinish':frescuraSession&&!finished?'frStepReview':'frStepPrepare';
  for(const id of ['frStepPrepare','frStepReview','frStepFinish']){
    const el=document.getElementById(id);
    if(el){if(id===step)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current')}
  }
  const count=document.getElementById('frReviewCount');
  if(count)count.textContent=total?`${reviewed} de ${total} lotes revisados · ${total-reviewed} pendientes`:'Sin lotes cargados';
  const progress=document.getElementById('frReviewProgress');
  if(progress){progress.max=total||1;progress.value=reviewed}
  const hint=document.getElementById('frReviewHint');
  if(hint)hint.textContent=finished?'Control finalizado. Consultá las diferencias al pie.':active?(reviewed===total&&total?'Todo revisado. Ya podés finalizar y guardar.':'Los cambios se guardan como borrador. Revisá cada lote antes de finalizar.'):frescuraSession?.estado==='pausado'?'Control pausado. Reanudá para continuar.':'Iniciá el control para comenzar la revisión.';
  const next=document.getElementById('frNextPending');
  if(next)next.disabled=!active||reviewed===total;
}
let frLastPending=-1;
function frNextPending(){
  const pending=frescuraRows.map((r,i)=>frReviewed(r)?-1:i).filter(i=>i>=0);
  if(!pending.length)return;
  const index=pending.find(i=>i>frLastPending)??pending[0];
  frLastPending=index;
  const el=[...document.querySelectorAll(`[data-fr-ok="${index}"]`)].find(e=>e.getClientRects().length&&!e.disabled)
    ||[...document.querySelectorAll(`[data-fr-b="${index}"]`)].find(e=>e.getClientRects().length);
  if(el){el.scrollIntoView({behavior:'smooth',block:'center'});el.focus({preventScroll:true})}
}
function frTick(){
  const el=document.getElementById('frClock');if(!el)return;
  if(!frescuraSession){el.textContent='Tiempo: sin iniciar';return}
  const extra=frescuraSession.estado==='activo'?(Date.now()-frescuraSessionReceivedAt)/1000:0;
  el.textContent=`${frescuraSession.estado==='activo'?'En curso':frescuraSession.estado==='pausado'?'En pausa':'Finalizado'} - activo ${frDuration(Number(frescuraSession.segundos_activos)+extra)}`;
}
setInterval(frTick,1000);

async function iniciarControlFrescura(){
  if(frescuraSessionRequest)return;
  if(!responsableFrescura.value||!frescuraRows.length){await modalAlert('Selecciona operario y carga los lotes antes de iniciar.');return}
  frescuraSessionRequest=true;frSessionControls();
  try{
    const result=await frRequest('/api/control-stock/frescura-sesiones','POST',{
      sucursal:sucursalFrescura.value,fecha:fechaFrescura.value,responsable:responsableFrescura.value,borrador:frDraft()});
    frReceiveSession(result.data);
    frescuraRows=result.data.borrador.rows;
    observacionesFrescura.value=result.data.borrador.observaciones||'';
    frArticulos.textContent=`Articulos: ${new Set(frescuraRows.map(r=>r.codigo_articulo)).size}`;
    frLotes.textContent=`Lotes: ${frescuraRows.length}`;
    frTotal.textContent=`Referencia: ${frescuraRows.reduce((n,r)=>n+Number(r.stock_sistema_bultos||0),0)} bultos con ${frescuraRows.reduce((n,r)=>n+Number(r.stock_sistema_unidades||0),0)} unidades`;
    frSync.textContent='Stock de referencia del control iniciado';
    frSync.title=`Inicio del control: ${new Date(result.data.iniciado_at).toLocaleString()}. El stock esperado se conserva durante la revision.`;
    renderControlFrescuraRows();
    restaurarCamposFrescura();
    frescuraControlStatus.textContent='Control recuperado/iniciado. Confirma los pallets o lotes revisados. El tiempo sigue corriendo hasta pausar o finalizar, incluso si cerras la pantalla.';
    frTick();
  }catch(error){await modalAlert(error.message)}
  finally{frescuraSessionRequest=false;frSessionControls()}
}
function restaurarCamposFrescura(){
  frescuraRows.forEach((r,idx)=>{
    for(const field of ['b','u','ok','real','obs']){
      if(r['_control_'+field]!==undefined)document.querySelectorAll(`[data-fr-${field}="${idx}"]`).forEach(el=>el.value=r['_control_'+field]);
    }
  });
  aplicarDistribucionesFrescura();actualizarTotalesFrescura();
}
function frScheduleDraft(){
  clearTimeout(frescuraDraftTimer);
  if(frescuraSession?.estado!=='activo')return;
  frescuraDraftTimer=setTimeout(()=>guardarSesionFrescura('borrador'),1200);
}
async function guardarSesionFrescura(action){
  if(!frescuraSession||frescuraSession.estado==='finalizado')return;
  if(frescuraSessionRequest){if(action==='borrador')frScheduleDraft();return}
  clearTimeout(frescuraDraftTimer);
  frescuraSessionRequest=true;
  if(action!=='borrador')frSessionControls();
  try{
    const result=await frRequest(`/api/control-stock/frescura-sesiones/${frescuraSession.id}`,'PUT',{accion:action,borrador:frDraft()});
    frReceiveSession(result.data);frTick();
    document.getElementById('frDraftStatus').textContent='Borrador guardado en el servidor';
  }catch(error){document.getElementById('frDraftStatus').textContent='Borrador sin guardar: '+error.message}
  finally{frescuraSessionRequest=false;frSessionControls()}
}
function pausarControlFrescura(){return guardarSesionFrescura(frescuraSession?.estado==='activo'?'pausar':'reanudar')}
function salirControlFrescura(){
  if(frescuraSession?.estado!=='pausado'||frescuraSessionRequest)return;
  frescuraSession=null;frescuraDirty=false;frescuraLoaded=false;frSessionControls();frTick();
  document.getElementById('frDraftStatus').textContent='Control pausado y guardado. Para continuarlo, selecciona su sucursal, fecha y operario y pulsa Iniciar / recuperar.';
}

function frReviewed(row){
  if(row.distribucion_fechas?.length)return row.distribucion_fechas.every(g=>['OK','NO_OK'].includes(g.revision));
  return ['OK','NO_OK'].includes(row._control_ok);
}
function frNoOkTable(rows){
  if(!rows.length)return '<p>No se detectaron No OK en este control.</p>';
  return `<div style="overflow:auto"><table><thead><tr><th>Articulo</th><th>Lote</th><th>Pallet / grupo</th><th>Tipo</th><th>Fecha esperada</th><th>Fecha real</th><th>Bultos afectados / contados</th><th>Unidades</th><th>Observacion</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.codigo_articulo)} ${esc(r.descripcion||'')}</td><td>${esc(r.lote)}</td><td>${esc(r.referencia||'')}</td><td>${r.tipo==='CANTIDAD'?`Cantidad (dif. ${esc(r.diferencia_bultos)} bultos / ${esc(r.diferencia_unidades)} un.)`:'Fecha'}</td><td>${esc(r.fecha_sistema||'-')}</td><td>${esc(r.fecha_vencimiento||'-')}</td><td>${esc(r.bultos)}</td><td>${esc(r.unidades)}</td><td>${esc(r.observacion||'')}</td></tr>`).join('')}</tbody></table></div>`;
}
function mostrarCierreFrescura(data){
  frescuraLastReport=data.no_ok||[];
  const el=document.getElementById('frFinishReport');el.hidden=false;
  el.innerHTML=`<h3>Control #${esc(data.id)} finalizado - No OK para analizar</h3><p>${esc(frBranch(sucursalFrescura.value))} - ${esc(responsableFrescura.value)} - ${esc(fechaFrescura.value)}. Tiempo activo: <strong>${frDuration(data.segundos_activos)}</strong>. Transcurrido: ${frDuration(data.segundos_transcurridos)} (incluye pausas).</p>${frNoOkTable(frescuraLastReport)}`;
  el.scrollIntoView({behavior:'smooth',block:'start'});
}
async function cargarTiemposFrescura(){
  const el=document.getElementById('frHistory');
  const params=new URLSearchParams({desde:document.getElementById('frDesde').value,hasta:document.getElementById('frHasta').value,
    sucursal:document.getElementById('frHistoryBranch').value,responsable:document.getElementById('frHistoryWorker').value.trim()});
  el.textContent='Consultando controles...';
  try{
    const data=await frRequest('/api/control-stock/frescura-tiempos?'+params,'GET');
    el.innerHTML=`<h4>Totales por sucursal y operario</h4>${data.resumen.map(r=>`<p>${esc(frBranch(r.sucursal))} - ${esc(r.responsable)}: ${r.controles} controles, ${r.lotes_no_ok} lotes No OK. Tiempo activo: ${r.controles_con_tiempo?frDuration(r.segundos_activos):'Sin medicion'} (${r.controles_con_tiempo} controles medidos).</p>`).join('')||'<p>No hay controles en el periodo.</p>'}<div style="overflow:auto"><table><thead><tr><th>Control</th><th>Sucursal</th><th>Fecha</th><th>Operario</th><th>Inicio</th><th>Fin</th><th>Activo</th><th>Transcurrido</th><th>No OK</th></tr></thead><tbody>${data.rows.map(r=>`<tr><td>${r.id}</td><td>${esc(frBranch(r.sucursal))}</td><td>${esc(r.fecha)}</td><td>${esc(r.responsable)}</td><td>${r.iniciado_at?esc(new Date(r.iniciado_at).toLocaleString()):'-'}</td><td>${r.finalizado_at?esc(new Date(r.finalizado_at).toLocaleString()):'-'}</td><td>${frDuration(r.segundos_activos)}</td><td>${frDuration(r.segundos_transcurridos)}</td><td><button class="btn" data-fr-history-id="${r.id}" data-branch="${esc(r.sucursal)}" data-date="${esc(r.fecha)}">${r.lotes_no_ok} lotes</button></td></tr>`).join('')}</tbody></table></div>`;
    el.querySelectorAll('[data-fr-history-id]').forEach(b=>b.onclick=()=>consultarNoOkFrescura(b.dataset.frHistoryId,b.dataset.branch,b.dataset.date));
  }catch(error){el.textContent=error.message}
}
async function consultarNoOkFrescura(id,branch,day){
  const el=document.getElementById('frHistoryDetail');el.textContent='Consultando No OK...';
  try{
    const data=await frRequest('/api/control-stock/frescura-diferencias?'+new URLSearchParams({conteo_id:id,sucursal:branch,desde:day,hasta:day}),'GET');
    const findings=[];
    for(const r of data.rows){
      const common={codigo_articulo:r.codigo_articulo,descripcion:r.descripcion_articulo,lote:r.lote,fecha_sistema:r.fecha_vencimiento_sistema,observacion:r.observacion};
      if(r.distribucion_fechas?.length){
        for(const g of r.distribucion_fechas)if(g.fecha_vencimiento!==r.fecha_vencimiento_sistema)findings.push({...common,...g,tipo:'FECHA'});
      }else if(r.diferencia_fecha)findings.push({...common,tipo:'FECHA',referencia:'Lote completo',fecha_vencimiento:r.fecha_vencimiento_controlada,bultos:r.stock_contado_bultos,unidades:r.stock_contado_unidades});
      if(r.diferencia_stock)findings.push({...common,tipo:'CANTIDAD',referencia:'Total del lote',bultos:r.stock_contado_bultos,unidades:r.stock_contado_unidades,diferencia_bultos:r.stock_contado_bultos-r.stock_sistema_bultos,diferencia_unidades:r.stock_contado_unidades-r.stock_sistema_unidades});
    }
    el.innerHTML=`<h4>No OK del control #${esc(id)}</h4>${frNoOkTable(findings)}`;
  }catch(error){el.textContent=error.message}
}
