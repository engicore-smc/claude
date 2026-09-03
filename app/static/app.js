'use strict';

const state = {
  jobId: null,
  reports: null,
  options: null,
  kinds: {},          // clave de estructura -> 'anclaje' | 'suspension'
  temps: [],          // temperaturas disponibles
  selectedTemps: [],
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

function show(id, visible = true) { $(id).hidden = !visible; }

function notice(kind, message, items = []) {
  const box = el('div', { class: `notice ${kind}` }, message);
  if (items.length) {
    box.append(el('ul', {}, ...items.map((t) => el('li', { text: t }))));
  }
  return box;
}

function fail(message) {
  const host = $('#global-error');
  host.replaceChildren(notice('err', message));
  host.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function clearError() { $('#global-error').replaceChildren(); }

function num(value, decimals = 2) {
  return value === null || value === undefined ? '—' : Number(value).toFixed(decimals);
}

async function api(path, { method = 'POST', body, raw = false } = {}) {
  const init = { method, headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }

  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = `Error ${response.status}`;
    if (response.status === 401) detail = 'La sesión expiró. Recarga la página e inicia sesión de nuevo.';
    else {
      try { detail = (await response.json()).detail || detail; } catch { /* respuesta sin JSON */ }
    }
    throw new Error(detail);
  }
  return raw ? response : response.json();
}

function busy(button, on, label) {
  button.disabled = on;
  if (on) {
    button.dataset.label = button.textContent;
    button.replaceChildren(el('span', { class: 'spinner' }), label || 'Procesando…');
  } else if (button.dataset.label) {
    button.textContent = button.dataset.label;
  }
}

// ------------------------------------------------------------------ paso 1
function wireDropzones() {
  $$('.drop').forEach((drop) => {
    const input = drop.querySelector('input[type=file]');
    const picked = drop.querySelector('.picked');
    const refresh = () => {
      const file = input.files && input.files[0];
      drop.classList.toggle('filled', Boolean(file));
      picked.textContent = file ? `✓ ${file.name}` : '';
    };
    input.addEventListener('change', refresh);
    ['dragenter', 'dragover'].forEach((evt) =>
      drop.addEventListener(evt, (e) => { e.preventDefault(); drop.classList.add('dragover'); }));
    ['dragleave', 'drop'].forEach((evt) =>
      drop.addEventListener(evt, (e) => { e.preventDefault(); drop.classList.remove('dragover'); }));
    drop.addEventListener('drop', (e) => {
      if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; refresh(); }
    });
  });
}

$('#upload-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  clearError();
  const button = $('#btn-upload');
  busy(button, true, 'Analizando…');
  $('#upload-status').textContent = '';
  try {
    const payload = await api('/api/upload', { body: new FormData(event.target) });
    applyJobPayload(payload);
    const rows = Object.values(payload.reports).reduce((total, r) => total + r.rows, 0);
    $('#upload-status').textContent = `${rows.toLocaleString('es')} filas leídas.`;
  } catch (error) {
    fail(error.message);
  } finally {
    busy(button, false);
  }
});

// ------------------------------------------------------------------ paso 2
function applyJobPayload(payload) {
  state.jobId = payload.job_id;
  state.reports = payload.reports;
  state.options = payload.options;
  renderMapping();
  show('#step-mapping');

  if (!payload.ready) {
    fail(payload.error || 'No se pudieron interpretar los reportes.');
    $('#mapping-details').open = true;
    ['#step-filters', '#step-structures', '#step-preview', '#step-generate'].forEach((id) => show(id, false));
    return;
  }
  clearError();
  state.kinds = {};
  payload.options.structures.forEach((s) => { state.kinds[s.key] = s.kind; });
  renderFilters();
  renderStructures();
  show('#step-filters');
  show('#step-structures');
  show('#step-preview');
  show('#step-generate');
  refreshTemperatures().then(refreshPreview);
}

function renderMapping() {
  const host = $('#mapping-groups');
  host.replaceChildren();
  let missingTotal = 0;

  for (const [key, report] of Object.entries(state.reports)) {
    missingTotal += report.missing.length;
    const group = el('div', { class: 'map-group' },
      el('h4', { text: report.label }),
      el('div', { class: 'file', text: `${report.filename} · hoja "${report.sheet}" · ${report.rows} filas` }));
    const grid = el('div', { class: 'grid cols-3' });

    for (const field of report.fields) {
      const select = el('select', { 'data-report': key, 'data-field': field.key });
      select.append(el('option', { value: '' }, field.required ? '— sin asignar —' : '— no usar —'));
      for (const column of report.columns) {
        const option = el('option', { value: column }, column);
        if (report.mapping[field.key] === column) option.selected = true;
        select.append(option);
      }
      const label = el('label', { class: 'field' }, field.label,
        field.required ? null : el('span', { class: 'muted', text: ' (opcional)' }));
      grid.append(el('div', {}, label, select));
    }
    group.append(grid);
    host.append(group);
  }

  $('#mapping-state').replaceChildren(missingTotal
    ? el('span', { class: 'badge err', text: `${missingTotal} columna(s) sin asignar` })
    : el('span', { class: 'badge ok', text: 'Todo detectado' }));
}

