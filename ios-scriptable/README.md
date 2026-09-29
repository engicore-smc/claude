# Hora y Clima — widget para iPhone (Scriptable)

Versión para iPhone del widget de la app Android de `hora-clima-app/`,
simplificada y sin cuenta del Banco Central:

- **Hora de Chile y España.** Avanza sola; se muestra como `14:32:10`
  (Scriptable solo permite un reloj en vivo con segundos).
- **Temperatura e icono del cielo** en Chillán, San Nicolás y Galapagar.
- **UF, dólar y euro** en pesos, sin decimales.
- **IPC del último mes** (variación mensual), p. ej. `IPC ago +0,6%`.

Fuentes gratuitas y sin clave: Open-Meteo (clima) y mindicador.cl (UF, dólar y
euro del Banco Central). El IPC se deduce de la UF, que por ley sube del día 10
del mes *t* al 9 del mes *t+1* exactamente el IPC del mes *t−1*; aparece desde
el día 10, cuando la UF empieza a reflejarlo.

## Instalar

1. Instala **Scriptable** (gratis) desde la App Store.
2. Abre [`HoraClima.js`](HoraClima.js) en GitHub desde el iPhone, pulsa el botón
   de copiar el archivo (o *Raw* → seleccionar todo → copiar).
3. En Scriptable, pulsa **+**, pega el código y cambia el nombre del script
   (arriba) a **Hora y Clima**. Pulsa ▶︎ para ver una vista previa.
4. En la pantalla de inicio: mantén pulsado un hueco → **+** (arriba a la
   izquierda) → **Scriptable** → tamaño **mediano** → **Añadir widget**.
5. Mantén pulsado el widget → **Editar widget** → **Script**: *Hora y Clima*.

Para actualizarlo más adelante, se reemplaza el código del script por la
versión nueva; el widget no hay que volver a añadirlo.

## Notas

- iOS decide cuándo refresca los datos (normalmente cada 15–30 minutos). La
  hora sí avanza segundo a segundo.
- Los últimos datos se guardan en el iPhone y se muestran si no hay conexión;
  la hora pequeña en la esquina indica cuándo se descargó el clima.
- Las ciudades están al principio del script (`CIUDADES`).
