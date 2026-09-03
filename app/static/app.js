'use strict';

const state = {
  jobId: null,
  reports: null,
  options: null,
  kinds: {},          // clave de estructura -> 'anclaje' | 'suspension'
  structures: [],     // estructuras conocidas, en orden
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
    ['#step-filters', '#step-preview', '#step-generate'].forEach((id) => show(id, false));
    return;
  }
  clearError();
  state.kinds = {};
  state.structures = payload.options.structures;
  state.structures.forEach((s) => { state.kinds[s.key] = s.kind; });
  renderFilters();
  renderStructures();
  show('#step-filters');
  show('#step-preview');
  show('#step-generate');
  refreshOptions().then(runPreview);
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
  const weather = $('#weather-select');
  weather.replaceChildren(el('option', { value: '' }, 'Peso propio del cable (recomendado)'));
  (state.options.weather_cases || []).forEach((name) => weather.append(el('option', { value: name }, name)));
  $('#weather-wrap').hidden = !(state.options.weather_cases || []).length;

  if (state.options.condition_text) $('#opt-condicion').value = state.options.condition_text;

  const warnings = state.options.warnings || [];
  if (warnings.length) $('#global-error').replaceChildren(notice('warn', 'Avisos al leer los reportes:', warnings));
}

function renderCables(cables) {
  const previous = $('#cable-select').value;
  const select = $('#cable-select');
  select.replaceChildren();
  if (!cables.length) select.append(el('option', { value: '' }, 'Sin conductores detectados'));
  cables.forEach((cable) => {
    select.append(el('option', { value: String(cable.value) }, `${cable.label} — ${cable.spans} vano(s)`));
  });
  if (previous && cables.some((c) => String(c.value) === previous)) select.value = previous;
}

async function refreshOptions({ keepTemps = false } = {}) {
  try {
    const data = await api('/api/options', {
      body: { job_id: state.jobId, cable: currentCable(), weather_case: currentWeather() },
    });
    renderCables(data.cables);
    const fresh = await api('/api/options', {
      body: { job_id: state.jobId, cable: currentCable(), weather_case: currentWeather() },
    });
    const previous = new Set(state.selectedTemps);
    state.temps = fresh.temperatures;
    state.selectedTemps = keepTemps
      ? fresh.temperatures.filter((t) => previous.has(t))
      : fresh.temperatures.slice();
    if (!state.selectedTemps.length) state.selectedTemps = fresh.temperatures.slice();
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
    const chip = el('label', { class: `chip${on ? ' on' : ''}` }, `${temp}°C`);
    chip.addEventListener('click', () => {
      const index = state.selectedTemps.indexOf(temp);
      if (index >= 0) state.selectedTemps.splice(index, 1);
      else state.selectedTemps.push(temp);
      state.selectedTemps.sort((a, b) => a - b);
      renderTempChips();
      refreshPreview();
    });
    host.append(chip);
  });
}

function currentCable() {
  const value = $('#cable-select').value;
  return value === '' ? null : Number(value);
}

function currentWeather() {
  return $('#weather-select').value || null;
}

$('#cable-select').addEventListener('change', async () => { await refreshOptions({ keepTemps: true }); runPreview(); });
$('#weather-select').addEventListener('change', async () => { await refreshOptions(); runPreview(); });
$('#temps-all').addEventListener('click', () => { state.selectedTemps = state.temps.slice(); renderTempChips(); refreshPreview(); });
$('#temps-none').addEventListener('click', () => { state.selectedTemps = []; renderTempChips(); refreshPreview(); });

// ------------------------------------------------------------------ paso 4
function toggleKind(key) {
  state.kinds[key] = state.kinds[key] === 'anclaje' ? 'suspension' : 'anclaje';
  renderStructures();
  runPreview();
}

/** Pastilla con el tipo de estructura; al hacer clic cambia anclaje <-> suspensión. */
function structurePill(key, label, kind) {
  return el('button', {
    type: 'button',
    class: `pill ${kind}`,
    title: `${label} · ${kind === 'anclaje' ? 'anclaje' : 'suspensión'} — clic para cambiar`,
    onclick: () => toggleKind(key),
  }, label, el('span', { class: 'pill-kind', text: kind === 'anclaje' ? 'A' : 'S' }));
}