$('#btn-remap').addEventListener('click', async () => {
  const mappings = {};
  $$('#mapping-groups select').forEach((select) => {
    const report = select.dataset.report;
    mappings[report] = mappings[report] || {};
    mappings[report][select.dataset.field] = select.value || null;
  });
  const button = $('#btn-remap');
  busy(button, true, 'Aplicando…');
  try {
    applyJobPayload(await api('/api/mapping', { body: { job_id: state.jobId, mappings } }));
  } catch (error) {
    fail(error.message);
  } finally {
    busy(button, false);
  }
});

// ------------------------------------------------------------------ paso 3
function renderFilters() {
  const cables = state.options.cables;
  const select = $('#cable-select');
  select.replaceChildren();
  if (!cables.length) {
    select.append(el('option', { value: '' }, 'Sin conductores detectados'));
  }
  cables.forEach((cable) => {
    select.append(el('option', { value: String(cable.value) }, `${cable.label} — ${cable.spans} vano(s)`));
  });

  const conditions = state.options.conditions || [];
  const condition = $('#condition-select');
  condition.replaceChildren(el('option', { value: '' }, conditions.length ? 'Todas las condiciones' : 'No disponible en el reporte'));
  conditions.forEach((value) => condition.append(el('option', { value }, value)));
  if (conditions.length) condition.value = conditions[0];

  const warnings = state.options.warnings || [];
  const host = $('#global-error');
  if (warnings.length) host.replaceChildren(notice('warn', 'Avisos al leer los reportes:', warnings));
}

async function refreshTemperatures() {
  try {
    const data = await api('/api/temperatures', { body: { job_id: state.jobId, cable: currentCable() } });
    state.temps = data.temperatures;
    state.selectedTemps = data.temperatures.slice();
    renderTempChips();
  } catch (error) {
    fail(error.message);
  }
}

function renderTempChips() {
  const host = $('#temp-chips');
  host.replaceChildren();
  state.temps.forEach((temp) => {
    const on = state.selectedTemps.includes(temp);
    const chip = el('label', { class: `chip${on ? ' on' : ''}` }, formatTemp(temp));
    chip.addEventListener('click', () => {
      const index = state.selectedTemps.indexOf(temp);
      if (index >= 0) state.selectedTemps.splice(index, 1);
      else state.selectedTemps.push(temp);
      state.selectedTemps.sort((a, b) => a - b);
      renderTempChips();
    });
    host.append(chip);
  });
}

function formatTemp(temp) {
  return Number.isInteger(temp) ? `${temp}°C` : `${temp}°C`;
}

function currentCable() {
  const value = $('#cable-select').value;
  return value === '' ? null : Number(value);
}

$('#cable-select').addEventListener('change', async () => { await refreshTemperatures(); refreshPreview(); });
$('#condition-select').addEventListener('change', refreshPreview);
$('#temps-all').addEventListener('click', () => { state.selectedTemps = state.temps.slice(); renderTempChips(); });
$('#temps-none').addEventListener('click', () => { state.selectedTemps = []; renderTempChips(); });

// ------------------------------------------------------------------ paso 4
function renderStructures() {
  const body = $('#structures-table tbody');
  body.replaceChildren();
  const structures = state.options.structures;
  $('#structures-count').textContent =
    `${structures.filter((s) => state.kinds[s.key] === 'anclaje').length} anclaje / ` +
    `${structures.filter((s) => state.kinds[s.key] === 'suspension').length} suspensión`;

  structures.forEach((structure) => {
    const toggle = el('div', { class: 'toggle' });
    ['anclaje', 'suspension'].forEach((kind) => {
      const button = el('button', {
        type: 'button',
        class: state.kinds[structure.key] === kind ? 'on' : '',
        onclick: () => {
          state.kinds[structure.key] = kind;
          renderStructures();
          refreshPreview();
        },
      }, kind === 'anclaje' ? 'Anclaje' : 'Suspensión');
      toggle.append(button);
    });
    body.append(el('tr', {},
      el('td', {}, el('strong', { text: structure.key })),
      el('td', { text: structure.name || '—' }),
      el('td', {}, structure.has_coords
        ? el('span', { class: 'badge ok', text: 'sí' })
        : el('span', { class: 'badge warn', text: 'faltan' })),
      el('td', {}, toggle)));
  });
}

$('#kinds-reset').addEventListener('click', () => {
  state.options.structures.forEach((s) => { state.kinds[s.key] = s.auto_kind; });
  renderStructures();
  refreshPreview();
});

// ------------------------------------------------------------------ paso 5
function configPayload() {
  return {
    job_id: state.jobId,
    cable: currentCable(),
    temperatures: state.selectedTemps,
    kinds: state.kinds,
    prefix: $('#opt-prefix').value || 'E',
    condition: $('#condition-select').value || null,
  };
}

