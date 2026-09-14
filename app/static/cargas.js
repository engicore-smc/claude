'use strict';

const S = {
  jobId: null,
  estructuras: [],      // [{key, nombre, wind_span}]
  casos: [],
  condiciones: [],
  proyecto: null,       // {nombre, condicion, conductores[], grupos[]}
  activa: 0,
  opciones: [],         // pares (set, cable) del grupo activo
  resultados: [],
};

const CAMPOS_GRUPO = [
  ['fs', 'FS · factor de succión', 0.01],
  ['nc', 'Nc · conductores por fase', 1],
  ['espesor_hielo_mm', 'e · espesor de hielo [mm]', 0.1],
  ['n_cadenas', 'Ncad · n.º de cadenas', 1],
  ['n_aisladores', 'Naisl · n.º de aisladores', 1],
  ['alpha_deg', 'α · ángulo de deflexión [°]', 0.01],
  ['ht_m', 'Ht · altura del poste [m]', 0.1],
  ['t_servicio_kg', 'Carga de servicio en punta [kg]', 1],
  ['pv_kg_m2', 'Pv · presión de viento [kg/m²]', 1],
];

const CAMPOS_LINEA = [
  ['n_conductores', 'Conductores por fase', 1],
  ['diam_aislador_mm', 'Ø aislador [mm]', 0.1],
  ['long_aislador_mm', 'Longitud aislador [mm]', 1],
  ['peso_aislador_kg', 'Peso aislador [kg]', 0.1],
  ['n_aisladores', 'N.º de aisladores', 1],
  ['peso_ferreteria_kg', 'Ferretería y accesorios [kg]', 0.1],
];

const n2 = (v, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));

function grupoActivo() {
  return S.proyecto && S.proyecto.grupos[S.activa];
}

function grupoNuevo(nombre) {
  return {
    nombre, estructuras: [], casos: S.casos.slice(), n_postes: 1,
    fs: 1.1, nc: 1, espesor_hielo_mm: 0, n_cadenas: 1, n_aisladores: 1,
    alpha_deg: 0, ht_m: 15, t_servicio_kg: 800, pv_kg_m2: 80, lineas: [],
  };
}

// ------------------------------------------------------------------ carga
function pintarElegidos(input) {
  const destino = input.parentElement.querySelector('.picked');
  const nombres = Array.from(input.files || []).map((f) => f.name);
  destino.textContent = nombres.length ? `✓ ${nombres.join(', ')}` : '';
  input.parentElement.classList.toggle('filled', nombres.length > 0);
}
['#file-reportes', '#file-respaldo'].forEach((sel) =>
  $(sel).addEventListener('change', () => pintarElegidos($(sel))));

$('#btn-cargar').addEventListener('click', async () => {
  const boton = $('#btn-cargar');
  clearError();
  const datos = new FormData();
  const reportes = Array.from($('#file-reportes').files || []);
  const respaldo = Array.from($('#file-respaldo').files || []);
  if (!reportes.length) { fail('Selecciona los reportes de PLS-CADD.'); return; }
  [...reportes, ...respaldo].forEach((f) => datos.append('archivos', f));

  busy(boton, true, 'Analizando…');
  try {
    const r = await api('/api/mec/upload', { body: datos });
    S.jobId = r.job_id;
    S.estructuras = r.estructuras;
    S.casos = r.casos;
    S.condiciones = r.condiciones;
    S.proyecto = r.proyecto || {
      nombre: 'Cargas mecánicas', condicion: 'creep', conductores: [], grupos: [],
    };
    if (!S.proyecto.grupos.length) S.proyecto.grupos.push(grupoNuevo('Hoja 1'));
    S.activa = 0;
    $('#estado-carga').textContent =
      `${S.estructuras.length} estructuras · ${S.casos.length} casos climáticos` +
      (r.proyecto ? ` · respaldo con ${r.proyecto.grupos.length} hoja(s)` : '');
    if (r.avisos && r.avisos.length) {
      $('#global-error').replaceChildren(notice('warn', 'Avisos al leer los reportes:', r.avisos));
    }
    ['#paso-proyecto', '#paso-hojas', '#paso-resumen'].forEach((id) => { $(id).hidden = false; });
    render();
  } catch (e) {
    fail(e.message);
  } finally {
    busy(boton, false);
  }
});

