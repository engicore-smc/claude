'use strict';

const S = {
  jobId: null,
  estructuras: [],      // [{key, nombre, wind_span}]
  casos: [],
  condiciones: [],
  proyecto: null,       // {nombre, condicion, conductores[], grupos[]}
  activa: 0,
  opciones: [],         // pares (set, cable) del grupo activo
  poste: null,          // altura y cargas de ensayo que trae el reporte
  resultados: [],
};

// Mismos símbolos, descripciones y unidades que el libro de Excel.
const PARAMETROS = [
  ['fs', 'FS', 'Factor de succión', '-', 0.01],
  ['nc', 'Nc', 'Número de conductores por fase', 'un', 1],
  ['espesor_hielo_mm', 'e', 'Espesor de hielo', 'mm', 0.1],
  ['n_cadenas', 'Ncad', 'Número de cadenas de aisladores', 'un', 1],
  ['n_aisladores', 'Naisl', 'Número de aisladores', 'un', 1],
  ['alpha_deg', 'α', 'Ángulo de deflexión de la línea', '°', 0.01],
  ['ht_m', 'Ht', 'Altura total del poste', 'm', 0.1],
  ['t_servicio_kg', 'Tserv', 'Carga de servicio en la punta', 'kg', 1],
  ['pv_kg_m2', 'Pv', 'Presión de viento máximo', 'kg/m²', 1],
];

// Valores que el usuario escribe una sola vez y se reutilizan en cada hoja nueva.
const CLAVE_DEFAULTS = 'plscadd.cargas.defaults';
const DEFAULTS_FABRICA = {
  fs: 1.1, nc: 1, espesor_hielo_mm: 0, n_cadenas: 1, n_aisladores: 1,
  alpha_deg: 0, ht_m: 15, t_servicio_kg: 800, pv_kg_m2: 80,
};

function leerDefaults() {
  try {
    return { ...DEFAULTS_FABRICA, ...JSON.parse(localStorage.getItem(CLAVE_DEFAULTS) || '{}') };
  } catch {
    return { ...DEFAULTS_FABRICA };
  }
}

function guardarDefaults(grupo) {
  const guardar = { ...leerDefaults() };
  PARAMETROS.forEach(([clave]) => { guardar[clave] = grupo[clave]; });
  try { localStorage.setItem(CLAVE_DEFAULTS, JSON.stringify(guardar)); } catch { /* sin localStorage */ }
}

const n2 = (v, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));

function grupoActivo() {
  return S.proyecto && S.proyecto.grupos[S.activa];
}

function grupoNuevo(nombre) {
  const d = leerDefaults();
  return {
    nombre, estructuras: [], casos: S.casos.slice(), n_postes: 1,
    fs: d.fs, nc: d.nc, espesor_hielo_mm: d.espesor_hielo_mm,
    n_cadenas: d.n_cadenas, n_aisladores: d.n_aisladores, alpha_deg: d.alpha_deg,
    ht_m: d.ht_m, t_servicio_kg: d.t_servicio_kg, pv_kg_m2: d.pv_kg_m2, lineas: [],
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
      nombre: 'Cargas mecánicas', condicion: 'creep',
      conductores: [], aisladores: [], grupos: [],
    };
    S.proyecto.aisladores = S.proyecto.aisladores || [];
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
  renderAisladores();
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
      el('td', {}, campo('n_conductores', 1)),
      el('td', {}, el('button', {
        class: 'btn-x', type: 'button', title: 'Quitar',
        onclick: () => { S.proyecto.conductores.splice(i, 1); renderConductores(); evaluar(); },
      }, '×'))));
  });
}

