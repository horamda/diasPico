(() => {
  const $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels={asignar:'Asignar días',reemplazar:'Reemplazar días',conservar:'Conservar días actuales',sin_cambios:'Sin cambios',inactivo:'Cliente inactivo',no_encontrado:'No encontrado en Rutas',error:'Error'};
  const dayNames={LU:'Lun',MA:'Mar',MI:'Mié',JU:'Jue',VI:'Vie',SA:'Sáb'};
  const days=value=>(value.match(/../g)||[]).map(d=>dayNames[d]||d).join(', ')||'Sin días';
  let preview=null,page=0,generation=0;
  function invalidate(){generation++;preview=null;$('importPreview').hidden=true;$('confirmImport').disabled=true;$('importStatus').textContent='Analizá el archivo para generar una vista previa.'}
  $('importFile').onchange=invalidate;$('importMode').onchange=invalidate;
  function render(){
    const filter=$('importFilter').value;
    const rows=preview.rows.filter(r=>filter==='todos'||(filter==='cambios'?['asignar','reemplazar'].includes(r.estado):['error','inactivo','no_encontrado','conservar'].includes(r.estado)));
    const pages=Math.max(1,Math.ceil(rows.length/50));page=Math.min(page,pages-1);
    $('importRows').innerHTML=rows.slice(page*50,page*50+50).map(r=>`<tr><td>${r.fila}</td><td>${esc(r.cliente)}</td><td>${esc(r.nombre)}</td><td>${esc(days(r.actuales))}</td><td>${esc(days(r.dias))}</td><td>${esc(labels[r.estado])}${r.error?'<br>'+esc(r.error):''}</td></tr>`).join('');
    $('importPage').textContent=`Página ${page+1} de ${pages} · ${rows.length} filas`;
    $('previousPage').disabled=page===0;$('nextPage').disabled=page>=pages-1;
  }
  $('importFilter').onchange=()=>{page=0;if(preview)render()};
  $('previousPage').onclick=()=>{page--;render()};$('nextPage').onclick=()=>{page++;render()};
  async function result(response){const data=await response.json().catch(()=>({}));if(!response.ok||!data.ok)throw Error(data.error||'No se pudo completar la consulta. Revisá tu sesión y reintentá.');return data}
  $('refreshImportMaster').onclick=async()=>{
    invalidate();const button=$('refreshImportMaster');button.disabled=true;
    $('importStatus').textContent='Actualizando clientes...';
    try{const data=await result(await fetch(window.RUTAS_IMPORT.maestro,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}));$('importStatus').textContent=`Maestro actualizado: ${data.leidos} clientes. Analizá el CSV.`}catch(e){$('importStatus').textContent=e.message}finally{button.disabled=false}
  };
  $('importForm').onsubmit=async event=>{
    event.preventDefault();invalidate();const request=generation;const file=$('importFile').files[0];
    if(!file||file.size>5*1024*1024){$('importStatus').textContent='Seleccioná un CSV de hasta 5 MB.';return}
    const form=new FormData();form.append('archivo',file);form.append('modo',$('importMode').value);
    $('previewButton').disabled=true;$('importStatus').textContent='Analizando archivo y relacionando clientes...';
    try{
      const data=await result(await fetch(window.RUTAS_IMPORT.preview,{method:'POST',body:form}));
      if(request!==generation)return;
      preview=data;page=0;$('importFilter').value='todos';$('importPreview').hidden=false;
      $('importSummary').innerHTML=`<span class="pill">${data.resumen.total} filas</span>`+Object.entries(labels).filter(([key])=>data.resumen[key]).map(([key,label])=>`<span class="pill">${esc(label)}: ${data.resumen[key]}</span>`).join('');
      $('confirmImport').disabled=!data.token;$('confirmImport').textContent=`Confirmar ${data.resumen.cambios} cambios`;
      $('importStatus').textContent=data.token?'Vista previa lista. Todavía no se guardaron cambios.':'No hay cambios para aplicar con esta opción.';render();
    }catch(e){if(request===generation)$('importStatus').textContent=e.message}finally{$('previewButton').disabled=false}
  };
  $('confirmImport').onclick=async()=>{
    if(!preview?.token)return;
    const request=generation;
    $('confirmImport').disabled=true;$('previewButton').disabled=true;$('refreshImportMaster').disabled=true;$('importFile').disabled=true;$('importMode').disabled=true;
    $('importStatus').textContent='Guardando días de entrega...';
    try{
      const data=await result(await fetch(window.RUTAS_IMPORT.confirmar,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:preview.token})}));
      if(request!==generation)return;
      preview.token=null;$('confirmImport').textContent='Importación guardada';
      $('importStatus').textContent=`${data.ya_aplicada?'Esta importación ya estaba guardada.':'Importación completada.'} ${data.resumen.cambios} clientes actualizados. Podés ver los días en el mapa y los cambios en el historial de cada cliente.`;
    }catch(e){$('importStatus').textContent=e.message;$('confirmImport').disabled=false}
    finally{$('refreshImportMaster').disabled=false;$('previewButton').disabled=false;$('importFile').disabled=false;$('importMode').disabled=false}
  };
})();
