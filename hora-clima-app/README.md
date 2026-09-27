# Hora y Clima (Android)

App para Android que muestra:

- La **hora en Chile y en España**, con segundos y fecha. Usa las zonas horarias
  del teléfono (`America/Santiago` y `Europe/Madrid`), así que funciona sin
  conexión y sigue sola los cambios de horario de verano de cada país. Debajo
  indica cuántas horas de diferencia hay en ese momento.
- La **temperatura actual en Chillán, San Nicolás y Galapagar**, con el estado
  del cielo, la sensación térmica y la máxima y mínima del día. Los datos vienen
  de [Open-Meteo](https://open-meteo.com) (gratis, sin clave) y se actualizan al
  abrir la app, con el botón **Actualizar** y cada 15 minutos.
- El **precio del euro en pesos chilenos**: el valor oficial del Banco Central de
  Chile (vía [mindicador.cl](https://mindicador.cl)) y, si no responde, el de
  [open.er-api.com](https://open.er-api.com). Ambos gratis y sin clave.

Los últimos datos quedan guardados en el teléfono, así que al abrir la app o
sin conexión se ve lo último que se descargó.

## Widget

Resumen para la pantalla de inicio (4×2, redimensionable): hora y minuto de
Chile y España, temperatura e icono del cielo de las tres ciudades, y el euro.
Para añadirlo: mantén pulsado un hueco de la pantalla de inicio → *Widgets* →
*Hora y Clima*.

La hora avanza sola. Los datos se descargan cada 30 minutos (el mínimo que
permite Android) y cada vez que se abre la app; tocar el widget abre la app.
En HyperOS, si el widget deja de actualizarse, pon la app en *Ajustes → Batería*
como *Sin restricciones*.

Tema oscuro. Requiere Android 11 o superior.

## Instalar en el teléfono

Cada cambio en esta carpeta hace que GitHub Actions compile el APK
(workflow `.github/workflows/hora-clima-apk.yml`) y lo publique en
**Releases** del repositorio.

1. Desde el teléfono, abre la página *Releases* del repositorio y descarga
   `HoraClima.apk` de la versión más reciente.
2. Ábrelo. La primera vez Android pide permitir *instalar apps desconocidas*
   al navegador o al gestor de archivos: acéptalo.
3. En HyperOS puede aparecer un aviso de seguridad por no venir de Play Store;
   se puede continuar.

Las versiones nuevas se instalan encima de la anterior porque todas se firman
con la misma clave (`app/sideload.jks`, incluida en el repositorio). Esa clave
sirve solo para instalar a mano, no para publicar en Play Store.

## Cambiar las ciudades

Están al principio de `app/src/main/java/cl/horaclima/app/MainActivity.java`,
con nombre, región, latitud y longitud.

## Compilar en local

Con Android Studio o con el SDK de Android instalado:

```bash
cd hora-clima-app
./gradlew assembleRelease
# APK en app/build/outputs/apk/release/app-release.apk
```