// ------------------------------------------------------- proyecto y cables
function render() {
  $('#proy-nombre').value = S.proyecto.nombre;
  const cond = $('#proy-condicion');
  cond.replaceChildren(...S.condiciones.map((c) =>
    el('option', { value: c, ...(c === S.proyecto.condicion ? { selected: 'selected' } : {}) }, c)));
  renderConductores();
  renderTabs();
  refrescarOpciones();   // trae las opciones de la hoja activa y luego pinta
}

$('#proy-nombre').addEventListener('input', (e) => { S.proyecto.nombre = e.target.value; });
$('#proy-condicion').addEventListener('change', (e) => {
  S.proyecto.condicion = e.target.value;
  fail('La condición del cable se aplica al leer los reportes: vuelve a pulsar «Analizar» con el respaldo descargado.');
});

function renderConductores() {
  const cuerpo = $('#tabla-conductores tbody');
  cuerpo.replaceChildren();
  S.proyecto.conductores.forEach((c, i) => {
    const campo = (clave, paso) => {
      const input = el('input', { type: 'number', step: String(paso), value: c[clave] ?? '' });
      input.addEventListener('input', () => {
        c[clave] = input.value === '' ? (clave === 'peso_dan_m' ? null : 0) : Number(input.value);
        evaluar();
      });
      return input;
    };
    const nombre = el('input', { type: 'text', value: c.nombre || '' });
    nombre.addEventListener('input', () => { c.nombre = nombre.value; evaluar(); });
    cuerpo.append(el('tr', {},
      el('td', {}, campo('cable', 0.01)),
      el('td', {}, nombre),
      el('td', {}, campo('diametro_mm', 0.0001)),
      el('td', {}, campo('peso_dan_m', 0.000001)),
      el('td', {}, el('button', {
        class: 'btn-x', type: 'button', title: 'Quitar',
        onclick: () => { S.proyecto.conductores.splice(i, 1); renderConductores(); evaluar(); },
      }, '×'))));
  });
}

$('#btn-conductor').addEventListener('click', () => {
  S.proyecto.conductores.push({ cable: 0, nombre: '', diametro_mm: 0, peso_dan_m: null });
  renderConductores();
});

/** Asegura que el catálogo tenga los cables que usan las líneas del proyecto.
 *  Solo añade: nunca borra, para no quitar un conductor añadido a mano. Se
 *  basa en las líneas en uso y no en las opciones ofrecidas, de modo que no se
 *  acumulan cables que se llegaron a ver una vez (por ejemplo los de hielo). */
function sincronizarCatalogo() {
  const conocidos = new Set(S.proyecto.conductores.map((c) => Number(c.cable).toFixed(6)));
  let nuevos = 0;
  S.proyecto.grupos.forEach((g) => (g.lineas || []).forEach((l) => {
    const clave = Number(l.cable).toFixed(6);
    if (!conocidos.has(clave)) {
      conocidos.add(clave);
      S.proyecto.conductores.push({ cable: l.cable, nombre: '', diametro_mm: 0, peso_dan_m: null });
      nuevos += 1;
    }
  }));
  if (nuevos) {
    S.proyecto.conductores.sort((a, b) => a.cable - b.cable);
    renderConductores();
  }
}

$('#btn-conductor').addEventListener('click', () => {
  S.proyecto.conductores.push({ cable: 0, nombre: '', diametro_mm: 0, peso_dan_m: null });
  renderConductores();
});

/** El catálogo contiene exactamente los cables que usan las líneas del proyecto.
 *  Derivarlo de las líneas y no de las opciones ofrecidas evita que se acumulen
 *  conductores que se llegaron a ver una vez y ya no se usan. */
function sincronizarCatalogo() {
  const usados = new Map();
  S.proyecto.grupos.forEach((g) => (g.lineas || []).forEach((l) => {
    usados.set(Number(l.cable).toFixed(6), l.cable);
  }));
  const antes = S.proyecto.conductores.length;
  // Se conservan los que siguen en uso, con lo que el usuario ya haya escrito.
  const porClave = new Map(S.proyecto.conductores.map((c) => [Number(c.cable).toFixed(6), c]));
  S.proyecto.conductores = [...usados.entries()]
    .sort((a, b) => a[1] - b[1])
    .map(([clave, cable]) => porClave.get(clave)
      || { cable, nombre: '', diametro_mm: 0, peso_dan_m: null });
  if (S.proyecto.conductores.length !== antes
      || S.proyecto.conductores.some((c, i) => c !== [...porClave.values()][i])) {
    renderConductores();
  }
}

