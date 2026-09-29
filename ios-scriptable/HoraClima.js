// Hora y Clima — widget para Scriptable (iPhone).
//
// Muestra la hora de Chile y España, la temperatura de Chillán, San Nicolás y
// Galapagar, y UF, dólar, euro e IPC del último mes. Tamaño recomendado:
// mediano. Instrucciones en ios-scriptable/README.md.
//
// Fuentes (gratis, sin clave): Open-Meteo para el clima y mindicador.cl
// (datos del Banco Central) para UF, dólar y euro. El IPC se deduce de la UF.

const CIUDADES = [
  { nombre: "Chillán", lat: -36.6061, lon: -72.1039 },
  { nombre: "San Nicolás", lat: -36.5000, lon: -72.2167 },
  { nombre: "Galapagar", lat: 40.5786, lon: -4.0039 },
];

const RELOJES = [
  { etiqueta: "🇨🇱 Chile", zona: "America/Santiago" },
  { etiqueta: "🇪🇸 España", zona: "Europe/Madrid" },
];

const COLOR = {
  fondo: new Color("#0F1115"),
  texto: new Color("#ECEFF4"),
  suave: new Color("#9AA3B2"),
  acento: new Color("#6CB4FF"),
};

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

// ------------------------------------------------------------------ datos

async function leerJson(url) {
  const r = new Request(url);
  r.timeoutInterval = 15;
  return await r.loadJSON();
}

async function descargarClima() {
  const lat = CIUDADES.map((c) => c.lat.toFixed(4)).join(",");
  const lon = CIUDADES.map((c) => c.lon.toFixed(4)).join(",");
  let r = await leerJson(
    "https://api.open-meteo.com/v1/forecast?latitude=" + lat + "&longitude=" + lon +
    "&current=temperature_2m,weather_code,is_day&timezone=auto");
  if (!Array.isArray(r)) r = [r];
  return r.map((x) => ({
    temp: x.current.temperature_2m,
    codigo: x.current.weather_code,
    dia: x.current.is_day === 1,
  }));
}

async function descargarMonedas() {
  const r = await leerJson("https://mindicador.cl/api");
  return { uf: r.uf.valor, dolar: r.dolar.valor, euro: r.euro.valor };
}

// La UF sube por ley, del día 10 del mes t al 9 del mes t+1, exactamente el
// IPC del mes t−1, repartido en forma geométrica por día. Con la UF del día 9
// (S) y la de hoy (T): 1 + IPC = (UF(T) / UF(S)) ^ (días del período / días transcurridos).
async function descargarIpc() {
  const hoy = (await leerJson("https://mindicador.cl/api/uf")).serie[0];
  const t = fechaDe(hoy.fecha);
  const s = t.dia >= 10 ? { anio: t.anio, mes: t.mes } : mesAnterior(t.anio, t.mes);
  const sig = mesSiguiente(s.anio, s.mes);
  const msS = Date.UTC(s.anio, s.mes - 1, 9);
  const dias = (Date.UTC(sig.anio, sig.mes - 1, 9) - msS) / 864e5;
  const transcurridos = (Date.UTC(t.anio, t.mes - 1, t.dia) - msS) / 864e5;

  const ufS = (await leerJson("https://mindicador.cl/api/uf/09-" + dos(s.mes) + "-" + s.anio)).serie[0].valor;
  const variacion = (Math.pow(hoy.valor / ufS, dias / transcurridos) - 1) * 100;
  const mesIpc = mesAnterior(s.anio, s.mes);
  return { valor: variacion, mes: MESES[mesIpc.mes - 1] };
}

// Los últimos datos se guardan en el iPhone: sin conexión se ve lo anterior.
const fm = FileManager.local();
const archivo = fm.joinPath(fm.documentsDirectory(), "horaclima.json");

function cargarGuardado() {
  try {
    return fm.fileExists(archivo) ? JSON.parse(fm.readString(archivo)) : {};
  } catch (e) {
    return {};
  }
}

async function actualizarDatos() {
  const datos = cargarGuardado();
  const [clima, monedas, ipc] = await Promise.allSettled(
    [descargarClima(), descargarMonedas(), descargarIpc()]);
  if (clima.status === "fulfilled") {
    datos.clima = clima.value;
    datos.hora = Date.now();
  }
  if (monedas.status === "fulfilled") datos.monedas = monedas.value;
  if (ipc.status === "fulfilled") datos.ipc = ipc.value;
  fm.writeString(archivo, JSON.stringify(datos));
  return datos;
}

// ---------------------------------------------------------------- formato

function dos(n) {
  return (n < 10 ? "0" : "") + n;
}

function mesAnterior(anio, mes) {
  return mes === 1 ? { anio: anio - 1, mes: 12 } : { anio, mes: mes - 1 };
}

function mesSiguiente(anio, mes) {
  return mes === 12 ? { anio: anio + 1, mes: 1 } : { anio, mes: mes + 1 };
}

// "2026-09-27T03:00:00.000Z" → { anio: 2026, mes: 9, dia: 27 }
function fechaDe(iso) {
  const [a, m, d] = iso.substring(0, 10).split("-").map(Number);
  return { anio: a, mes: m, dia: d };
}

