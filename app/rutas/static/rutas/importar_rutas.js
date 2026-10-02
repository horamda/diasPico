(() => {
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={crear:'Crear recorrido',reemplazar:'Reemplazar',conservar:'Conservar actual',sin_cambios:'Sin cambios',error:'Error'};
let preview=null,page=0,generation=0;
function invalidate(){generation++;preview=null;$('routePreview').hidden=true;$('routeConfirm').disabled=true;$('routeStatus').textContent='Analizá el archivo para revisar los recorridos.'}
$('routeFile').onchange=invalidate;$('routeMode').onchange=invalidate;
const stops=items=>items.map(p=>`${p.orden}. ${p.localidad}`).join(' → ')||'Sin recorrido';
function render(){
 const pages=Math.max(1,Math.ceil(preview.rows.length/50));
 $('routeRows').innerHTML=preview.rows.slice(page*50,page*50+50).map(r=>`<tr><td>${esc(r.filas.join(', '))}</td><td>${esc(r.sucursal)}</td><td>${esc(r.vehiculo)}${r.nuevo_vehiculo?' (nuevo)':''}</td><td>${esc(r.dia)}</td><td>${esc(stops(r.actual))}</td><td>${esc(stops(r.paradas))}</td><td>${esc(labels[r.estado])}${r.error?'<br>'+esc(r.error):''}</td></tr>`).join('');
 $('routePage').textContent=`Página ${page+1} de ${pages}`;$('routePrev').disabled=page===0;$('routeNext').disabled=page>=pages-1;
}
$('routePrev').onclick=()=>{page--;render()};$('routeNext').onclick=()=>{page++;render()};
async function result(res){const data=await res.json().catch(()=>({}));if(!res.ok||!data.ok)throw Error(data.error||'No se pudo completar la operación. Revisá tu sesión.');return data}
$('routeForm').onsubmit=async e=>{
 e.preventDefault();invalidate();const request=generation,file=$('routeFile').files[0];
 if(!file||file.size>5*1024*1024){$('routeStatus').textContent='Seleccioná un CSV de hasta 5 MB.';return}
 const form=new FormData();form.append('archivo',file);form.append('modo',$('routeMode').value);
 $('routeAnalyze').disabled=true;$('routeStatus').textContent='Analizando recorridos...';
 try{
  const data=await result(await fetch(window.RUTAS_REC.preview,{method:'POST',body:form}));if(request!==generation)return;
  preview=data;page=0;$('routePreview').hidden=false;
  $('routeSummary').textContent=`${data.resumen.filas} paradas · ${data.resumen.total} recorridos · ${data.resumen.cambios} cambios propuestos · ${(data.resumen.error||0)+(data.resumen.errores_fila||0)} errores.`;
  $('routeErrors').innerHTML=data.errores.length?'<h3>Filas a corregir</h3>'+data.errores.slice(0,200).map(r=>`<p>Fila ${r.fila}: ${esc(r.error)}</p>`).join('')+(data.errores.length>200?'<p>Se muestran los primeros 200 errores.</p>':''):'';
  $('routeConfirm').disabled=!data.token;$('routeConfirm').textContent=`Confirmar ${data.resumen.cambios} recorridos`;
  $('routeStatus').textContent=data.token?'Vista previa lista. Todavía no se guardaron cambios.':data.resumen.error||data.errores.length?'Corregí los errores y volvé a analizar. No se guardó ningún cambio.':'No hay cambios para aplicar.';render();
 }catch(err){if(request===generation)$('routeStatus').textContent=err.message}finally{$('routeAnalyze').disabled=false}
};
$('routeConfirm').onclick=async()=>{
 if(!preview?.token)return;
 for(const id of ['routeConfirm','routeAnalyze','routeFile','routeMode'])$(id).disabled=true;
 $('routeStatus').textContent='Guardando recorridos...';
 try{
  const data=await result(await fetch(window.RUTAS_REC.confirmar,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:preview.token})}));
  preview.token=null;$('routeConfirm').textContent='Importación guardada';
  $('routeStatus').textContent=`${data.ya_aplicada?'La importación ya estaba guardada.':'Importación completada.'} ${data.resumen.cambios} recorridos guardados. Podés consultarlos en Rutas.`;
 }catch(err){$('routeStatus').textContent=err.message;$('routeConfirm').disabled=false}
 finally{for(const id of ['routeAnalyze','routeFile','routeMode'])$(id).disabled=false}
};
})();
