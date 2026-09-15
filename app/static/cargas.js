'use strict';

const S = {
  jobId: null,
  estructuras: [],      // [{key, nombre, wind_span}]
  casos: [],
  proyectos: [],        // guardados en el navegador
  proyecto: null,       // el activo: {id, nombre, grupos[]}
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
    // La hoja arranca en blanco, como en el libro: las estructuras y los
    // casos climáticos se eligen a mano.
    nombre, estructuras: [], casos: [], n_postes: 1,
    fs: d.fs, nc: d.nc, espesor_hielo_mm: d.espesor_hielo_mm,
    n_cadenas: d.n_cadenas, n_aisladores: d.n_aisladores, alpha_deg: d.alpha_deg,
    ht_m: d.ht_m, t_servicio_kg: d.t_servicio_kg, pv_kg_m2: d.pv_kg_m2, lineas: [],
  };
}

// -------------------------------------------------------------- proyectos
// Los proyectos viven en el navegador, igual que los reportes subidos; el
// respaldo sirve para llevárselo todo a otro equipo.
const CLAVE_PROYECTOS = 'plscadd.cargas.proyectos';
const CONDICION = 'creep';

function leerProyectos() {
  try {
    const datos = JSON.parse(localStorage.getItem(CLAVE_PROYECTOS) || '{}');
    return Array.isArray(datos.lista) ? datos : { activo: null, lista: [] };
  } catch {
    return { activo: null, lista: [] };
  }
}

function guardarProyectos() {
  try {
    localStorage.setItem(CLAVE_PROYECTOS,
      JSON.stringify({ activo: S.proyecto ? S.proyecto.id : null, lista: S.proyectos }));
  } catch { /* sin localStorage */ }
}

function proyectoNuevo(nombre, grupos = null) {
  return {
    id: `p${Date.now()}${Math.floor(Math.random() * 1000)}`,
    nombre, condicion: CONDICION, grupos: grupos || [grupoNuevo('Hoja 1')],
  };
}

function abrirProyecto(id) {
  const encontrado = S.proyectos.find((p) => p.id === id);
  if (!encontrado) return;
  S.proyecto = encontrado;
  S.proyecto.condicion = CONDICION;
  if (!S.proyecto.grupos.length) S.proyecto.grupos.push(grupoNuevo('Hoja 1'));
  S.activa = 0;
  guardarProyectos();
  renderProyectos();
  renderTabs();
  refrescarOpciones();
}

function renderProyectos() {
  const select = $('#proyecto-select');
  select.replaceChildren(...S.proyectos.map((p) => {
    const opcion = el('option', { value: p.id }, p.nombre);
    if (S.proyecto && p.id === S.proyecto.id) opcion.selected = true;
    return opcion;
  }));
  $('#btn-proy-borrar').disabled = S.proyectos.length <= 1;
}

$('#proyecto-select').addEventListener('change', (e) => abrirProyecto(e.target.value));

$('#btn-proy-nuevo').addEventListener('click', () => {
  const nombre = (prompt('Nombre del proyecto nuevo:', `Proyecto ${S.proyectos.length + 1}`) || '').trim();
  if (!nombre) return;
  const proyecto = proyectoNuevo(nombre);
  S.proyectos.push(proyecto);
  abrirProyecto(proyecto.id);
});

$('#btn-proy-renombrar').addEventListener('click', () => {
  if (!S.proyecto) return;
  const nombre = (prompt('Nuevo nombre:', S.proyecto.nombre) || '').trim();
  if (!nombre) return;
  S.proyecto.nombre = nombre;
  guardarProyectos();
  renderProyectos();
});

$('#btn-proy-borrar').addEventListener('click', () => {
  if (!S.proyecto || S.proyectos.length <= 1) return;
  if (!confirm(`¿Eliminar el proyecto «${S.proyecto.nombre}» y todas sus hojas?`)) return;
  S.proyectos = S.proyectos.filter((p) => p.id !== S.proyecto.id);
  abrirProyecto(S.proyectos[0].id);
});

// ------------------------------------------------------------------ carga
// Los reportes quedan guardados en este navegador: al recargar la página se
// vuelven a enviar solos, sin tener que elegirlos otra vez.
const CLAVE_ARCHIVOS = 'cargas.reportes';

