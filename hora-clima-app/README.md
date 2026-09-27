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