// ------------------------------------------------------------------ hojas
function renderTabs() {
  const host = $('#tabs');
  host.replaceChildren();
  S.proyecto.grupos.forEach((g, i) => {
    const tab = el('button', {
      class: `tab${i === S.activa ? ' on' : ''}`, type: 'button',
      onclick: () => { S.activa = i; renderTabs(); refrescarOpciones(); },
    }, g.nombre || `Hoja ${i + 1}`);
    if (S.proyecto.grupos.length > 1) {
      tab.append(el('span', {
        class: 'x', title: 'Eliminar hoja',
        onclick: (ev) => {
          ev.stopPropagation();
          if (!confirm(`¿Eliminar la hoja «${g.nombre}»?`)) return;
          S.proyecto.grupos.splice(i, 1);
          S.activa = Math.max(0, Math.min(S.activa, S.proyecto.grupos.length - 1));
          renderTabs(); refrescarOpciones();
        },
      }, '×'));
    }
    host.append(tab);
  });
  host.append(el('button', {
    class: 'tab add', type: 'button',
    onclick: () => {
      S.proyecto.grupos.push(grupoNuevo(`Hoja ${S.proyecto.grupos.length + 1}`));
      S.activa = S.proyecto.grupos.length - 1;
      renderTabs(); refrescarOpciones();
    },
  }, '+ Nueva hoja'));
  const activo = S.proyecto.grupos[S.activa];
  if (!activo) return;
  const copia = el('button', {
    class: 'tab add', type: 'button', title: 'Duplicar la hoja activa',
    onclick: () => {
      S.proyecto.grupos.splice(S.activa + 1, 0,
        { ...JSON.parse(JSON.stringify(activo)), nombre: `${activo.nombre} (copia)` });
      S.activa += 1;
      renderTabs(); refrescarOpciones();
    },
  }, 'Duplicar');
  host.append(copia);
}

function chips(valores, elegidos, alCambiar, etiqueta = (v) => v) {
  const host = el('div', { class: 'chips' });
  valores.forEach((v) => {
    const on = elegidos.includes(v);
    const chip = el('label', { class: `chip${on ? ' on' : ''}` }, etiqueta(v));
    chip.addEventListener('click', () => {
      const i = elegidos.indexOf(v);
      if (i >= 0) elegidos.splice(i, 1); else elegidos.push(v);
      alCambiar();
    });
    host.append(chip);
  });
  return host;
}

function numero(objeto, clave, paso, alCambiar) {
  const input = el('input', { type: 'number', step: String(paso), value: objeto[clave] ?? 0 });
  input.addEventListener('input', () => {
    objeto[clave] = input.value === '' ? 0 : Number(input.value);
    alCambiar();
  });
  return input;
}