function pintarElegidos(input) {
  const destino = input.parentElement.querySelector('.picked');
  const nombres = Array.from(input.files || []).map((f) => f.name);
  destino.textContent = nombres.length ? `✓ ${nombres.join(', ')}` : '';
  input.parentElement.classList.toggle('filled', nombres.length > 0);
}
['#file-reportes', '#file-respaldo'].forEach((sel) =>
  $(sel).addEventListener('change', () => pintarElegidos($(sel))));

async function analizar(reportes, respaldo = []) {
  const datos = new FormData();
  [...reportes, ...respaldo].forEach((f) => datos.append('archivos', f));
  return api('/api/mec/upload', { body: datos });
}

/** Deja la página lista con lo que devolvió /upload. */
function aplicarCarga(r, { preguntarNombre = true } = {}) {
  S.jobId = r.job_id;
  S.estructuras = r.estructuras;
  S.casos = r.casos;
  const guardados = leerProyectos();
  S.proyectos = guardados.lista;
  if (r.proyecto) {
    // Un respaldo entra como proyecto nuevo, para no pisar lo que ya había.
    const importado = proyectoNuevo(r.proyecto.nombre || 'Respaldo', r.proyecto.grupos);
    S.proyectos.push(importado);
    guardados.activo = importado.id;
  }
  if (!S.proyectos.length) {
    const nombre = preguntarNombre
      ? (prompt('Nombre del proyecto:', 'Proyecto 1') || 'Proyecto 1').trim()
      : 'Proyecto 1';
    S.proyectos.push(proyectoNuevo(nombre));
  }
  S.proyecto = S.proyectos.find((p) => p.id === guardados.activo) || S.proyectos[0];
  S.proyecto.condicion = CONDICION;
  if (!S.proyecto.grupos.length) S.proyecto.grupos.push(grupoNuevo('Hoja 1'));
  S.activa = 0;
  guardarProyectos();
  $('#paso-hojas').hidden = false;
}

function resumenCarga(extra = '') {
  $('#estado-carga').textContent =
    `${S.estructuras.length} estructuras · ${S.casos.length} casos climáticos${extra}`;
}

function pintarGuardados(nombres) {
  const host = $('#archivos-guardados');
  if (!nombres.length) {
    host.replaceChildren();
    $('#btn-olvidar').hidden = true;
    return;
  }
  host.replaceChildren(
    el('span', { class: 'ok' }, '✓ '),
    `Reportes guardados en este navegador: ${nombres.join(', ')}. Se cargan solos al abrir la página.`,
  );
  $('#btn-olvidar').hidden = false;
}

$('#btn-cargar').addEventListener('click', async () => {
  const boton = $('#btn-cargar');
  clearError();
  const reportes = Array.from($('#file-reportes').files || []);
  const respaldo = Array.from($('#file-respaldo').files || []);
  if (!reportes.length) { fail('Selecciona los reportes de PLS-CADD.'); return; }

  busy(boton, true, 'Analizando…');
  try {
    const r = await analizar(reportes, respaldo);
    aplicarCarga(r);
    // Sólo se guardan los reportes: el respaldo ya quedó dentro del proyecto.
    const guardado = await guardarArchivos(CLAVE_ARCHIVOS, reportes);
    pintarGuardados(guardado ? reportes.map((f) => f.name) : []);
    resumenCarga(r.proyecto ? ` · respaldo con ${r.proyecto.grupos.length} hoja(s)` : '');
    if (r.avisos && r.avisos.length) {
      $('#global-error').replaceChildren(notice('warn', 'Avisos al leer los reportes:', r.avisos));
    }
    render();
  } catch (e) {
    fail(e.message);
  } finally {
    busy(boton, false);
  }
});

$('#btn-olvidar').addEventListener('click', async () => {
  if (!confirm('¿Olvidar los reportes guardados en este navegador? Los proyectos y sus hojas se conservan.')) return;
  await olvidarArchivos(CLAVE_ARCHIVOS);
  pintarGuardados([]);
});

/** Vuelve a subir los reportes guardados: al recargar y cuando el servidor
 *  olvida la sesión de trabajo (se reinició o venció el plazo). */
async function reanudar() {
  const archivos = await leerArchivos(CLAVE_ARCHIVOS);
  if (!archivos.length) return null;
  const r = await analizar(archivos);
  S.jobId = r.job_id;
  S.estructuras = r.estructuras;
  S.casos = r.casos;
  pintarGuardados(archivos.map((f) => f.name));
  return r;
}

