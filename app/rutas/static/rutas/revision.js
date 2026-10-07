/* Revisión de días de entrega: compara los días asignados con la facturación real y con la ubicación. */
(function(root){
  const DAYS = ['LU','MA','MI','JU','VI','SA'];
  const PATRONES = ['LUJU','MAVI','MISA','MAJU','MASA'];
  const MIN_COMPRAS = 4;       // compras mínimas para opinar sobre un cliente
  const VECINOS = 8, VECINO_KM = .6;
  const isGeo = c => c.lat != null && c.lng != null && !c.far;
  const km = (a, b) => Math.hypot((a.lat - b.lat) * 111.32, (a.lng - b.lng) * 111.32 * Math.cos(a.lat * Math.PI / 180));
  const pares = d => { const s = new Set(); for (let i = 0; i < (d || '').length; i += 2) s.add(d.slice(i, i + 2)); return s; };
  const ordenar = ds => DAYS.filter(d => ds.includes(d)).join('');
  // Preventa: el camión entrega el día hábil siguiente a la visita del vendedor.
  const SIG = {LU:'MA', MA:'MI', MI:'JU', JU:'VI', VI:'SA', SA:'LU'};
  const trasVisita = vis => ordenar([...pares(vis)].filter(d => SIG[d]).map(d => SIG[d]));
  // Días cargados que son exactamente días de visita y ninguno el día siguiente.
  const esVisita = (d, vis) => !!d && !!vis && [...pares(d)].every(x => vis.includes(x)) && ![...pares(d)].some(x => trasVisita(vis).includes(x));

  // Envolvente convexa sin margen y punto dentro de polígono, sobre [lat,lng].
  function hull(pts) {
    const p = [...new Map(pts.map(x => [x.join(), x])).values()].sort((a, b) => a[1] - b[1] || a[0] - b[0]);
    if (p.length < 3) return p;
    const cross = (o, a, b) => (a[1] - o[1]) * (b[0] - o[0]) - (a[0] - o[0]) * (b[1] - o[1]);
    const lo = [], up = [];
    for (const x of p) { while (lo.length >= 2 && cross(lo.at(-2), lo.at(-1), x) <= 0) lo.pop(); lo.push(x); }
    for (const x of [...p].reverse()) { while (up.length >= 2 && cross(up.at(-2), up.at(-1), x) <= 0) up.pop(); up.push(x); }
    return lo.slice(0, -1).concat(up.slice(0, -1));
  }
  function dentro([y, x], poly) {
    let ok = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [yi, xi] = poly[i], [yj, xj] = poly[j];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) ok = !ok;
    }
    return ok;
  }

  // Días en que factura: los que reúnen al menos el 20% de sus compras, hasta dos.
  function diasFacturados(ent) {
    const tot = Object.values(ent || {}).reduce((a, b) => a + b, 0);
    if (!tot) return '';
    const top = DAYS.filter(d => (ent[d] || 0) / tot >= .2).sort((a, b) => ent[b] - ent[a]).slice(0, 2);
    return ordenar(top);
  }

  /**
   * clientes: los del mapa (c.d = días asignados, c.an = inactivo). ventas: {clientes:{id:{compras, ent, ...}}, dias}.
   * Devuelve resumen, diagnóstico por localidad y clientes a revisar con su día sugerido.
   */
  function analizar(clientes, ventas, {suc = 'TODAS'} = {}) {
    const V = (ventas && ventas.clientes) || {}, semanas = ((ventas && ventas.dias) || 60) / 7;
    const act = clientes.filter(c => !c.an && (suc === 'TODAS' || c.suc === suc));
    const porLoc = new Map();
    for (const c of act) {
      const k = c.suc + '|' + c.loc;
      if (!porLoc.has(k)) porLoc.set(k, []);
      porLoc.get(k).push(c);
    }
    const filas = [];
    const revisar = [];
    for (const [k, cs] of porLoc) {
      const [sucursal, loc] = k.split('|');
      const asig = Object.fromEntries(DAYS.map(d => [d, cs.filter(c => (c.d || '').includes(d)).length]));
      const reales = Object.fromEntries(DAYS.map(d => [d, 0]));
      let conAcierto = 0, sumaAcierto = 0;
      const info = new Map();
      for (const c of cs) {
        const v = V[c.id], ent = (v && v.ent) || {}, tot = Object.values(ent).reduce((a, b) => a + b, 0);
        for (const d of DAYS) reales[d] += (ent[d] || 0) / semanas;
        const compras = v ? v.compras : 0;
        const acierto = c.d && tot ? DAYS.filter(d => c.d.includes(d)).reduce((t, d) => t + (ent[d] || 0), 0) / tot : null;
        if (acierto != null && compras >= MIN_COMPRAS) { conAcierto++; sumaAcierto += acierto; }
        info.set(c.id, {c, compras, compSem: compras / semanas, acierto, factura: compras >= MIN_COMPRAS ? diasFacturados(ent) : '', ent});
      }
      // Vecinos de la misma localidad y patrón dominante a su alrededor.
      const geo = cs.filter(c => isGeo(c) && c.d);
      for (const c of cs) {
        if (!isGeo(c)) continue;
        const vec = geo.filter(x => x !== c).map(x => [x, km(c, x)]).filter(([, m]) => m < VECINO_KM)
          .sort((a, b) => a[1] - b[1]).slice(0, VECINOS).map(([x]) => x);
        if (vec.length < 5) continue;
        const cnt = new Map(); vec.forEach(x => cnt.set(x.d, (cnt.get(x.d) || 0) + 1));
        const [pat, n] = [...cnt].sort((a, b) => b[1] - a[1])[0];
        const i = info.get(c.id);
        i.vecinos = pat; i.vecinosN = n; i.vecinosTot = vec.length;
        const mios = pares(c.d);
        i.aislado = !!c.d && pat !== c.d && n >= .75 * vec.length && ![...pares(pat)].some(d => mios.has(d));
      }
      // Superposición de zonas: clientes de un patrón dentro de la zona de otro (patrones con 5+ clientes).
      const pats = [...new Set(geo.map(c => c.d))].filter(p => geo.filter(c => c.d === p).length >= 5);
      let superp = null;
      if (pats.length >= 2) {
        const hs = Object.fromEntries(pats.map(p => [p, hull(geo.filter(c => c.d === p).map(c => [c.lat, c.lng]))]));
        const base = geo.filter(c => pats.includes(c.d));
        const aj = base.filter(c => pats.some(o => o !== c.d && hs[o].length >= 3 && dentro([c.lat, c.lng], hs[o])));
        superp = {ajenos: aj.length, total: base.length, pct: Math.round(aj.length / base.length * 100)};
      }
      // Diagnóstico de los días de camión de la localidad.
      const maxReal = Math.max(...DAYS.map(d => reales[d]));
      const notas = [];
      const sinAsignar = DAYS.filter(d => !asig[d] && reales[d] >= Math.max(3, .25 * maxReal));
      const flojos = DAYS.filter(d => asig[d] >= 5 && reales[d] < Math.max(3, .2 * maxReal));
      const aciertoLoc = conAcierto ? sumaAcierto / conAcierto : null;
      const conDias = cs.filter(c => c.d).length;
      const conVisita = cs.filter(c => c.d && trasVisita(c.vis));
      const cargoVisita = conVisita.filter(c => esVisita(c.d, c.vis));
      const notaVisita = conVisita.length >= 3 && cargoVisita.length >= .6 * conVisita.length
        ? {t:'bad', m:`Cargado el día de visita del vendedor (${cargoVisita.length} de ${conVisita.length})`,
           d:`La entrega sería el día siguiente a la visita: ${[...new Set(cargoVisita.map(c => trasVisita(c.vis)))].join(', ')}.`} : null;
      if (!conDias) notas.push({t:'bad', m:'Sin días cargados', d:`Días con entregas: ${DAYS.filter(d => reales[d] >= Math.max(1, .25 * maxReal)).join(', ') || '—'}`});
      else {
        const diasCamion = DAYS.filter(d => asig[d]);
        if (notaVisita) notas.push(notaVisita);
        if (diasCamion.length === 1 && aciertoLoc != null && aciertoLoc < .5 && sinAsignar.length)
          notas.push({t:'bad', m:`Día cargado ${diasCamion[0]}, se entrega ${sinAsignar.join(' y ')}`, d:'La planilla parece tener el día equivocado para toda la localidad.'});
        else {
          for (const d of sinAsignar) notas.push({t:'warn', m:`${d} sin clientes asignados`, d:`Se entrega igual: ~${Math.round(reales[d])} clientes por semana.`});
          if (aciertoLoc != null && aciertoLoc < .6) notas.push({t:'warn', m:`Solo ${Math.round(aciertoLoc * 100)}% factura en su día`, d:'Revisar los días de los clientes.'});
          for (const d of flojos) notas.push({t:'warn', m:`${d} con pocas entregas`, d:`${asig[d]} clientes lo tienen pero se entregan ~${reales[d].toFixed(1)} por semana. Evaluar sacarlo.`});
        }
        if (superp && superp.pct >= 25) notas.push({t:'warn', m:`Zonas superpuestas ${superp.pct}%`, d:'Los patrones de días están mezclados en la planta urbana; conviene sectorizar.'});
      }
      if (cs.length - conDias && conDias) notas.push({t:'warn', m:`${cs.length - conDias} sin días`, d:''});
      filas.push({suc:sucursal, loc, clientes:cs.length, sinDias:cs.length - conDias, asig, reales, acierto:aciertoLoc, superp, notas});

      // Clientes a revisar y día sugerido.
      const patronLoc = [...new Map(cs.filter(c => c.d).map(c => [c.d, 0]))].map(([p]) => [p, cs.filter(c => c.d === p).length]).sort((a, b) => b[1] - a[1]);
      for (const i of info.values()) {
        const {c} = i, motivos = [];
        if (!c.d) motivos.push('sindias');
        if (c.d && i.acierto != null && i.compras >= MIN_COMPRAS && i.acierto < .5) motivos.push('fuera');
        if (i.aislado) motivos.push('aislado');
        if (c.d && c.d.length >= 4 && i.compras && i.compSem < .5) motivos.push('frecuencia');
        if (esVisita(c.d, c.vis)) motivos.push('visita');
        const entVisita = trasVisita(c.vis);
        if (!motivos.length) continue;
        // Sugerencia: el patrón que mejor cubre los días en que factura. Cada día de más resta, y los
        // patrones que ya usan sus vecinos o su localidad tienen preferencia.
        let sug = '';
        const tot = Object.values(i.ent).reduce((a, b) => a + b, 0);
        if (i.compras >= MIN_COMPRAS && tot) {
          const locales = new Set([i.vecinos, ...patronLoc.map(p => p[0])].filter(Boolean));
          const cands = new Set([...locales, ...PATRONES, ...DAYS, ...(entVisita ? [entVisita] : [])]);
          let mejor = -1;
          for (const p of cands) {
            const cubre = DAYS.filter(d => p.includes(d)).reduce((t, d) => t + (i.ent[d] || 0), 0) / tot;
            const conVis = entVisita && [...pares(entVisita)].every(d => p.includes(d));
            const s = cubre - .1 * (p.length / 2 - 1) + (locales.has(p) ? .05 : 0) + (conVis ? .05 : 0);
            if (cubre >= .5 && s > mejor) { mejor = s; sug = p; }
          }
        }
        if (!sug && entVisita) {
          // Sin compras suficientes: el día siguiente a la visita, completado con el patrón de la zona si lo contiene.
          const zona = [i.vecinos, ...patronLoc.map(p => p[0])].find(p => p && [...pares(entVisita)].every(d => p.includes(d)));
          sug = zona || entVisita;
        }
        if (!sug && motivos.includes('aislado')) sug = i.vecinos;
        if (motivos.includes('frecuencia') && !motivos.some(m => m !== 'frecuencia')) {
          // Compra poco: proponer quedarse con el día en que más factura.
          const top = DAYS.filter(d => c.d.includes(d)).sort((a, b) => (i.ent[b] || 0) - (i.ent[a] || 0))[0];
          sug = (i.ent[top] || 0) ? top : '';
        }
        revisar.push({id:c.id, n:c.n, loc:c.loc, suc:c.suc, dom:c.dom, actual:c.d || '', sugerido:sug && sug !== c.d ? sug : '',
          factura:i.factura, vecinos:i.vecinos || '', visita:c.vis || '', acierto:i.acierto, compras:i.compras, compSem:i.compSem, motivos});
      }
    }
    const peso = r => (r.motivos.includes('visita') ? 5 : 0) + (r.motivos.includes('fuera') ? 4 : 0) + (r.motivos.includes('aislado') ? 3 : 0) + (r.motivos.includes('sindias') ? 2 : 0) + (r.sugerido ? 1 : 0);
    revisar.sort((a, b) => peso(b) - peso(a) || b.compras - a.compras);
    filas.sort((a, b) => a.suc.localeCompare(b.suc) || b.clientes - a.clientes);
    const conCompras = act.filter(c => c.d && V[c.id] && V[c.id].compras >= MIN_COMPRAS);
    const aciertos = conCompras.map(c => { const e = V[c.id].ent || {}, t = Object.values(e).reduce((a, b) => a + b, 0);
      return t ? DAYS.filter(d => c.d.includes(d)).reduce((s, d) => s + (e[d] || 0), 0) / t : 0; });
    const cuenta = m => revisar.filter(r => r.motivos.includes(m)).length;
    return {
      generado: new Date().toISOString(), desde: ventas && ventas.desde, hasta: ventas && ventas.hasta, suc,
      resumen: {activos: act.length, sinDias: cuenta('sindias'), fuera: cuenta('fuera'), aislados: cuenta('aislado'), frecuencia: cuenta('frecuencia'), visita: cuenta('visita'),
        conSugerencia: revisar.filter(r => r.sugerido).length, acierto: aciertos.length ? aciertos.reduce((a, b) => a + b, 0) / aciertos.length : null,
        evaluadosAcierto: aciertos.length, localidadesConAlerta: filas.filter(f => f.notas.some(n => n.t === 'bad' || n.t === 'warn')).length},
      localidades: filas, clientes: revisar,
    };
  }
  const api = {analizar, diasFacturados, trasVisita, DAYS};
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.RutasRevision = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