function renderEditor() {
  const host = $('#editor-hoja');
  host.replaceChildren();
  const g = grupoActivo();
  if (!g) return;

  const nombre = el('input', { type: 'text', value: g.nombre });
  nombre.addEventListener('input', () => { g.nombre = nombre.value; renderTabs(); evaluarDiferido(); });

  host.append(el('div', { class: 'grid cols-2' },
    el('div', {}, el('label', { class: 'field' }, 'Nombre de la hoja'), nombre),
    el('div', {}, el('label', { class: 'field' }, 'N.º de postes'),
      numero(g, 'n_postes', 1, evaluarDiferido))));

  host.append(el('label', { class: 'field', style: 'margin-top:16px' }, 'Estructuras a evaluar'));
  host.append(chips(S.estructuras.map((e) => e.key), g.estructuras,
    () => { renderEditor(); refrescarOpciones(); }));

  host.append(el('label', { class: 'field', style: 'margin-top:16px' }, 'Casos climáticos'));
  host.append(chips(S.casos, g.casos, () => { renderEditor(); refrescarOpciones(); }));

  host.append(el('h3', { class: 'sub' }, 'Parámetros generales'));
  const grid = el('div', { class: 'grid cols-3' });
  CAMPOS_GRUPO.forEach(([clave, etiqueta, paso]) => {
    grid.append(el('div', {}, el('label', { class: 'field' }, etiqueta), numero(g, clave, paso, evaluarDiferido)));
  });
  host.append(grid);
  const efectiva = (g.ht_m || 0) - (g.ht_m || 0) / 6;
  host.append(el('p', { class: 'muted', style: 'margin:8px 0 0' },
    `Enterramiento ${((g.ht_m || 0) / 6).toFixed(2)} m · altura efectiva ${efectiva.toFixed(2)} m`));

  host.append(el('h3', { class: 'sub' }, 'Líneas de conductor'));
  host.append(el('p', { class: 'muted', style: 'margin:0 0 12px' },
    'Cada línea es un par (set, cable): así una línea no puede mezclar dos conductores.'));
  const lineas = el('div', { id: 'lineas' });
  host.append(lineas);
  renderLineas(lineas, g);

  host.append(el('div', { class: 'actions' },
    el('button', {
      class: 'ghost small', type: 'button',
      onclick: () => {
        const o = S.opciones[0];
        g.lineas.push({
          set_no: o ? o.set : '', cable: o ? o.cable : 0, fases: 1, n_conductores: 1,
          diam_aislador_mm: 0, long_aislador_mm: 0, peso_aislador_kg: 0,
          n_aisladores: 0, peso_ferreteria_kg: 0, alturas_amarre: [0],
        });
        renderEditor(); evaluar();
      },
    }, '+ Añadir línea'),
    el('button', {
      class: 'ghost small', type: 'button', title: 'Una línea por cada par (set, cable) disponible',
      onclick: () => {
        g.lineas = S.opciones.map((o) => ({
          set_no: o.set, cable: o.cable, fases: 1, n_conductores: 1,
          diam_aislador_mm: 0, long_aislador_mm: 0, peso_aislador_kg: 0,
          n_aisladores: 0, peso_ferreteria_kg: 0, alturas_amarre: [0],
        }));
        sincronizarCatalogo(); renderEditor(); evaluar();
      },
    }, 'Añadir todas las disponibles')));

  host.append(el('div', { id: 'resultado-hoja', style: 'margin-top:20px' }));
  pintarResultadoHoja();
}

function renderLineas(host, g) {
  host.replaceChildren();
  if (!g.lineas.length) {
    host.append(notice('warn', 'Esta hoja no tiene líneas de conductor todavía.'));
    return;
  }
  g.lineas.forEach((linea, i) => {
    const tarjeta = el('div', { class: 'linea' });

    // --- selector (set, cable)
    const select = el('select', {});
    const clave = (s, c) => `${s}|${Number(c).toFixed(6)}`;
    const actual = clave(linea.set_no, linea.cable);
    let encontrado = false;
    S.opciones.forEach((o) => {
      const v = clave(o.set, o.cable);
      const opcion = el('option', { value: v },
        `${o.etiqueta} — ${o.amarres} amarre(s), máx ${n2(o.tension_max, 1)} kg`);
      if (v === actual) { opcion.selected = true; encontrado = true; }
      select.append(opcion);
    });
    if (!encontrado) {
      const perdida = el('option', { value: actual },
        `Set ${linea.set_no} · ${Number(linea.cable)} daN/m — no está en estas estructuras`);
      perdida.selected = true;
      select.prepend(perdida);
    }
    select.addEventListener('change', () => {
      const [s, c] = select.value.split('|');
      linea.set_no = s;
      linea.cable = Number(c);
      sincronizarCatalogo();
      evaluar();
    });

    const fases = el('input', { type: 'number', min: '1', step: '1', value: linea.fases });
    fases.addEventListener('input', () => {
      const n = Math.max(1, Number(fases.value) || 1);
      linea.fases = n;
      while (linea.alturas_amarre.length < n) {
        linea.alturas_amarre.push(linea.alturas_amarre[linea.alturas_amarre.length - 1] ?? 0);
      }
      linea.alturas_amarre.length = n;
      renderLineas(host, g);
      evaluar();
    });

    tarjeta.append(el('div', { class: 'cab' },
      el('div', { class: 'ancho' }, el('label', { class: 'field' }, `Línea ${i + 1} · set y cable`), select),
      el('div', {}, el('label', { class: 'field' }, 'N.º de fases'), fases),
      el('div', { style: 'flex:0 0 auto' }, el('label', { class: 'field' }, ' '),
        el('button', {
          class: 'btn-x', type: 'button', title: 'Quitar línea',
          onclick: () => { g.lineas.splice(i, 1); renderEditor(); evaluar(); },
        }, '×'))));

    const grid = el('div', { class: 'grid cols-3' });
    CAMPOS_LINEA.forEach(([campo, etiqueta, paso]) => {
      grid.append(el('div', {}, el('label', { class: 'field' }, etiqueta),
        numero(linea, campo, paso, evaluarDiferido)));
    });
    tarjeta.append(grid);

    // --- alturas de amarre, una por fase
    tarjeta.append(el('label', { class: 'field', style: 'margin:14px 0 6px' },
      'Altura de amarre bajo la punta [m], por fase'));
    const alturas = el('div', { class: 'alturas' });
    for (let f = 0; f < linea.fases; f += 1) {
      const input = el('input', { type: 'number', step: '0.01', value: linea.alturas_amarre[f] ?? 0 });
      input.addEventListener('input', () => {
        linea.alturas_amarre[f] = input.value === '' ? 0 : Number(input.value);
        evaluarDiferido();
      });
      alturas.append(el('div', {}, el('label', {}, `Fase ${f + 1}`), input));
    }
    tarjeta.append(alturas);
    host.append(tarjeta);
  });
}

