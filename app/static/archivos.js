'use strict';

// Guarda en el propio navegador (IndexedDB) los archivos que se suben, para
// no tener que volver a elegirlos cada vez que se recarga la página. Los
// archivos nunca salen del equipo: al recargar se vuelven a enviar solos.

const BD_NOMBRE = 'plscadd';
const BD_VERSION = 1;
const ALMACEN = 'archivos';

function hayAlmacen() {
  try {
    return typeof indexedDB !== 'undefined' && indexedDB !== null;
  } catch {
    return false;
  }
}

function abrirBD() {
  return new Promise((resolve, reject) => {
    const peticion = indexedDB.open(BD_NOMBRE, BD_VERSION);
    peticion.onupgradeneeded = () => {
      const bd = peticion.result;
      if (!bd.objectStoreNames.contains(ALMACEN)) bd.createObjectStore(ALMACEN);
    };
    peticion.onsuccess = () => resolve(peticion.result);
    peticion.onerror = () => reject(peticion.error);
    peticion.onblocked = () => reject(new Error('IndexedDB bloqueada'));
  });
}

async function conAlmacen(modo, accion) {
  const bd = await abrirBD();
  try {
    return await new Promise((resolve, reject) => {
      const tx = bd.transaction(ALMACEN, modo);
      const peticion = accion(tx.objectStore(ALMACEN));
      tx.oncomplete = () => resolve(peticion ? peticion.result : undefined);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    bd.close();
  }
}

/** Deja guardados los archivos indicados bajo una clave. */
async function guardarArchivos(clave, archivos) {
  if (!hayAlmacen()) return false;
  try {
    const registros = await Promise.all(Array.from(archivos).map(async (f) => ({
      nombre: f.name, tipo: f.type || '', datos: await f.arrayBuffer(),
    })));
    await conAlmacen('readwrite', (a) => a.put({ guardado: Date.now(), registros }, clave));
    return true;
  } catch {
    return false;   // navegador sin permiso de almacenamiento: seguimos sin guardar
  }
}

/** Devuelve los archivos guardados como objetos File, o una lista vacía. */
async function leerArchivos(clave) {
  if (!hayAlmacen()) return [];
  try {
    const guardado = await conAlmacen('readonly', (a) => a.get(clave));
    const registros = guardado && Array.isArray(guardado.registros) ? guardado.registros : [];
    return registros.map((r) => new File([r.datos], r.nombre, { type: r.tipo || '' }));
  } catch {
    return [];
  }
}

/** Borra los archivos guardados bajo esa clave. */
async function olvidarArchivos(clave) {
  if (!hayAlmacen()) return;
  try {
    await conAlmacen('readwrite', (a) => a.delete(clave));
  } catch { /* nada que borrar */ }
}