/** Como api(), pero si la sesión de trabajo venció la rehace y reintenta. */
async function apiMec(ruta, opciones) {
  try {
    return await api(ruta, opciones);
  } catch (e) {
    if (e.status !== 404 || !S.jobId) throw e;
    if (!(await reanudar())) throw e;
    return api(ruta, { ...opciones, body: { ...opciones.body, job_id: S.jobId } });
  }
}

// Al abrir la página se recupera lo último que se subió desde este navegador.
(async function arranque() {
  const nombres = (await leerArchivos(CLAVE_ARCHIVOS)).map((f) => f.name);
  if (!nombres.length) return;
  pintarGuardados(nombres);
  $('#estado-carga').textContent = 'Recuperando los reportes guardados…';
  try {
    const r = await reanudar();
    if (!r) return;
    aplicarCarga(r, { preguntarNombre: false });
    resumenCarga();
    render();
  } catch (e) {
    $('#estado-carga').textContent = '';
    fail(`No pude recuperar los reportes guardados: ${e.message}`);
  }
}());

// ------------------------------------------------------- proyecto y cables
function render() {
  renderProyectos();
  renderTabs();
  refrescarOpciones();   // trae las opciones de la hoja activa y luego pinta
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

// ----------------------------------------------- réplica de la hoja de Excel
// Anchos de las columnas A..M, tomados del libro original.
const ANCHOS = [65, 250, 145, 48, 140, 135, 135, 130, 18, 140, 148, 132, 50];
const COLS = ANCHOS.length;

function cel(contenido, opciones = {}) {
  const atributos = { class: opciones.clase || '' };
  if (opciones.colspan) atributos.colspan = String(opciones.colspan);
  if (opciones.rowspan) atributos.rowspan = String(opciones.rowspan);
  if (opciones.calc) { atributos['data-calc'] = opciones.calc; atributos['data-dec'] = String(opciones.dec ?? 2); }
  const td = el('td', atributos);
  if (contenido !== null && contenido !== undefined) {
    if (contenido.nodeType) td.append(contenido);
    else td.textContent = String(contenido);
  }
  return td;
}

/** Celda amarilla: las que se rellenan a mano, como en el libro. */
function celAm(input) { return cel(input, { clase: 'am' }); }

function celNum(valor, dec = 2, clave = null, clase = '') {
  return cel(n2(valor, dec), { clase: `num ${clase}`.trim(), calc: clave, dec });
}

function entrada(objeto, clave, paso, alCambiar = evaluarDiferido, opciones = {}) {
  const input = el('input', {
    type: opciones.texto ? 'text' : 'number',
    ...(opciones.texto ? {} : { step: String(paso) }),
    value: objeto[clave] ?? (opciones.texto ? '' : 0),
  });
  input.addEventListener('input', () => {
    objeto[clave] = opciones.texto ? input.value : (input.value === '' ? 0 : Number(input.value));
    alCambiar();
  });
  return input;
}

function banda(texto) {
  return el('tr', { class: 'banda' }, cel(texto, { colspan: COLS }));
}

function vacia() {
  return el('tr', { class: 'hueca' }, cel('', { colspan: COLS }));
}

function rellenar(fila, desde) {
  for (let i = desde; i < COLS; i += 1) fila.append(cel(''));
  return cerrar(fila);
}

/** Marca cada celda con su letra de columna (A..M), como en el libro. */
function cerrar(fila) {
  let columna = 0;
  [...fila.children].forEach((td) => {
    td.dataset.col = String.fromCharCode(65 + columna);
    columna += Number(td.getAttribute('colspan') || 1);
  });
  return fila;
}

// --------------------------------------------------------------- editor
function renderEditor() {
  const host = $('#editor-hoja');
  host.replaceChildren();
  const g = grupoActivo();
  if (!g) return;
  const r = S.resultados[S.activa];

  const cuerpo = el('tbody', {});
  filasCabecera(cuerpo, g);
  filasParametros(cuerpo, g);
  cuerpo.append(vacia());
  filasTransversal(cuerpo, g, r);
  cuerpo.append(vacia());
  filasVertical(cuerpo, g, r);
  cuerpo.append(vacia());
  filasMomentos(cuerpo, g, r);

  const grupo = el('colgroup', {}, ...ANCHOS.map((w) => el('col', { style: `width:${w}px` })));
  host.append(el('div', { class: 'hoja-scroll' },
    el('table', { class: 'hoja' }, grupo, cuerpo)));
  host.append(pieHoja(g));
}

function filasCabecera(cuerpo, g) {
  const nombre = entrada(g, 'nombre', null, () => { renderTabs(); evaluarDiferido(); }, { texto: true });
  nombre.classList.add('titulo');
  cuerpo.append(cerrar(el('tr', { class: 'titulo' }, cel(nombre, { colspan: COLS, clase: 'am' }))));
}

function filasParametros(cuerpo, g) {
  cuerpo.append(banda('1. Parámetros generales'));
  const enterramiento = (g.ht_m || 0) / 6;
  const params = [
    ['FS', 'Factor de succión.', 'fs', '-', 0.01],
    ['Nc', 'Número de conductores por fase, [un].', 'nc', 'un', 1],
    ['e', 'Espesor de hielo, [mm].', 'espesor_hielo_mm', 'mm', 0.1],
    ['Ncad', 'Número de cadenas de aisladores, [un].', 'n_cadenas', 'un', 1],
    ['Naisl', 'Número de aisladores, [un].', 'n_aisladores', 'un', 1],
    ['α', 'Ángulo de deflexión de la línea, [°].', 'alpha_deg', '°', 0.01],
    ['Ht', 'Altura total del poste.', 'ht_m', 'm', 0.1],
    ['Tservicio', 'Carga de servicio en la punta del poste.', 't_servicio_kg', 'kg', 1],
    ['', 'Enterramiento', null, 'm', null, enterramiento],
    ['', 'Altura efectiva', null, 'm', null, (g.ht_m || 0) - enterramiento],
    ['Pv', 'Presión de viento máximo, [kg/m²].', 'pv_kg_m2', 'kg/m²', 1],
  ];

  const filas = Math.max(params.length, g.lineas.length + 1, g.estructuras.length + 1, g.casos.length + 1);
  for (let i = 0; i < filas; i += 1) {
    const fila = el('tr', {});
    const p = params[i];
    if (p) {
      const [simbolo, descripcion, clave, unidad, paso, calculado] = p;
      fila.append(cel(simbolo, { clase: 'sim' }), cel(descripcion, { clase: 'txt' }));
      fila.append(clave ? celAm(entrada(g, clave, paso, () => { renderEditor(); evaluar(); }))
                        : celNum(calculado, 2));
      fila.append(cel(unidad, { clase: 'uni' }));
    } else {
      fila.append(cel(''), cel(''), cel(''), cel(''));
    }
    fila.append(cel(''));  // E, separador como en el libro

    if (i === 0) {
      fila.append(cel("Set's", { clase: 'am cab' }), cel('N° Fase x set', { clase: 'am cab' }),
        cel('Nombre', { clase: 'am cab' }), cel(''),
        cel('Estructura(s) a evaluar', { clase: 'am cab' }), cel('N° postes', { clase: 'cab' }),
        cel('Casos climáticos a evaluar', { clase: 'am cab' }), cel(''));
    } else {
      const j = i - 1;
      const linea = g.lineas[j];
      fila.append(
        celAm(linea ? selectorLinea(linea) : selectorLineaVacia(g)),
        linea ? celAm(entrada(linea, 'fases', 1, () => ajustarFases(linea))) : cel(''),
        linea ? celAm(entrada(linea, 'nombre', null, evaluarDiferido, { texto: true })) : cel(''),
        cel(''),
        celAm(selectorEstructura(g, j)),
        i === 1 ? celAm(entrada(g, 'n_postes', 1)) : cel(''),
        celAm(selectorCaso(g, j)),
        cel(''));
    }
    cuerpo.append(cerrar(fila));
  }
}

function filasTransversal(cuerpo, g, r) {
  cuerpo.append(banda('2. Cargas transversales y longitudinales'));
  const cab = el('tr', { class: 'cab' },
    cel('Set', { clase: 'cab' }),
    cel('Diámetro del conductor, [mm].', { clase: 'cab am' }),
    cel('Diámetro del aislador, [mm].', { clase: 'cab am' }),
    cel('Longitud del aislador, [mm].', { clase: 'cab am' }),
    cel('Luz viento, [m].', { clase: 'cab' }),
    cel('Tensión longitudinal por cada conductor del set, [kg].', { clase: 'cab' }),
    cel('Carga transversal por cada conductor del set, [kg].', { clase: 'cab' }),
    cel(''), cel(''),
    cel('Carga transversal admisible', { clase: 'cab' }),
    cel(n2(r && r.transversal_admisible), { clase: 'num rojo', calc: 'total.transv_adm', dec: 2 }));
  cuerpo.append(rellenar(cab, 11));

  g.lineas.forEach((linea, i) => {
    const res = r && r.lineas[i];
    const fila = el('tr', { 'data-bloque': '2' },
      cel(linea.set_no, { clase: 'sim' }),
      celAm(entrada(linea, 'diametro_conductor_mm', 0.0001)),
      celAm(entrada(linea, 'diam_aislador_mm', 0.1)),
      celAm(entrada(linea, 'long_aislador_mm', 1)),
      celNum(res && res.luz_viento, 1, `l${i}.luz_viento`, 'rojo'),
      celNum(res && res.tension_kg, 2, `l${i}.tension`, 'rojo'),
      celNum(res && res.carga_transversal, 2, `l${i}.transversal`, 'rojo'),
      cel(''), cel(''));
    if (i === 0) {
      const excede = r && r.transversal_calculada > r.transversal_admisible;
      fila.append(cel('Carga transversal calculada', { clase: `cab ${excede ? 'malo' : 'bueno'}` }));
      fila.append(cel(n2(r && r.transversal_calculada),
        { clase: `num rojo ${excede ? 'malo' : 'bueno'}`, calc: 'total.transv', dec: 2 }));
    } else {
      fila.append(cel(''), cel(''));
    }
    cuerpo.append(rellenar(fila, 11));
  });
  if (!g.lineas.length) {
    cuerpo.append(rellenar(el('tr', {}, cel('Sin sets elegidos todavía.', { clase: 'txt', colspan: 7 })), 7));
  }
}

function filasVertical(cuerpo, g, r) {
  cuerpo.append(banda('3. Cargas verticales'));
  const cab = el('tr', { class: 'cab' },
    cel('Set', { clase: 'cab' }),
    cel('Número de conductores por fase, [un].', { clase: 'cab am' }),
    cel('Peso del conductor, [kg/m].', { clase: 'cab am' }),
    cel('Peso del aislador, [kg].', { clase: 'cab am' }),
    cel('Número de aisladores, [un].', { clase: 'cab am' }),
    cel('Peso de la ferretería y accesorios, [kg]', { clase: 'cab am' }),
    cel('Luz peso, [m].', { clase: 'cab' }),
    cel('Carga vertical por cada conductor del set [kg]', { clase: 'cab' }));
  cuerpo.append(rellenar(cab, 8));

  g.lineas.forEach((linea, i) => {
    const res = r && r.lineas[i];
    cuerpo.append(rellenar(el('tr', { 'data-bloque': '3' },
      cel(linea.set_no, { clase: 'sim' }),
      celAm(entrada(linea, 'n_conductores', 1)),
      celAm(entrada(linea, 'peso_conductor_kg_m', 0.000001)),
      celAm(entrada(linea, 'peso_aislador_kg', 0.1)),
      celAm(entrada(linea, 'n_aisladores', 1)),
      celAm(entrada(linea, 'peso_ferreteria_kg', 0.1)),
      celNum(res && res.luz_peso, 1, `l${i}.luz_peso`, 'rojo'),
      celNum(res && res.carga_vertical, 2, `l${i}.vertical`, 'rojo')), 8));
  });
}

function filasMomentos(cuerpo, g, r) {
  cuerpo.append(banda('4. Momentos'));
  const cab = el('tr', { class: 'cab' },
    cel('Set', { clase: 'cab' }), cel('Fase', { clase: 'cab' }),
    cel('Attach. Dist. Below Top (m)', { clase: 'am cab' }),
    cel('Carga transversal, [kg].', { clase: 'cab' }),
    cel(''),
    cel('Attach. Dist. Below Top (m), unique', { clase: 'cab' }),
    cel('Momento calculado por altura vertical kg*m', { clase: 'cab' }),
    cel(''), cel(''),
    cel('Momento admisible kg*m', { clase: 'cab' }),
    cel(n2(r && r.momento_admisible), { clase: 'num rojo', calc: 'total.momento_adm', dec: 2 }));
  cuerpo.append(rellenar(cab, 11));

  const fases = [];
  g.lineas.forEach((linea, i) => {
    for (let f = 0; f < linea.fases; f += 1) fases.push({ linea, i, fase: f });
  });
  const momentos = (r && r.momentos) || [];
  const filas = Math.max(fases.length, momentos.length, 1);

  for (let k = 0; k < filas; k += 1) {
    const fila = el('tr', { 'data-bloque': '4' });
    const item = fases[k];
    if (item) {
      const input = el('input', { type: 'number', step: '0.01', value: item.linea.alturas_amarre[item.fase] ?? 0 });
      input.addEventListener('input', () => {
        item.linea.alturas_amarre[item.fase] = input.value === '' ? 0 : Number(input.value);
        evaluarDiferido();
      });
      const res = r && r.lineas[item.i];
      fila.append(cel(item.linea.set_no, { clase: 'sim' }), cel(item.fase + 1, { clase: 'uni' }),
        celAm(input), celNum(res && res.carga_transversal, 2, `l${item.i}.transversal`, 'rojo'));
    } else {
      fila.append(cel(''), cel(''), cel(''), cel(''));
    }
    fila.append(cel(''));
    const m = momentos[k];
    fila.append(celNum(m && m.altura_amarre, 2, `mom${k}.altura`, 'rojo'),
                celNum(m && m.momento, 4, `mom${k}.momento`, 'rojo'));
    fila.append(cel(''), cel(''));
    if (k === 0) {
      const excede = r && r.momento_calculado > r.momento_admisible;
      fila.append(cel('Momento calculado kg*m', { clase: `cab ${excede ? 'malo' : 'bueno'}` }));
      fila.append(cel(n2(r && r.momento_calculado),
        { clase: `num rojo ${excede ? 'malo' : 'bueno'}`, calc: 'total.momento', dec: 2 }));
    } else {
      fila.append(cel(''), cel(''));
    }
    cuerpo.append(rellenar(fila, 11));
  }
}

function pieHoja(g) {
  const pie = el('div', { class: 'xl-pie' });
  pie.append(el('button', {
    class: 'ghost small', type: 'button',
    onclick: () => {
      g.lineas = S.opciones.map(lineaNueva);
      renderEditor(); evaluar();
    },
  }, 'Añadir todos los sets disponibles'));
  pie.append(el('button', {
    class: 'ghost small', type: 'button', title: 'Se aplicarán a las hojas nuevas',
    onclick: () => { guardarDefaults(g); pie.append(el('span', { class: 'badge ok', text: 'guardados' })); },
  }, 'Guardar parámetros por defecto'));
  return pie;
}

// ------------------------------------------------------------ selectores
function claveOpcion(s, c) { return `${s}|${Number(c).toFixed(6)}`; }

/** Etiqueta del set: el número y, entre paréntesis, el cable que lleva. */
function etiquetaOpcion(o) { return `${o.set} (${Number(o.cable)} daN/m)`; }

function opcionesSet(seleccionada) {
  return S.opciones.map((o) => {
    const v = claveOpcion(o.set, o.cable);
    const opcion = el('option', { value: v, title: `${o.amarres} amarre(s), máx ${n2(o.tension_max, 1)} kg` },
      etiquetaOpcion(o));
    if (v === seleccionada) opcion.selected = true;
    return opcion;
  });
}

/** Al elegir un set se adelanta el peso del conductor que da el reporte.
 *  Queda editable: el reporte redondea la carga vertical a dos decimales. */
function aplicarSet(linea, valor) {
  const [s, c] = valor.split('|');
  linea.set_no = s;
  linea.cable = Number(c);
  if (!linea.peso_conductor_kg_m) linea.peso_conductor_kg_m = Number((linea.cable * 1.019716).toFixed(6));
}

function selectorLinea(linea) {
  const select = el('select', {});
  const actual = claveOpcion(linea.set_no, linea.cable);
  const opciones = opcionesSet(actual);
  select.append(...opciones);
  if (!opciones.some((o) => o.selected)) {
    const perdida = el('option', { value: actual },
      `${linea.set_no} (${Number(linea.cable)} daN/m) — no está aquí`);
    perdida.selected = true;
    select.prepend(perdida);
  }
  select.append(el('option', { value: '' }, '— quitar —'));
  select.addEventListener('change', () => {
    const g = grupoActivo();
    if (select.value === '') g.lineas.splice(g.lineas.indexOf(linea), 1);
    else aplicarSet(linea, select.value);
    renderEditor();
    evaluar();
  });
  return select;
}

/** Fila en blanco al final: elegir un set añade una línea nueva. */
function selectorLineaVacia(g) {
  const select = el('select', {});
  select.append(el('option', { value: '' }, '—'));
  select.append(...opcionesSet(null));
  select.addEventListener('change', () => {
    if (!select.value) return;
    const linea = { set_no: '', cable: 0, nombre: '', fases: 1,
      diametro_conductor_mm: 0, diam_aislador_mm: 0, long_aislador_mm: 0,
      n_conductores: 1, peso_conductor_kg_m: 0, peso_aislador_kg: 0,
      n_aisladores: 0, peso_ferreteria_kg: 0, alturas_amarre: [0] };
    aplicarSet(linea, select.value);
    g.lineas.push(linea);
    renderEditor();
    evaluar();
  });
  return select;
}

function selectorEstructura(g, indice) {
  const select = el('select', {});
  select.append(el('option', { value: '' }, '—'));
  S.estructuras.forEach((e) => {
    const usada = g.estructuras.includes(e.key) && g.estructuras[indice] !== e.key;
    const opcion = el('option', { value: e.key, ...(usada ? { disabled: 'disabled' } : {}) }, e.key);
    if (g.estructuras[indice] === e.key) opcion.selected = true;
    select.append(opcion);
  });
  select.addEventListener('change', () => {
    if (select.value === '') g.estructuras.splice(indice, 1);
    else if (indice < g.estructuras.length) g.estructuras[indice] = select.value;
    else g.estructuras.push(select.value);
    renderEditor(); refrescarOpciones();
  });
  return select;
}

function selectorCaso(g, indice) {
  const select = el('select', {});
  select.append(el('option', { value: '' }, '—'));
  S.casos.forEach((caso) => {
    const usado = g.casos.includes(caso) && g.casos[indice] !== caso;
    const opcion = el('option', { value: caso, ...(usado ? { disabled: 'disabled' } : {}) }, caso);
    if (g.casos[indice] === caso) opcion.selected = true;
    select.append(opcion);
  });
  select.addEventListener('change', () => {
    if (select.value === '') g.casos.splice(indice, 1);
    else if (indice < g.casos.length) g.casos[indice] = select.value;
    else g.casos.push(select.value);
    renderEditor(); refrescarOpciones();
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

/** Una línea está vacía si no se ha escrito nada en ella. El peso del
 *  conductor no cuenta si sigue siendo el que se adelantó del reporte. */
function lineaVacia(linea) {
  const numeros = ['diametro_conductor_mm', 'diam_aislador_mm', 'long_aislador_mm',
    'peso_aislador_kg', 'n_aisladores', 'peso_ferreteria_kg'];
  const adelantado = Number((linea.cable * 1.019716).toFixed(6));
  const pesoIntacto = !linea.peso_conductor_kg_m
    || Math.abs(linea.peso_conductor_kg_m - adelantado) < 1e-9;
  return !linea.nombre
    && pesoIntacto
    && numeros.every((k) => !linea[k])
    && (linea.alturas_amarre || []).every((a) => !a);
}

/** Pone una fila por cada par (set, cable) que exista en las estructuras y los
 *  casos elegidos. Lo que ya se escribió no se toca: solo se retiran las filas
 *  que se habían puesto solas, siguen vacías y ya no existen. */
function preseleccionarSets() {
  const g = grupoActivo();
  if (!g) return;
  const disponibles = new Set(S.opciones.map((o) => claveOpcion(o.set, o.cable)));
  g.lineas = g.lineas.filter(
    (l) => disponibles.has(claveOpcion(l.set_no, l.cable)) || !lineaVacia(l));

  const presentes = new Set(g.lineas.map((l) => claveOpcion(l.set_no, l.cable)));
  S.opciones.forEach((o) => {
    const clave = claveOpcion(o.set, o.cable);
    if (!presentes.has(clave)) {
      presentes.add(clave);
      g.lineas.push(lineaNueva(o));
    }
  });
  // En el mismo orden que el reporte: por número de set y luego por cable.
  g.lineas.sort((a, b) => (Number(a.set_no) - Number(b.set_no)) || (a.cable - b.cable));
}

function lineaNueva(opcion) {
  const linea = { set_no: '', cable: 0, nombre: '', fases: 1,
    diametro_conductor_mm: 0, diam_aislador_mm: 0, long_aislador_mm: 0,
    n_conductores: 1, peso_conductor_kg_m: 0, peso_aislador_kg: 0,
    n_aisladores: 0, peso_ferreteria_kg: 0, alturas_amarre: [0] };
  if (opcion) aplicarSet(linea, claveOpcion(opcion.set, opcion.cable));
  return linea;
}

// ------------------------------------------------------------- opciones
async function refrescarOpciones() {
  const g = grupoActivo();
  if (!g || !S.jobId) return;
  try {
    const r = await apiMec('/api/mec/opciones', {
      body: { job_id: S.jobId, estructuras: g.estructuras, casos: g.casos },
    });
    S.opciones = r.opciones;
    S.poste = r.poste || null;
    preseleccionarSets();
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
    const r = await apiMec('/api/mec/evaluar', { body: { job_id: S.jobId, proyecto: S.proyecto } });
    S.resultados = r.resultados;
    refrescarCalculos();
    guardarProyectos();
    $('#estado-calculo').textContent = '';
  } catch (e) {
    $('#estado-calculo').textContent = '';
    fail(e.message);
  }
}

/** Actualiza solo las celdas calculadas de la hoja activa.
 *  Reconstruir el DOM en cada tecleo le robaría el foco al campo en edición.
 *  Las filas nunca cambian de número: hay una por fase, y las alturas únicas
 *  nunca son más que las fases. */
function refrescarCalculos() {
  const host = $('#editor-hoja');
  const g = grupoActivo();
  const r = S.resultados[S.activa];
  if (!host || !g || !r) return;

  const valores = {
    'total.transv': r.transversal_calculada,
    'total.transv_adm': r.transversal_admisible,
    'total.momento': r.momento_calculado,
    'total.momento_adm': r.momento_admisible,
  };
  r.lineas.forEach((l, i) => {
    Object.assign(valores, {
      [`l${i}.luz_viento`]: l.luz_viento,
      [`l${i}.tension`]: l.tension_kg,
      [`l${i}.transversal`]: l.carga_transversal,
      [`l${i}.luz_peso`]: l.luz_peso,
      [`l${i}.vertical`]: l.carga_vertical,
    });
  });
  host.querySelectorAll('[data-calc^="mom"]').forEach((celda) => { celda.textContent = ''; });
  r.momentos.forEach((m, k) => {
    valores[`mom${k}.altura`] = m.altura_amarre;
    valores[`mom${k}.momento`] = m.momento;
  });

  host.querySelectorAll('[data-calc]').forEach((celda) => {
    const clave = celda.dataset.calc;
    if (clave in valores) celda.textContent = n2(valores[clave], Number(celda.dataset.dec || 2));
  });

  marcarVeredicto(host, 'total.transv', r.transversal_calculada > r.transversal_admisible);
  marcarVeredicto(host, 'total.momento', r.momento_calculado > r.momento_admisible);

  const avisos = [...(r.avisos || [])];
  r.lineas.forEach((l) => (l.avisos || []).forEach((a) => avisos.push(`Set ${l.set_no}: ${a}`)));
  const pie = host.querySelector('.xl-pie');
  if (pie) {
    pie.querySelectorAll('.pista-aviso').forEach((n) => n.remove());
    [...new Set(avisos)].forEach((a) => pie.append(el('span', { class: 'pista-linea pista-aviso', text: a })));
  }
}

function marcarVeredicto(host, clave, excede) {
  const celda = host.querySelector(`[data-calc="${clave}"]`);
  if (!celda) return;
  const etiqueta = celda.previousElementSibling;
  [celda, etiqueta].forEach((n) => {
    if (!n) return;
    n.classList.toggle('malo', excede);
    n.classList.toggle('bueno', !excede);
  });
}

// ------------------------------------------------------------- respaldo
$('#btn-respaldo').addEventListener('click', async () => {
  const boton = $('#btn-respaldo');
  busy(boton, true, 'Generando…');
  try {
    const respuesta = await apiMec('/api/mec/respaldo', {
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