// ------------------------------------------------------------- opciones
async function refrescarOpciones() {
  const g = grupoActivo();
  if (!g || !S.jobId) return;
  try {
    const r = await api('/api/mec/opciones', {
      body: { job_id: S.jobId, estructuras: g.estructuras, casos: g.casos },
    });
    S.opciones = r.opciones;
    renderEditor();
    evaluar();
  } catch (e) {
    fail(e.message);
  }
}

// ------------------------------------------------------------- resultados
let temporizador = null;
function evaluarDiferido() {
  clearTimeout(temporizador);
  temporizador = setTimeout(evaluar, 260);
}

async function evaluar() {
  if (!S.jobId || !S.proyecto) return;
  $('#estado-calculo').textContent = 'calculando…';
  try {
    const r = await api('/api/mec/evaluar', { body: { job_id: S.jobId, proyecto: S.proyecto } });
    S.resultados = r.resultados;
    pintarResumen();
    pintarResultadoHoja();
    $('#estado-calculo').textContent = '';
  } catch (e) {
    $('#estado-calculo').textContent = '';
    fail(e.message);
  }
}

function barra(uso) {
  const pct = uso === null || uso === undefined ? 0 : Math.min(uso * 100, 100);
  const clase = uso > 1 ? 'bar pasa' : uso > 0.85 ? 'bar alto' : 'bar';
  return el('div', { class: 'uso' },
    el('span', { text: uso === null || uso === undefined ? '—' : `${(uso * 100).toFixed(1)} %` }),
    el('div', { class: clase }, el('i', { style: `width:${pct.toFixed(1)}%` })));
}

function pintarResumen() {
  const cuerpo = $('#tabla-resumen tbody');
  cuerpo.replaceChildren();
  S.resultados.forEach((r, i) => {
    const g = S.proyecto.grupos[i];
    cuerpo.append(el('tr', {},
      el('td', {}, el('strong', { text: r.nombre })),
      el('td', { text: (g.estructuras || []).join(', ') || '—' }),
      el('td', { class: 'num', text: n2(r.transversal_calculada) }),
      el('td', { class: 'num', text: n2(r.transversal_admisible) }),
      el('td', { class: 'num' }, barra(r.uso_transversal)),
      el('td', { class: 'num', text: n2(r.momento_calculado) }),
      el('td', { class: 'num', text: n2(r.momento_admisible) }),
      el('td', { class: 'num' }, barra(r.uso_momento)),
      el('td', { class: 'num', text: n2(r.vertical_total) }),
      el('td', {}, el('span', { class: `badge ${r.cumple ? 'ok' : 'err'}` },
        r.cumple ? 'CUMPLE' : 'NO CUMPLE'))));
  });
}