// 41032.64 → "41.033"; con decimales, coma decimal: "0,6".
function numero(valor, decimales) {
  const [entero, fraccion] = Math.abs(valor).toFixed(decimales).split(".");
  const miles = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return (valor < 0 ? "−" : "") + miles + (fraccion ? "," + fraccion : "");
}

function grados(t) {
  const r = Math.round(t);
  return (r === 0 ? 0 : r) + "°";
}

function icono(codigo, dia) {
  if (codigo === 0) return dia ? "☀️" : "🌙";
  if (codigo === 1) return dia ? "🌤️" : "🌙";
  if (codigo === 2) return "⛅";
  if (codigo === 3) return "☁️";
  if (codigo === 45 || codigo === 48) return "🌫️";
  if (codigo >= 51 && codigo <= 57) return "🌦️";
  if (codigo >= 61 && codigo <= 67) return "🌧️";
  if (codigo >= 71 && codigo <= 77) return "🌨️";
  if (codigo >= 80 && codigo <= 82) return "🌦️";
  if (codigo === 85 || codigo === 86) return "🌨️";
  if (codigo >= 95) return "⛈️";
  return "";
}

// Medianoche de hoy en una zona horaria. Un temporizador que cuenta desde ahí
// muestra la hora local de esa zona y avanza solo, sin refrescar el widget.
function medianoche(zona) {
  const ahora = new Date();
  const [h, m, s] = new Intl.DateTimeFormat("en-GB", {
    timeZone: zona, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(ahora).split(":").map(Number);
  return new Date(ahora.getTime() - (((h % 24) * 60 + m) * 60 + s) * 1000 - ahora.getMilliseconds());
}

// ----------------------------------------------------------------- widget

function texto(pila, contenido, tamano, color, ligera) {
  const t = pila.addText(contenido);
  t.font = ligera ? Font.lightSystemFont(tamano) : Font.systemFont(tamano);
  t.textColor = color;
  t.lineLimit = 1;
  t.minimumScaleFactor = 0.7;
  return t;
}

function columna(fila) {
  const c = fila.addStack();
  c.layoutVertically();
  fila.addSpacer();
  return c;
}

async function crearWidget() {
  const datos = await actualizarDatos();
  const w = new ListWidget();
  w.backgroundColor = COLOR.fondo;
  w.setPadding(12, 14, 12, 14);

  // Horas: temporizadores desde la medianoche de cada zona.
  const filaHoras = w.addStack();
  let proximaMedianoche = Infinity;
  for (const r of RELOJES) {
    const c = columna(filaHoras);
    texto(c, r.etiqueta, 10, COLOR.suave);
    const inicio = medianoche(r.zona);
    const reloj = c.addDate(inicio);
    reloj.applyTimerStyle();
    reloj.font = Font.lightMonospacedSystemFont(24);
    reloj.textColor = COLOR.texto;
    reloj.lineLimit = 1;
    proximaMedianoche = Math.min(proximaMedianoche, inicio.getTime() + 864e5);
  }
  const hora = filaHoras.addStack();
  hora.layoutVertically();
  if (datos.hora) {
    const d = new Date(datos.hora);
    texto(hora, dos(d.getHours()) + ":" + dos(d.getMinutes()), 9, COLOR.suave);
  }

  // Temperaturas.
  w.addSpacer(6);
  const filaClima = w.addStack();
  CIUDADES.forEach((ciudad, i) => {
    const c = columna(filaClima);
    texto(c, ciudad.nombre, 10, COLOR.suave);
    const l = datos.clima && datos.clima[i];
    texto(c, l ? grados(l.temp) + " " + icono(l.codigo, l.dia) : "—", 14, COLOR.texto);
  });

  // Indicadores.
  w.addSpacer(6);
  const filaInd = w.addStack();
  const m = datos.monedas || {};
  const ipc = datos.ipc;
  const indicadores = [
    ["UF", m.uf != null ? numero(m.uf, 0) : "—"],
    ["US$", m.dolar != null ? numero(m.dolar, 0) : "—"],
    ["€", m.euro != null ? numero(m.euro, 0) : "—"],
    [ipc ? "IPC " + ipc.mes : "IPC", ipc ? (ipc.valor > 0 ? "+" : "") + numero(ipc.valor, 1) + "%" : "—"],
  ];
  for (const [nombre, valor] of indicadores) {
    const c = columna(filaInd);
    texto(c, nombre, 10, COLOR.suave);
    texto(c, valor, 13, COLOR.acento);
  }

  // iOS decide cuándo refrescar; se pide en 15 min o justo después de la
  // medianoche de Chile o España, para que el temporizador vuelva a 00:00.
  w.refreshAfterDate = new Date(Math.min(Date.now() + 15 * 60 * 1000, proximaMedianoche + 1000));
  return w;
}

const widget = await crearWidget();
if (config.runsInWidget) {
  Script.setWidget(widget);
} else {
  await widget.presentMedium();
}
Script.complete();
