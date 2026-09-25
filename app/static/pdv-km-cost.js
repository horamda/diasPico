/* Cost of serving = assigned kilometers × all-inclusive pesos per kilometer. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const amount = (value, money = false) => value == null ? '—' : Number(value).toLocaleString('es-AR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
    ...(money ? {style: 'currency', currency: 'ARS'} : {})
  });
  let context = {}, report = null, signature = '', controller, page = 0, bound = false, loadedAt = 0;
  const pageSize = 50;
  function filtered() {
    const query = String(context.q || '').trim().toLocaleLowerCase('es-AR');
    return (report?.items || []).filter(r => !query || [r.cliente, r.nombre, r.localidad].join(' ').toLocaleLowerCase('es-AR').includes(query));
  }
  function render() {
    const rows = filtered();
    $('pdvKmExport').disabled = !report?.configurado || !rows.length;
    if (!report?.configurado) {
      $('pdvKmStatus').textContent = report?.mensaje || 'Ingresá la tarifa para calcular.';
      $('pdvKmSummary').innerHTML = '';
      $('pdvKmTable').innerHTML = '';
      $('pdvKmPager').innerHTML = '';
      return;
    }
    const known = rows.filter(r => r.costo != null);
    const pending = rows.reduce((sum, r) => sum + r.pendientes, 0);
    const visits = rows.reduce((sum, r) => sum + r.atenciones_con_km, 0);
    const cost = known.reduce((sum, r) => sum + r.costo, 0);
    $('pdvKmStatus').textContent = `${report.desde} a ${report.hasta} · ${report.mensaje} ${report.rutas_sin_distancias || 0} recorridos sin distancias en el período (todas las sucursales).`;
    const card = (label, value) => `<div class="note"><strong>${esc(label)}</strong><br>${esc(value)}</div>`;
    $('pdvKmSummary').innerHTML = card('Tarifa aplicada · todo incluido', amount(report.tarifa, true) + ' / km')
      + card(pending ? 'Costo calculado · parcial' : 'Costo de atenciones registradas', known.length ? amount(cost, true) : 'Sin distancias')
      + card('Promedio por atención con km', visits ? amount(cost / visits, true) : 'Sin distancias')
      + card('Atenciones pendientes de distancia', String(pending));
    page = Math.min(page, Math.max(0, Math.ceil(rows.length / pageSize) - 1));
    const visible = rows.slice(page * pageSize, (page + 1) * pageSize);
    $('pdvKmTable').innerHTML = !rows.length ? '<div class="empty">Sin clientes para los filtros actuales.</div>' : `
      <table><thead><tr><th>Cliente / sucursal</th><th>Cluster</th><th>Atenciones</th><th>Km asignados</th>
      <th>Costo de atención</th><th>Promedio / atención</th><th>$/bulto</th><th>Costo / venta</th><th>Cobertura y recorridos</th></tr></thead>
      <tbody>${visible.map(r => `<tr><td><strong>${esc(r.cliente)} · ${esc(r.nombre)}</strong><div class="client-sub">Sucursal ${esc(r.sucursal)} · ${esc(r.localidad)}</div></td>
      <td>${esc(r.cluster)}</td><td class="num">${r.atenciones_con_km} / ${r.atenciones}</td>
      <td class="num">${amount(r.km_asignados)}</td><td class="num">${amount(r.costo, true)}</td>
      <td class="num">${amount(r.costo_por_atencion, true)}</td><td class="num">${amount(r.costo_por_bulto, true)}</td>
      <td class="num">${r.costo_sobre_venta == null ? '—' : amount(r.costo_sobre_venta) + '%'}</td>
      <td><strong>${esc(r.estado)}</strong>${r.estimadas ? `<div>${r.estimadas} con distancia aproximada</div>` : ''}
      ${r.sin_maestro ? '<div>Sin coincidencia en el maestro</div>' : ''}
      ${r.visitas.length ? `<details><summary>Ver ${r.visitas.length} recorridos</summary>${r.visitas.map(v => `
        <div class="note"><a href="${esc(v.detalle_url)}" target="_blank" rel="noopener noreferrer">${esc(v.fecha)} · ${esc(v.rid)}</a><br>
        Tramo: ${amount(v.km_tramo)} km · Regreso asignado: ${amount(v.km_regreso)} km<br>
        Costo: ${amount(v.costo, true)} · ${esc(v.estado_entrega)}${v.estimada ? ' · Distancia aproximada' : ''}</div>`).join('')}</details>` : ''}</td></tr>`).join('')}</tbody></table>`;
    $('pdvKmPager').innerHTML = `<button type="button" class="btn" id="pdvKmPrev" ${page === 0 ? 'disabled' : ''}>Anterior</button>
      <span>${rows.length ? page * pageSize + 1 : 0}–${Math.min((page + 1) * pageSize, rows.length)} de ${rows.length} clientes</span>
      <button type="button" class="btn" id="pdvKmNext" ${(page + 1) * pageSize >= rows.length ? 'disabled' : ''}>Siguiente</button>`;
    $('pdvKmPrev').onclick = () => { page--; render(); };
    $('pdvKmNext').onclick = () => { page++; render(); };
  }
  async function load(force = false) {
    const input = $('pdvKmRate');
    if (!input.checkValidity() || !input.value) { input.reportValidity(); return; }
    const params = new URLSearchParams({tarifa: input.value});
    if (context.sucursal && context.sucursal !== 'TODAS') params.set('sucursal', context.sucursal);
    if (context.cluster) params.set('cluster', context.cluster);
    const next = params.toString() + '|' + String(context.desde || '') + '|' + String(context.hasta || '');
    if (!force && signature === next && (controller || Date.now() - loadedAt < 60000)) { if (report) render(); return; }
    signature = next;
    if (controller) controller.abort();
    const active = new AbortController();
    controller = active;
    report = null;
    render();
    $('pdvKmStatus').textContent = 'Consultando kilómetros de Reparto…';
    $('pdvKmApply').disabled = true;
    try {
      const response = await fetch('/api/segmentacion/reporte/costos-km?' + params, {signal: active.signal});
      const payload = await response.json();
      if (active !== controller) return;
      if (!response.ok || !payload.ok) throw new Error(payload.error || 'No se pudieron consultar las distancias.');
      report = payload.data;
      loadedAt = Date.now();
      page = 0;
      render();
    } catch (error) {
      if (active !== controller || error.name === 'AbortError') return;
      signature = '';
      $('pdvKmStatus').textContent = error.message;
    } finally {
      if (active === controller) { controller = null; $('pdvKmApply').disabled = false; }
    }
  }
  function exportCsv() {
    if (!report?.configurado) return;
    const columns = ['Desde','Hasta','Tarifa ARS/km','Cliente','Sucursal','Nombre','Cluster','Atenciones','Atenciones con km','Km asignados','Costo ARS','Costo por atención','Costo/bulto','Costo/venta %','Cobertura'];
    const cell = value => {
      let text = String(value ?? '');
      if (/^[=+\-@\t\r\n]/.test(text)) text = "'" + text;
      return '"' + text.replace(/"/g, '""') + '"';
    };
    const lines = [columns, ...filtered().map(r => [report.desde,report.hasta,report.tarifa,r.cliente,r.sucursal,r.nombre,r.cluster,r.atenciones,r.atenciones_con_km,r.km_asignados,r.costo,r.costo_por_atencion,r.costo_por_bulto,r.costo_sobre_venta,r.estado])];
    const url = URL.createObjectURL(new Blob(['\ufeff' + lines.map(row => row.map(cell).join(';')).join('\r\n')], {type:'text/csv;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = `costo-km-pdv-${report.desde}-${report.hasta}.csv`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  window.renderPdvKmCosts = (filters) => {
    if (!$('pdvKmRate')) return;
    if (context.q !== filters.q) page = 0;
    context = filters;
    if (!bound) {
      bound = true;
      $('pdvKmForm').addEventListener('submit', e => { e.preventDefault(); load(true); });
      $('pdvKmExport').addEventListener('click', exportCsv);
    }
    load();
  };
})();