function renderAisladores() {
  const cuerpo = $('#tabla-aisladores tbody');
  cuerpo.replaceChildren();
  (S.proyecto.aisladores || []).forEach((a, i) => {
    const campo = (clave, paso) => {
      const input = el('input', { type: 'number', step: String(paso), value: a[clave] ?? 0 });
      input.addEventListener('input', () => {
        a[clave] = input.value === '' ? 0 : Number(input.value);
        evaluarDiferido();
      });
      return input;
    };
    const nombre = el('input', { type: 'text', value: a.nombre || '' });
    nombre.addEventListener('change', () => {
      const anterior = a.nombre;
      a.nombre = nombre.value;
      // Las líneas que apuntaban a esta cadena siguen apuntándole.
      S.proyecto.grupos.forEach((g) => g.lineas.forEach((l) => {
        if (l.aislador === anterior) l.aislador = a.nombre;
      }));
      renderEditor();
      evaluar();
    });
    cuerpo.append(el('tr', {},
      el('td', {}, nombre),
      el('td', {}, campo('diametro_mm', 0.1)),
      el('td', {}, campo('longitud_mm', 1)),
      el('td', {}, campo('peso_kg', 0.1)),
      el('td', {}, campo('n_aisladores', 1)),
      el('td', {}, campo('peso_ferreteria_kg', 0.1)),
      el('td', {}, el('button', {
        class: 'btn-x', type: 'button', title: 'Quitar',
        onclick: () => { S.proyecto.aisladores.splice(i, 1); renderAisladores(); renderEditor(); evaluar(); },
      }, '×'))));
  });
  if (!(S.proyecto.aisladores || []).length) {
    cuerpo.append(el('tr', {}, el('td', { colspan: '7', class: 'muted' },
      'Sin cadenas todavía. Añade una para poder elegirla en las hojas.')));
  }
}

$('#btn-aislador').addEventListener('click', () => {
  S.proyecto.aisladores = S.proyecto.aisladores || [];
  S.proyecto.aisladores.push({
    nombre: `Cadena ${S.proyecto.aisladores.length + 1}`,
    diametro_mm: 0, longitud_mm: 0, peso_kg: 0, n_aisladores: 0, peso_ferreteria_kg: 0,
  });
  renderAisladores();
  renderEditor();
});

