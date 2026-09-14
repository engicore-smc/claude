'use strict';

// Utilidades compartidas por las dos herramientas.

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