function tarjeta(clave, valor, detalle) {
  return el('div', { class: 'res-card' },
    el('div', { class: 'k', text: clave }),
    el('div', { class: 'v', text: valor }),
    el('div', { class: 'd', text: detalle }));
}

function pintarResultadoHoja() {
  const host = $('#resultado-hoja');
  if (!host) return;
  const r = S.resultados[S.activa];
  host.replaceChildren();
  if (!r) return;

  const pct = (u) => (u === null || u === undefined ? '—' : `${(u * 100).toFixed(1)} %`);
  host.append(el('div', { class: 'res-cards' },
    tarjeta('Carga transversal', `${n2(r.transversal_calculada)} kg`,
      `admisible ${n2(r.transversal_admisible, 0)} kg · uso ${pct(r.uso_transversal)}`),
    tarjeta('Momento', `${n2(r.momento_calculado)} kg·m`,
      `admisible ${n2(r.momento_admisible, 0)} kg·m · uso ${pct(r.uso_momento)}`),
    tarjeta('Carga vertical total', `${n2(r.vertical_total)} kg`,
      `altura efectiva ${n2(r.altura_efectiva)} m`)));

  const tabla = el('table', { class: 'data' },
    el('thead', {}, el('tr', {},
      ...['Set', 'Cable', 'Conductor', 'Fases', 'Luz viento [m]', 'Tensión [kg]',
          'Transversal [kg]', 'Luz peso [m]', 'Vertical [kg]'].map((h) => el('th', { text: h })))));
  const cuerpo = el('tbody', {});
  r.lineas.forEach((l) => {
    cuerpo.append(el('tr', {},
      el('td', {}, el('strong', { text: l.set_no })),
      el('td', { text: `${l.cable} daN/m` }),
      el('td', { text: l.nombre || '—' }),
      el('td', { class: 'num', text: String(l.fases) }),
      el('td', { class: 'num', text: n2(l.luz_viento, 1) }),
      el('td', { class: 'num', text: n2(l.tension_kg) }),
      el('td', { class: 'num', text: n2(l.carga_transversal) }),
      el('td', { class: 'num', text: n2(l.luz_peso, 1) }),
      el('td', { class: 'num', text: n2(l.carga_vertical) })));
  });
  tabla.append(cuerpo);
  host.append(el('div', { class: 'table-scroll' }, tabla));

  if (r.momentos.length) {
    const mt = el('table', { class: 'data' },
      el('thead', {}, el('tr', {},
        ...['Altura de amarre [m]', 'Brazo [m]', 'Momento [kg·m]'].map((h) => el('th', { text: h })))),
      el('tbody', {}, ...r.momentos.map((m) => el('tr', {},
        el('td', { class: 'num', text: n2(m.altura_amarre) }),
        el('td', { class: 'num', text: n2(m.brazo) }),
        el('td', { class: 'num', text: n2(m.momento) })))));
    host.append(el('h3', { class: 'sub' }, 'Momentos por altura de amarre'));
    host.append(el('div', { class: 'table-scroll' }, mt));
  }

  const avisos = [...(r.avisos || [])];
  r.lineas.forEach((l) => (l.avisos || []).forEach((a) => avisos.push(`Set ${l.set_no}: ${a}`)));
  if (avisos.length) host.append(notice('warn', 'Revisa esta hoja:', [...new Set(avisos)]));
}

// ------------------------------------------------------------- respaldo
$('#btn-respaldo').addEventListener('click', async () => {
  const boton = $('#btn-respaldo');
  busy(boton, true, 'Generando…');
  try {
    const respuesta = await api('/api/mec/respaldo', {
      body: { job_id: S.jobId, proyecto: S.proyecto }, raw: true,
    });
    const blob = await respuesta.blob();
    const m = /filename="([^"]+)"/.exec(respuesta.headers.get('Content-Disposition') || '');
    const url = URL.createObjectURL(blob);
    const enlace = el('a', { href: url, download: m ? m[1] : 'respaldo.xlsx' });
    document.body.append(enlace);
    enlace.click();
    enlace.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    fail(e.message);
  } finally {
    busy(boton, false);
  }
});
