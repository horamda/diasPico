/* Efectividad de visita: de las visitas del vendedor, en cuántas hubo venta.
   Visitas: todas las semanas en los días de visita del maestro (no hay registro de visitas reales).
   Visita con venta: alguna venta (vendedor o BEES) después de la visita y hasta la visita siguiente,
   inclusive; la factura lleva la fecha de entrega, que es el día siguiente a la visita. */
(function(root){
  const DAYS = ['LU','MA','MI','JU','VI','SA'];
  const WD = ['DO','LU','MA','MI','JU','VI','SA'];          // índice de Date.getUTCDay()
  const DIA_MS = 864e5;
  const fecha = s => Date.parse(s + 'T00:00:00Z');
  const iso = t => new Date(t).toISOString().slice(0, 10);
  const wd = t => WD[new Date(t).getUTCDay()];

  // Fechas de visita (ms) dentro de [desde, hasta] y la visita siguiente a cada una (puede caer fuera).
  function visitas(dias, desde, hasta) {
    const out = [];
    for (let t = desde; t <= hasta; t += DIA_MS) if (dias.includes(wd(t))) out.push(t);
    let sig = hasta + DIA_MS;
    while (!dias.includes(wd(sig))) sig += DIA_MS;
    return out.map((t, i) => [t, out[i + 1] ?? sig]);
  }

  function cliente(c, compras, desde, hasta) {
    const dias = DAYS.filter(d => (c.vis || '').includes(d));
    const ventas = new Map((compras || []).map(([f, b]) => [fecha(f), !!b]));
    const porDia = Object.fromEntries(DAYS.map(d => [d, {visitas:0, efectivas:0}]));
    let vis = 0, ef = 0;
    for (const [t, sig] of visitas(dias, desde, hasta)) {
      if (sig > hasta) continue;                               // ciclo incompleto al final del período
      let hubo = false;
      for (let x = t + DIA_MS; x <= sig && !hubo; x += DIA_MS) hubo = ventas.has(x);
      vis++; porDia[wd(t)].visitas++;
      if (hubo) { ef++; porDia[wd(t)].efectivas++; }
    }
    // Semanas completas (lunes a domingo) dentro del período y en cuántas compró.
    let lunes = desde; while (wd(lunes) !== 'LU') lunes += DIA_MS;
    let semanas = 0, semCompra = 0;
    for (let s = lunes; s + 6 * DIA_MS <= hasta; s += 7 * DIA_MS) {
      semanas++;
      for (let x = s; x < s + 7 * DIA_MS; x += DIA_MS) if (ventas.has(x)) { semCompra++; break; }
    }
    const enPeriodo = [...ventas].filter(([t]) => t >= desde && t <= hasta);
    const ultima = enPeriodo.length ? iso(Math.max(...enPeriodo.map(([t]) => t))) : null;
    return {id:c.id, n:c.n, loc:c.loc, suc:c.suc, dom:c.dom, vis:dias.join(''), d:c.d || '', visitas:vis, efectivas:ef,
      pct:vis ? ef / vis : null, semanas, semCompra, compras:enPeriodo.length,
      bees:enPeriodo.length ? enPeriodo.filter(([, b]) => b).length / enPeriodo.length : null, ultima, porDia};
  }

  /** clientes: los del mapa (c.vis = días de visita del maestro). fechas: {desde, hasta, clientes:{id:[[fecha, bees]]}}. */
  function analizar(clientes, fechas, {suc = 'TODAS'} = {}) {
    const desde = fecha(fechas.desde), hasta = fecha(fechas.hasta), F = fechas.clientes || {};
    const act = clientes.filter(c => !c.an && (suc === 'TODAS' || c.suc === suc));
    const sinVisita = act.filter(c => !DAYS.some(d => (c.vis || '').includes(d)));
    const filas = act.filter(c => !sinVisita.includes(c)).map(c => cliente(c, F[c.id], desde, hasta)).filter(r => r.visitas);
    const sumar = rs => {
      const visitas = rs.reduce((t, r) => t + r.visitas, 0), efectivas = rs.reduce((t, r) => t + r.efectivas, 0);
      const sem = rs.reduce((t, r) => t + r.semanas, 0), semC = rs.reduce((t, r) => t + r.semCompra, 0);
      const comp = rs.reduce((t, r) => t + r.compras, 0), bees = rs.reduce((t, r) => t + (r.bees || 0) * r.compras, 0);
      return {clientes:rs.length, visitas, efectivas, pct:visitas ? efectivas / visitas : null, semPct:sem ? semC / sem : null,
        bees:comp ? bees / comp : null, ceros:rs.filter(r => !r.efectivas).length, bajos:rs.filter(r => r.pct < .25).length};
    };
    const grupos = new Map();
    for (const r of filas) { const k = r.suc + '|' + r.loc; if (!grupos.has(k)) grupos.set(k, []); grupos.get(k).push(r); }
    const localidades = [...grupos].map(([k, rs]) => { const [s, loc] = k.split('|'); return {suc:s, loc, ...sumar(rs)}; })
      .sort((a, b) => a.suc.localeCompare(b.suc) || b.clientes - a.clientes);
    const porDia = DAYS.map(d => {
      const rs = filas.filter(r => r.porDia[d].visitas);
      const visitas = rs.reduce((t, r) => t + r.porDia[d].visitas, 0), efectivas = rs.reduce((t, r) => t + r.porDia[d].efectivas, 0);
      return {dia:d, clientes:rs.length, visitas, efectivas, pct:visitas ? efectivas / visitas : null};
    });
    filas.sort((a, b) => a.pct - b.pct || b.visitas - a.visitas);
    return {generado:new Date().toISOString(), desde:fechas.desde, hasta:fechas.hasta, suc,
      resumen:{...sumar(filas), sinVisitaDom:sinVisita.filter(c => (c.vis || '').includes('DO')).length,
        sinVisita:sinVisita.filter(c => !(c.vis || '').includes('DO')).length, activos:act.length},
      localidades, porDia, clientes:filas};
  }
  const api = {analizar, DAYS};
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.RutasEfectividad = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