let previewTimer = null;
function refreshPreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, 180);
}

async function runPreview() {
  if (!state.jobId || !state.selectedTemps.length) {
    $('#preview-table tbody').replaceChildren();
    $('#preview-warnings').replaceChildren(
      state.jobId ? notice('warn', 'Selecciona al menos una temperatura.') : null);
    return;
  }
  try {
    const data = await api('/api/preview', { body: configPayload() });
    renderPreview(data);
  } catch (error) {
    $('#preview-table tbody').replaceChildren();
    $('#preview-warnings').replaceChildren(notice('err', error.message));
  }
}

function kindBadge(kind) {
  return el('span', { class: `badge ${kind}`, text: kind === 'anclaje' ? 'Anclaje' : 'Suspensión' });
}

function renderPreview(data) {
  const body = $('#preview-table tbody');
  body.replaceChildren();
  const decVano = Number($('#dec-vano').value || 1);
  const decDesnivel = Number($('#dec-desnivel').value || 2);
  const decRuling = Number($('#dec-ruling_span').value || 4);

  data.sections.forEach((section) => {
    const single = section.subspans.length === 1;
    const intermediate = section.intermediate.length
      ? el('span', {}, ...section.intermediate.flatMap((s, i) => [i ? ', ' : '', s.label]))
      : el('span', { class: 'muted', text: '—' });

    body.append(el('tr', {},
      el('td', {}, el('strong', { text: section.tramo })),
      el('td', {}, section.from_label, ' ', kindBadge(section.from_kind)),
      el('td', {}, section.to_label, ' ', kindBadge(section.to_kind)),
      el('td', {}, intermediate),
      el('td', { class: 'num', text: num(section.ruling_span, decRuling) }),
      el('td', { class: 'num', text: single ? num(section.subspans[0].vano, decVano) : '' }),
      el('td', { class: 'num', text: single ? num(section.subspans[0].desnivel, decDesnivel) : '' }),
      el('td', { text: section.cable === null ? '—' : `${section.cable} daN/m` })));

    if (!single) {
      section.subspans.forEach((sub) => {
        body.append(el('tr', { class: 'sub' },
          el('td', { text: `↳ ${sub.from_label}-${sub.to_label}` }),
          el('td', {}), el('td', {}), el('td', {}), el('td', {}),
          el('td', { class: 'num', text: num(sub.vano, decVano) }),
          el('td', { class: 'num', text: num(sub.desnivel, decDesnivel) }),
          el('td', {})));
      });
    }
  });

  const warnings = [...(data.warnings || [])];
  data.sections.forEach((section) => {
    section.warnings.forEach((w) => warnings.push(`${section.tramo}: ${w}`));
  });
  const host = $('#preview-warnings');
  host.replaceChildren();
  host.append(notice('ok', `${data.sections.length} tabla(s) se generarán con ${data.temperatures.length} temperatura(s).`));
  if (warnings.length) {
    const unique = [...new Set(warnings)];
    host.append(notice('warn', 'Revisa estos puntos antes de generar:', unique.slice(0, 25)));
  }
}

$('#btn-preview').addEventListener('click', runPreview);
$('#opt-prefix').addEventListener('change', refreshPreview);
['dec-vano', 'dec-desnivel', 'dec-ruling_span'].forEach((id) =>
  $(`#${id}`).addEventListener('change', runPreview));

// ------------------------------------------------------------------ paso 6
$('#btn-generate').addEventListener('click', async () => {
  const button = $('#btn-generate');
  const status = $('#generate-status');
  status.textContent = '';
  busy(button, true, 'Generando…');
  try {
    const payload = {
      ...configPayload(),
      condicion_texto: $('#condition-select').value || 'Initial RS',
      title_template: $('#opt-title').value,
      chapter: $('#opt-chapter').value,
      start_number: Number($('#opt-start').value || 1),
      font_name: $('#opt-font').value,
      font_size: Number($('#opt-size').value || 7),
      landscape: $('#opt-orient').value === 'landscape',
      decimal_separator: $('#opt-decsep').value,
      trim_trailing_zeros: $('#opt-trim').value === '1',
      document_title: $('#opt-doc-title').value,
      include_document_title: Boolean($('#opt-doc-title').value.trim()),
      decimals: Object.fromEntries(
        ['ruling_span', 'vano', 'desnivel', 'sag', 'wave', 'tension']
          .map((key) => [key, Number($(`#dec-${key}`).value || 2)])),
    };
    const response = await api('/api/generate', { body: payload, raw: true });
    const blob = await response.blob();
    const match = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') || '');
    const url = URL.createObjectURL(blob);
    const link = el('a', { href: url, download: match ? match[1] : 'tablas-tensado.docx' });
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    status.textContent = 'Documento descargado.';
  } catch (error) {
    fail(error.message);
  } finally {
    busy(button, false);
  }
});

wireDropzones();