$('#btn-conductor').addEventListener('click', () => {
  S.proyecto.conductores.push({ cable: 0, nombre: '', diametro_mm: 0, peso_dan_m: null, n_conductores: 1 });
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
      S.proyecto.conductores.push({ cable: l.cable, nombre: '', diametro_mm: 0, peso_dan_m: null, n_conductores: 1 });
      nuevos += 1;
    }
  }));
  if (nuevos) {
    S.proyecto.conductores.sort((a, b) => a.cable - b.cable);
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

// ------------------------------------------------- celdas de la "hoja"
function celdaEd(objeto, clave, paso, opciones = {}) {
  const input = el('input', {
    type: opciones.texto ? 'text' : 'number',
    ...(opciones.texto ? {} : { step: String(paso) }),
    ...(opciones.min !== undefined ? { min: String(opciones.min) } : {}),
    value: objeto[clave] ?? (opciones.texto ? '' : 0),
  });
  input.addEventListener('input', () => {
    objeto[clave] = opciones.texto ? input.value
      : (input.value === '' ? 0 : Number(input.value));
    (opciones.alCambiar || evaluarDiferido)();
  });
  return el('td', { class: 'ed' }, input);
}

function celdaCalc(valor, decimales = 2, fuerte = false, clave = null) {
  const atributos = { class: `calc${fuerte ? ' fuerte' : ''}`, text: n2(valor, decimales) };
  // La clave permite refrescar el valor sin reconstruir la tabla, para no
  // robarle el foco al campo que se esté escribiendo.
  if (clave) { atributos['data-calc'] = clave; atributos['data-dec'] = String(decimales); }
  return el('td', atributos);
}

function filaParam(simbolo, descripcion, celda, unidad) {
  return el('tr', {},
    el('td', { class: 'sim', text: simbolo }),
    el('td', { class: 't', text: descripcion }),
    celda,
    el('td', { class: 'uni', text: unidad }));
}

function bloque(titulo, derecha) {
  const caja = el('div', { class: 'xl' });
  const cab = el('div', { class: 'xl-tit' }, titulo);
  if (derecha) cab.append(el('span', { class: 'der', text: derecha }));
  caja.append(cab);
  return caja;
}

function cabecera(...titulos) {
  return el('thead', {}, el('tr', {}, ...titulos.map((t) => el('th', {}, t))));
}

function etiquetaLinea(linea) {
  const conductor = S.proyecto.conductores.find(
    (c) => Number(c.cable).toFixed(6) === Number(linea.cable).toFixed(6));
  const nombre = conductor && conductor.nombre ? ` ${conductor.nombre}` : '';
  return `Set ${linea.set_no} · ${Number(linea.cable)}${nombre}`;
}

function conductorDe(linea) {
  return S.proyecto.conductores.find(
    (c) => Number(c.cable).toFixed(6) === Number(linea.cable).toFixed(6)) || {};
}

function aisladorDe(linea) {
  return (S.proyecto.aisladores || []).find((a) => a.nombre === linea.aislador) || {};
}

/** Selector de cadena: en la hoja solo se elige el nombre y vienen sus datos. */
function selectorAislador(linea) {
  const select = el('select', {});
  select.append(el('option', { value: '' }, '— sin cadena —'));
  (S.proyecto.aisladores || []).forEach((a) => {
    const opcion = el('option', { value: a.nombre }, a.nombre || '(sin nombre)');
    if (a.nombre === linea.aislador) opcion.selected = true;
    select.append(opcion);
  });
  if (linea.aislador && !(S.proyecto.aisladores || []).some((a) => a.nombre === linea.aislador)) {
    const perdida = el('option', { value: linea.aislador }, `${linea.aislador} — no está en el catálogo`);
    perdida.selected = true;
    select.append(perdida);
  }
  select.addEventListener('change', () => {
    linea.aislador = select.value;
    renderEditor();
    evaluar();
  });
  return select;
}

// --------------------------------------------------------------- editor
function renderEditor() {
  const host = $('#editor-hoja');
  host.replaceChildren();
  const g = grupoActivo();
  if (!g) return;
  const r = S.resultados[S.activa];

  host.append(el('div', { class: 'xl-dos' }, bloqueParametros(g), bloqueSeleccion(g)));
  host.append(bloqueTransversal(g, r));
  host.append(bloqueVertical(g, r));
  host.append(bloqueMomentos(g, r));
}

// --- 1. parámetros generales
function bloqueParametros(g) {
  const caja = bloque('1. Parámetros generales');
  const cuerpo = el('tbody', {});
  PARAMETROS.forEach(([clave, simbolo, descripcion, unidad, paso]) => {
    cuerpo.append(filaParam(simbolo, descripcion, celdaEd(g, clave, paso), unidad));
  });
  const enterramiento = (g.ht_m || 0) / 6;
  cuerpo.append(filaParam('', 'Enterramiento', celdaCalc(enterramiento), 'm'));
  cuerpo.append(filaParam('', 'Altura efectiva', celdaCalc((g.ht_m || 0) - enterramiento), 'm'));
  caja.append(el('table', {}, cuerpo));

  const pie = el('div', { class: 'xl-pie' });
  pie.append(el('button', {
    class: 'ghost small', type: 'button',
    title: 'Se aplicarán a las hojas nuevas de cualquier proyecto',
    onclick: () => { guardarDefaults(g); pie.append(el('span', { class: 'badge ok', text: 'guardados' })); },
  }, 'Guardar como valores por defecto'));
  pie.append(el('button', {
    class: 'ghost small', type: 'button',
    onclick: () => { Object.assign(g, leerDefaults()); renderEditor(); evaluar(); },
  }, 'Restaurar mis valores'));
  caja.append(pie);

  // Altura y carga admisible que trae el reporte para ese tipo de poste.
  const p = S.poste;
  if (p && (p.altura_m !== null || p.transversal_kg !== null)) {
    const iguales = (p.altura_m === null || Math.abs(p.altura_m - g.ht_m) < 1e-9)
      && (p.transversal_kg === null || Math.abs(p.transversal_kg - g.t_servicio_kg) < 1e-9);
    if (!iguales) {
      const usar = el('a', {
        onclick: () => {
          if (p.altura_m !== null) g.ht_m = p.altura_m;
          if (p.transversal_kg !== null) g.t_servicio_kg = p.transversal_kg;
          renderEditor(); evaluar();
        },
      }, 'usar estos valores');
      caja.append(el('div', { class: 'pista' },
        `El reporte indica ${p.altura_m ?? '—'} m y ${p.transversal_kg ?? '—'} kg `
        + `para ${(p.archivos || []).join(', ') || 'este poste'} — `, usar));
    }
    (p.avisos || []).forEach((a) => caja.append(el('div', { class: 'pista', text: a })));
  }
  return caja;
}

// --- estructuras, casos y nombre de la hoja
function bloqueSeleccion(g) {
  const caja = bloque('Alcance de la hoja');
  const cuerpo = el('tbody', {});
  const nombre = el('input', { type: 'text', value: g.nombre });
  nombre.addEventListener('input', () => { g.nombre = nombre.value; renderTabs(); evaluarDiferido(); });
  cuerpo.append(el('tr', {}, el('td', { class: 't', text: 'Nombre de la hoja' }),
    el('td', { class: 'ed' }, nombre)));
  cuerpo.append(el('tr', {}, el('td', { class: 't', text: 'N.º de postes' }),
    celdaEd(g, 'n_postes', 1, { min: 1 })));
  caja.append(el('table', {}, cuerpo));

  const pie = el('div', { style: 'padding:12px' });
  pie.append(el('label', { class: 'field' }, 'Estructuras a evaluar'));
  pie.append(chips(S.estructuras.map((e) => e.key), g.estructuras,
    () => { renderEditor(); refrescarOpciones(); }));
  pie.append(el('label', { class: 'field', style: 'margin-top:14px' }, 'Casos climáticos'));
  pie.append(chips(S.casos, g.casos, () => { renderEditor(); refrescarOpciones(); }));
  caja.append(pie);
  return caja;
}

// --- 2. cargas transversales y longitudinales
function bloqueTransversal(g, r) {
  const caja = bloque('2. Cargas transversales y longitudinales');
  const tabla = el('table', {}, cabecera(
    'Set · cable', 'Fases', 'Ø conductor [mm]', 'Cadena de aisladores', 'Ø aislador [mm]',
    'Longitud aislador [mm]', 'Luz viento [m]', 'Tensión longitudinal [kg]',
    'Carga transversal [kg]', ''));
  const cuerpo = el('tbody', {});
  g.lineas.forEach((linea, i) => {
    const res = r && r.lineas[i];
    cuerpo.append(el('tr', {},
      el('td', { class: 'ed' }, selectorLinea(linea)),
      celdaEd(linea, 'fases', 1, { min: 1, alCambiar: () => ajustarFases(linea) }),
      celdaCalc(conductorDe(linea).diametro_mm, 4, false, `l${i}.diam`),
      el('td', { class: 'ed' }, selectorAislador(linea)),
      celdaCalc(aisladorDe(linea).diametro_mm, 1, false, `l${i}.ais_diam`),
      celdaCalc(aisladorDe(linea).longitud_mm, 1, false, `l${i}.ais_long`),
      celdaCalc(res && res.luz_viento, 1, false, `l${i}.luz_viento`),
      celdaCalc(res && res.tension_kg, 2, false, `l${i}.tension`),
      celdaCalc(res && res.carga_transversal, 2, true, `l${i}.transversal`),
      el('td', { class: 't' }, el('button', {
        class: 'btn-x', type: 'button', title: 'Quitar línea',
        onclick: () => { g.lineas.splice(i, 1); renderEditor(); evaluar(); },
      }, '×'))));
  });
  if (!g.lineas.length) {
    cuerpo.append(el('tr', {}, el('td', { class: 't', colspan: '9', text: 'Sin líneas de conductor todavía.' })));
  }
  // Las filas de veredicto se pintan siempre: refrescarCalculos() rellena sus
  // celdas después, sin tener que rehacer la tabla.
  cuerpo.append(el('tr', { class: 'veredicto' },
    el('td', { class: 't', colspan: '8' }, 'Carga transversal admisible [kg]'),
    celdaCalc(r && r.transversal_admisible, 2, false, 'total.transv_adm'), el('td', {})));
  const excede = r && r.transversal_calculada > r.transversal_admisible;
  cuerpo.append(el('tr', { class: 'veredicto', 'data-veredicto': 'transversal' },
    el('td', { class: `t ${excede ? 'malo' : 'bueno'}`, colspan: '8' }, 'Carga transversal calculada [kg]'),
    celdaCalc(r && r.transversal_calculada, 2, true, 'total.transv'),
    el('td', {})));
  tabla.append(cuerpo);
  caja.append(tabla);
  caja.append(pieLineas(g));
  return caja;
}

// --- 3. cargas verticales
function bloqueVertical(g, r) {
  const caja = bloque('3. Cargas verticales');
  const tabla = el('table', {}, cabecera(
    'Set · cable', 'Cadena', 'Conductores por fase', 'Peso conductor [kg/m]',
    'Peso aislador [kg]', 'N.º de aisladores', 'Ferretería [kg]', 'Luz peso [m]',
    'Carga vertical [kg]'));
  const cuerpo = el('tbody', {});
  g.lineas.forEach((linea, i) => {
    const res = r && r.lineas[i];
    const conductor = conductorDe(linea);
    const cadena = aisladorDe(linea);
    const peso = conductor.peso_dan_m ?? conductor.cable;
    // Todo viene de los catálogos: aquí no hay nada que escribir.
    cuerpo.append(el('tr', {},
      el('td', { class: 't', text: etiquetaLinea(linea) }),
      el('td', { class: 't', text: linea.aislador || '—' }),
      celdaCalc(conductor.n_conductores, 0, false, `l${i}.ncond`),
      celdaCalc(peso === undefined ? null : peso * 1.019716, 6, false, `l${i}.peso`),
      celdaCalc(cadena.peso_kg, 2, false, `l${i}.ais_peso`),
      celdaCalc(cadena.n_aisladores, 0, false, `l${i}.ais_n`),
      celdaCalc(cadena.peso_ferreteria_kg, 2, false, `l${i}.ais_ferr`),
      celdaCalc(res && res.luz_peso, 1, false, `l${i}.luz_peso`),
      celdaCalc(res && res.carga_vertical, 2, true, `l${i}.vertical`)));
  });
  cuerpo.append(el('tr', { class: 'veredicto' },
    el('td', { class: 't', colspan: '8' }, 'Carga vertical total (× fases) [kg]'),
    celdaCalc(r && r.vertical_total, 2, true, 'total.vertical')));
  tabla.append(cuerpo);
  caja.append(tabla);
  return caja;
}

// --- 4. momentos
function bloqueMomentos(g, r) {
  const caja = bloque('4. Momentos');
  const tabla = el('table', {}, cabecera(
    'Set · cable', 'Fase', 'Altura de amarre bajo la punta [m]', 'Carga transversal [kg]'));
  const cuerpo = el('tbody', {});
  g.lineas.forEach((linea, i) => {
    const res = r && r.lineas[i];
    for (let f = 0; f < linea.fases; f += 1) {
      const input = el('input', { type: 'number', step: '0.01', value: linea.alturas_amarre[f] ?? 0 });
      input.addEventListener('input', () => {
        linea.alturas_amarre[f] = input.value === '' ? 0 : Number(input.value);
        evaluarDiferido();
      });
      cuerpo.append(el('tr', {},
        el('td', { class: 't', text: f === 0 ? etiquetaLinea(linea) : '' }),
        el('td', { class: 'uni', text: String(f + 1) }),
        el('td', { class: 'ed' }, input),
        celdaCalc(res && res.carga_transversal, 2, false, `l${i}.transversal`)));
    }
  });
  tabla.append(cuerpo);
  caja.append(tabla);

  // Las alturas únicas cambian al editarlas, así que esta tabla se rehace
  // entera; los campos editables viven en la tabla de arriba y no se tocan.
  const resumenMomentos = el('div', { id: 'momentos-resumen' });
  caja.append(resumenMomentos);
  pintarMomentos(resumenMomentos, r);

  caja.append(el('div', { id: 'avisos-hoja' }));
  pintarAvisosHoja(r);
  return caja;
}

function pintarMomentos(host, r) {
  host.replaceChildren();
  if (!r || !r.momentos.length) return;
  const mt = el('table', {}, cabecera('Altura de amarre [m]', 'Brazo [m]', 'Momento [kg·m]', ''));
  const mc = el('tbody', {});
  r.momentos.forEach((m) => mc.append(el('tr', {},
    celdaCalc(m.altura_amarre), celdaCalc(m.brazo), celdaCalc(m.momento), el('td', {}))));
  mc.append(el('tr', { class: 'veredicto' },
    el('td', { class: 't', colspan: '2' }, 'Momento admisible [kg·m]'),
    celdaCalc(r.momento_admisible, 2), el('td', {})));
  const excede = r.momento_calculado > r.momento_admisible;
  mc.append(el('tr', { class: 'veredicto' },
    el('td', { class: `t ${excede ? 'malo' : 'bueno'}`, colspan: '2' }, 'Momento calculado [kg·m]'),
    el('td', { class: `calc fuerte ${excede ? 'malo' : 'bueno'}`, text: n2(r.momento_calculado) }),
    el('td', { class: excede ? 'malo' : 'bueno' })));
  mt.append(mc);
  host.append(mt);
}

function pintarAvisosHoja(r) {
  const host = $('#avisos-hoja');
  if (!host) return;
  host.replaceChildren();
  const avisos = [...((r && r.avisos) || [])];
  if (r) r.lineas.forEach((l) => (l.avisos || []).forEach((a) => avisos.push(`Set ${l.set_no}: ${a}`)));
  [...new Set(avisos)].forEach((a) => host.append(el('div', { class: 'pista', text: a })));
}

// --- selector (set, cable) y utilidades de línea
function selectorLinea(linea) {
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
    renderEditor();
    evaluar();
  });
  return select;
}

