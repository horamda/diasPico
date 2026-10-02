(() => {
  const $=id=>document.getElementById(id);
  const {esc,status,toast,timer,request,guardando}=window.ImportUI;
  const labels={asignar:'Asignar días',reemplazar:'Reemplazar días',conservar:'Conservar días actuales',sin_cambios:'Sin cambios',inactivo:'Cliente inactivo',no_encontrado:'No encontrado en Rutas',error:'Error'};
  const pillClass={asignar:'ok',reemplazar:'warn',error:'bad',no_encontrado:'bad',inactivo:'warn'};
  const dayNames={LU:'Lun',MA:'Mar',MI:'Mié',JU:'Jue',VI:'Vie',SA:'Sáb'};
  const days=value=>(value.match(/../g)||[]).map(d=>dayNames[d]||d).join(', ')||'Sin días';
  const st=(msg,kind)=>status($('importStatus'),msg,kind);
  let preview=null,page=0,generation=0;
  function invalidate(){generation++;preview=null;$('importPreview').hidden=true;$('confirmImport').disabled=true;st('Analizá el archivo para generar una vista previa.','info')}
  $('importFile').onchange=invalidate;$('importMode').onchange=invalidate;
  function render(){
    const filter=$('importFilter').value;
    const rows=preview.rows.filter(r=>filter==='todos'||(filter==='cambios'?['asignar','reemplazar'].includes(r.estado):['error','inactivo','no_encontrado','conservar'].includes(r.estado)));
    const pages=Math.max(1,Math.ceil(rows.length/50));page=Math.min(page,pages-1);
    $('importRows').innerHTML=rows.slice(page*50,page*50+50).map(r=>`<tr><td>${r.fila}</td><td>${esc(r.cliente)}</td><td>${esc(r.nombre)}</td><td>${esc(days(r.actuales))}</td><td>${esc(days(r.dias))}</td><td class="${['error','no_encontrado'].includes(r.estado)?'bad':''}">${esc(labels[r.estado])}${r.error?'<br>'+esc(r.error):''}</td></tr>`).join('');
    $('importPage').textContent=`Página ${page+1} de ${pages} · ${rows.length} filas`;
    $('previousPage').disabled=page===0;$('nextPage').disabled=page>=pages-1;
  }
  $('importFilter').onchange=()=>{page=0;if(preview)render()};
  $('previousPage').onclick=()=>{page--;render()};$('nextPage').onclick=()=>{page++;render()};
  $('refreshImportMaster').onclick=async()=>{
    invalidate();const button=$('refreshImportMaster');button.disabled=true;const t=timer();
    st('Actualizando clientes desde el maestro...','busy');
    try{
      const data=await request(window.RUTAS_IMPORT.maestro,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      const msg=`Maestro actualizado en ${t()}: ${data.leidos} clientes (${data.nuevos} nuevos)${data.omitidos?`, ${data.omitidos} códigos omitidos`:''}. Ya podés analizar el CSV.`;
      st(msg,data.omitidos?'warn':'ok');toast('Maestro actualizado','ok');
    }catch(e){st(e.message,'err');toast('No se pudo actualizar el maestro','err')}finally{button.disabled=false}
  };
  $('importForm').onsubmit=async event=>{
    event.preventDefault();invalidate();const request_=generation;const file=$('importFile').files[0];
    if(!file){st('Seleccioná un archivo CSV.','err');return}
    if(file.size>5*1024*1024){st('El archivo supera los 5 MB.','err');return}
    const form=new FormData();form.append('archivo',file);form.append('modo',$('importMode').value);
    $('previewButton').disabled=true;const t=timer();
    st(`Analizando ${file.name} y relacionando clientes...`,'busy');
    try{
      const data=await request(window.RUTAS_IMPORT.preview,{method:'POST',body:form});
      if(request_!==generation)return;
      const r=data.resumen,excluidos=(r.error||0)+(r.no_encontrado||0);
      preview=data;page=0;$('importFilter').value='todos';$('importPreview').hidden=false;
      $('importSummary').innerHTML=`<span class="pill">${r.total} filas</span>`+Object.entries(labels).filter(([key])=>r[key]).map(([key,label])=>`<span class="pill ${pillClass[key]||''}">${esc(label)}: ${r[key]}</span>`).join('');
      $('confirmImport').disabled=!data.token;$('confirmImport').textContent=`Confirmar ${r.cambios} cambios`;
      if(data.token)st(`Vista previa lista en ${t()}: ${r.cambios} clientes cambian${excluidos?` y ${excluidos} filas se excluyen por errores (filtrá "Excluidos" para verlas)`:''}. Todavía no se guardó nada.`,excluidos?'warn':'ok');
      else st(excluidos?`No hay cambios para aplicar y ${excluidos} filas tienen errores. Revisá la tabla.`:'No hay cambios para aplicar con esta opción.','warn');
      render();
    }catch(e){if(request_===generation){st(e.message,'err');toast('No se pudo analizar el archivo','err')}}finally{$('previewButton').disabled=false}
  };
  $('confirmImport').onclick=async()=>{
    if(!preview?.token)return;
    const request_=generation,t=timer(),lock=['confirmImport','previewButton','refreshImportMaster','importFile','importMode'];
    lock.forEach(id=>$(id).disabled=true);guardando(true);
    st(`Guardando ${preview.resumen.cambios} cambios en una sola transacción. No cierres la página...`,'busy');
    try{
      const data=await request(window.RUTAS_IMPORT.confirmar,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:preview.token})});
      if(request_!==generation)return;
      preview.token=null;$('confirmImport').textContent='Importación guardada';
      if(data.ya_aplicada){st('Esta importación ya estaba guardada; no se repitieron cambios.','warn');toast('La importación ya estaba guardada','warn')}
      else{st(`Importación completada en ${t()}: ${data.resumen.cambios} clientes actualizados. Podés ver los días en el mapa y los cambios en el historial de cada cliente.`,'ok');toast(`${data.resumen.cambios} clientes actualizados`,'ok')}
    }catch(e){st(e.message,'err');toast('La importación no se guardó','err');$('confirmImport').disabled=false}
    finally{guardando(false);lock.filter(id=>id!=='confirmImport').forEach(id=>$(id).disabled=false)}
  };
  st('Analizá el archivo para generar una vista previa.','info');
})();
