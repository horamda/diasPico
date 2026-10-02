(() => {
const $=id=>document.getElementById(id);
const {esc,status,toast,timer,request,guardando}=window.ImportUI;
const labels={crear:'Crear recorrido',reemplazar:'Reemplazar',conservar:'Conservar actual',sin_cambios:'Sin cambios',error:'Error'};
const st=(msg,kind)=>status($('routeStatus'),msg,kind);
let preview=null,page=0,generation=0;
function invalidate(){generation++;preview=null;$('routePreview').hidden=true;$('routeConfirm').disabled=true;st('Analizá el archivo para revisar los recorridos.','info')}
$('routeFile').onchange=invalidate;$('routeMode').onchange=invalidate;
const stops=items=>items.map(p=>`${p.orden}. ${p.localidad}`).join(' → ')||'Sin recorrido';
function render(){
 const pages=Math.max(1,Math.ceil(preview.rows.length/50));
 $('routeRows').innerHTML=preview.rows.slice(page*50,page*50+50).map(r=>`<tr><td>${esc(r.filas.join(', '))}</td><td>${esc(r.sucursal)}</td><td>${esc(r.vehiculo)}${r.nuevo_vehiculo?' (nuevo)':''}</td><td>${esc(r.dia)}</td><td>${esc(stops(r.actual))}</td><td>${esc(stops(r.paradas))}</td><td class="${r.estado==='error'?'bad':''}">${esc(labels[r.estado])}${r.error?'<br>'+esc(r.error):''}</td></tr>`).join('');
 $('routePage').textContent=`Página ${page+1} de ${pages}`;$('routePrev').disabled=page===0;$('routeNext').disabled=page>=pages-1;
}
$('routePrev').onclick=()=>{page--;render()};$('routeNext').onclick=()=>{page++;render()};
$('routeForm').onsubmit=async e=>{
 e.preventDefault();invalidate();const request_=generation,file=$('routeFile').files[0];
 if(!file){st('Seleccioná un archivo CSV.','err');return}
 if(file.size>5*1024*1024){st('El archivo supera los 5 MB.','err');return}
 const form=new FormData();form.append('archivo',file);form.append('modo',$('routeMode').value);
 $('routeAnalyze').disabled=true;const t=timer();st(`Analizando recorridos de ${file.name}...`,'busy');
 try{
  const data=await request(window.RUTAS_REC.preview,{method:'POST',body:form});if(request_!==generation)return;
  const r=data.resumen,errores=(r.error||0)+(r.errores_fila||0);
  preview=data;page=0;$('routePreview').hidden=false;
  $('routeSummary').textContent=`${r.filas} paradas · ${r.total} recorridos · ${r.cambios} cambios propuestos · ${errores} errores.`;
  $('routeErrors').innerHTML=data.errores.length?'<h3>Filas a corregir</h3>'+data.errores.slice(0,200).map(x=>`<p>Fila ${x.fila}: ${esc(x.error)}</p>`).join('')+(data.errores.length>200?'<p>Se muestran los primeros 200 errores.</p>':''):'';
  $('routeConfirm').disabled=!data.token;$('routeConfirm').textContent=`Confirmar ${r.cambios} recorridos`;
  if(data.token)st(`Vista previa lista en ${t()}: ${r.cambios} recorridos cambian. Todavía no se guardó nada.`,'ok');
  else if(errores||data.errores.length){st(`El archivo tiene ${errores||data.errores.length} errores. Corregilos y volvé a analizar; no se guardó ningún cambio.`,'err');toast('El archivo tiene errores','err')}
  else st('No hay cambios para aplicar.','warn');
  render();
 }catch(err){if(request_===generation){st(err.message,'err');toast('No se pudo analizar el archivo','err')}}finally{$('routeAnalyze').disabled=false}
};
$('routeConfirm').onclick=async()=>{
 if(!preview?.token)return;
 const t=timer(),lock=['routeConfirm','routeAnalyze','routeFile','routeMode'];
 lock.forEach(id=>$(id).disabled=true);guardando(true);
 st(`Guardando ${preview.resumen.cambios} recorridos. No cierres la página...`,'busy');
 try{
  const data=await request(window.RUTAS_REC.confirmar,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:preview.token})});
  preview.token=null;$('routeConfirm').textContent='Importación guardada';
  if(data.ya_aplicada){st('Esta importación ya estaba guardada; no se repitieron cambios.','warn');toast('La importación ya estaba guardada','warn')}
  else{st(`Importación completada en ${t()}: ${data.resumen.cambios} recorridos guardados. Podés consultarlos en Rutas.`,'ok');toast(`${data.resumen.cambios} recorridos guardados`,'ok')}
 }catch(err){st(err.message,'err');toast('La importación no se guardó','err');$('routeConfirm').disabled=false}
 finally{guardando(false);lock.filter(id=>id!=='routeConfirm').forEach(id=>$(id).disabled=false)}
};
st('Analizá el archivo para revisar los recorridos.','info');
})();