function ajustarFases(linea) {
  const n = Math.max(1, Number(linea.fases) || 1);
  linea.fases = n;
  while (linea.alturas_amarre.length < n) {
    linea.alturas_amarre.push(linea.alturas_amarre[linea.alturas_amarre.length - 1] ?? 0);
  }
  linea.alturas_amarre.length = n;
  renderEditor();
  evaluar();
}

function lineaNueva(opcion) {
  const cadenas = S.proyecto.aisladores || [];
  return {
    set_no: opcion ? opcion.set : '', cable: opcion ? opcion.cable : 0,
    fases: 1, aislador: cadenas.length ? cadenas[0].nombre : '', alturas_amarre: [0],
  };
}

function pieLineas(g) {
  const pie = el('div', { class: 'xl-pie' });
  pie.append(el('button', {
    class: 'ghost small', type: 'button',
    onclick: () => { g.lineas.push(lineaNueva(S.opciones[0])); sincronizarCatalogo(); renderEditor(); evaluar(); },
  }, '+ Añadir línea'));
  pie.append(el('button', {
    class: 'ghost small', type: 'button',
    title: 'Una línea por cada par (set, cable) disponible en estas estructuras',
    onclick: () => {
      g.lineas = S.opciones.map(lineaNueva);
      sincronizarCatalogo(); renderEditor(); evaluar();
    },
  }, 'Añadir todas las disponibles'));
  pie.append(el('span', { class: 'muted', style: 'align-self:center;font-size:12.5px' },
    'Cada línea es un par (set, cable): así no puede mezclar dos conductores.'));
  return pie;
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
    S.poste = r.poste || null;
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
    refrescarCalculos();
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

/** Actualiza solo las celdas calculadas de la hoja activa.
 *  Reconstruir el DOM en cada tecleo le robaría el foco al campo en edición. */
function refrescarCalculos() {
  const host = $('#editor-hoja');
  const g = grupoActivo();
  const r = S.resultados[S.activa];
  if (!host || !g || !r) return;

  const valores = { 'total.transv': r.transversal_calculada,
                    'total.transv_adm': r.transversal_admisible,
                    'total.vertical': r.vertical_total };
  r.lineas.forEach((l, i) => {
    const linea = g.lineas[i] || {};
    const conductor = conductorDe(linea);
    const cadena = aisladorDe(linea);
    const peso = conductor.peso_dan_m ?? conductor.cable;
    Object.assign(valores, {
      [`l${i}.ncond`]: conductor.n_conductores,
      [`l${i}.ais_diam`]: cadena.diametro_mm,
      [`l${i}.ais_long`]: cadena.longitud_mm,
      [`l${i}.ais_peso`]: cadena.peso_kg,
      [`l${i}.ais_n`]: cadena.n_aisladores,
      [`l${i}.ais_ferr`]: cadena.peso_ferreteria_kg,
      [`l${i}.luz_viento`]: l.luz_viento,
      [`l${i}.tension`]: l.tension_kg,
      [`l${i}.transversal`]: l.carga_transversal,
      [`l${i}.luz_peso`]: l.luz_peso,
      [`l${i}.vertical`]: l.carga_vertical,
      [`l${i}.diam`]: conductor.diametro_mm,
      [`l${i}.peso`]: peso === undefined ? null : peso * 1.019716,
    });
  });
  host.querySelectorAll('[data-calc]').forEach((celda) => {
    const clave = celda.dataset.calc;
    if (clave in valores) celda.textContent = n2(valores[clave], Number(celda.dataset.dec || 2));
  });

  const excede = r.transversal_calculada > r.transversal_admisible;
  host.querySelectorAll('[data-veredicto="transversal"] td').forEach((celda) => {
    celda.classList.toggle('malo', excede);
    celda.classList.toggle('bueno', !excede);
  });

  pintarMomentos($('#momentos-resumen'), r);
  pintarAvisosHoja(r);
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