function renderStructures() {
  const body = $('#structures-table tbody');
  body.replaceChildren();
  const anchors = state.structures.filter((s) => state.kinds[s.key] === 'anclaje').length;
  $('#structures-count').textContent =
    `· ${anchors} anclaje / ${state.structures.length - anchors} suspensión`;

  state.structures.forEach((structure) => {
    const toggle = el('div', { class: 'toggle' });
    ['anclaje', 'suspension'].forEach((kind) => {
      toggle.append(el('button', {
        type: 'button',
        class: state.kinds[structure.key] === kind ? 'on' : '',
        onclick: () => {
          if (state.kinds[structure.key] === kind) return;
          state.kinds[structure.key] = kind;
          renderStructures();
          runPreview();
        },
      }, kind === 'anclaje' ? 'Anclaje' : 'Suspensión'));
    });
    body.append(el('tr', {},
      el('td', {}, el('strong', { text: structure.key })),
      el('td', { text: structure.name || structure.description || '—' }),
      el('td', {}, structure.has_coords
        ? el('span', { class: 'badge ok', text: 'sí' })
        : el('span', { class: 'badge warn', text: 'faltan' })),
      el('td', {}, toggle)));
  });
}

$('#kinds-reset').addEventListener('click', () => {
  state.structures.forEach((s) => { state.kinds[s.key] = s.auto_kind; });
  renderStructures();
  runPreview();
});

function configPayload() {
  return {
    job_id: state.jobId,
    cable: currentCable(),
    weather_case: currentWeather(),
    temperatures: state.selectedTemps,
    kinds: state.kinds,
    prefix: $('#opt-prefix').value || 'E',
  };
}

let previewTimer = null;
function refreshPreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, 180);
}

async function runPreview() {
  if (!state.jobId) return;
  if (!state.selectedTemps.length) {
    $('#preview-table tbody').replaceChildren();
    $('#preview-warnings').replaceChildren(notice('warn', 'Selecciona al menos una temperatura.'));
    return;
  }
  try {
    const data = await api('/api/preview', { body: configPayload() });
    if (data.structures) {
      state.structures = data.structures;
      renderStructures();
    }
    renderPreview(data);
  } catch (error) {
    $('#preview-table tbody').replaceChildren();
    $('#preview-warnings').replaceChildren(notice('err', error.message));
  }
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
      ? el('span', { class: 'pill-row' },
          ...section.intermediate.map((s) => structurePill(s.key, s.label, s.kind)))
      : el('span', { class: 'muted', text: '—' });

    body.append(el('tr', {},
      el('td', {}, el('strong', { text: section.tramo })),
      el('td', {}, structurePill(section.from_key, section.from_label, section.from_kind)),
      el('td', {}, structurePill(section.to_key, section.to_label, section.to_kind)),
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
  data.sections.forEach((s) => s.warnings.forEach((w) => warnings.push(`${s.tramo}: ${w}`)));
  const host = $('#preview-warnings');
  host.replaceChildren(notice('ok',
    `${data.sections.length} tabla(s) se generarán con ${data.temperatures.length} temperatura(s).`));
  if (warnings.length) {
    host.append(notice('warn', 'Revisa estos puntos antes de generar:', [...new Set(warnings)].slice(0, 25)));
  }
}

$('#opt-prefix').addEventListener('change', refreshPreview);
['dec-vano', 'dec-desnivel', 'dec-ruling_span'].forEach((id) =>
  $(`#${id}`).addEventListener('change', runPreview));

// ------------------------------------------------------------------ paso 5
$('#btn-generate').addEventListener('click', async () => {
  const button = $('#btn-generate');
  const status = $('#generate-status');
  status.textContent = '';
  busy(button, true, 'Generando…');
  try {
    const payload = {
      ...configPayload(),
      condicion_texto: $('#opt-condicion').value.trim(),
      title_template: $('#opt-title').value,
      chapter: $('#opt-chapter').value,
      start_number: Number($('#opt-start').value || 1),
      font_name: $('#opt-font').value,
      font_size: Number($('#opt-size').value || 8),
      page_size: $('#opt-page').value,
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
